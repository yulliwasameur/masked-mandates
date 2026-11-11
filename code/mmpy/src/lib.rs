//! Python bindings: agent-side wallet and tool-side verifier.
//! Every process derives the same issuer, accumulator and escrow keys from the seed (key distribution is out of scope of E2).
use mmcore::*;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

fn sc(cls: &[usize]) -> Vec<bool> { let mut s = vec![false; NCLS]; for &c in cls { s[c] = true; } s }

#[pyclass(unsendable)]
struct Wallet { sys: System, m: Mandate, r: rand::rngs::StdRng, j: std::collections::HashMap<(String, u64), u64> }

#[pymethods]
impl Wallet {
    /// Builds a two-level delegation (root -> agent -> sub-agent) and keeps the sub-agent's mandate.
    #[new]
    fn new(seed: u64) -> PyResult<Self> {
        let mut r = rng(seed);
        let mut sys = System::setup(&mut r, 1000);
        let mut r2 = rng(seed + 1);
        let root = sys.issue_root(&mut r2, &Attrs { id: 11, anc: [0; 4], depth: 0, scope: sc(&[0, 1, 2]), budget: 10_000, k: 1_000_000, exp: u64::MAX >> 25, uid: 42 })
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
        let (a1, _, _) = sys.delegate(&mut r2, &root, &Attrs { id: 12, anc: [11, 0, 0, 0], depth: 1, scope: sc(&[0, 1]), budget: 5_000, k: 500_000, exp: (u64::MAX >> 25) - 1, uid: 42 }, 0, 0)
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
        let (a2, _, _) = sys.delegate(&mut r2, &a1, &Attrs { id: 13, anc: [12, 11, 0, 0], depth: 2, scope: sc(&[1]), budget: 1_000, k: 100_000, exp: (u64::MAX >> 25) - 2, uid: 42 }, 0, 0)
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
        Ok(Wallet { sys, m: a2, r: rng(seed + 2), j: Default::default() })
    }
    /// Returns the serialized presentation for one canonical tools/call.
    fn present<'py>(&mut self, py: Python<'py>, tool: String, call: String, class: usize, amt: u64, epoch: u64, t: u64, nonce: String, escrow: bool) -> PyResult<Bound<'py, PyBytes>> {
        let e = self.j.entry((tool.clone(), epoch)).or_insert(0);
        let j = *e; *e += 1;
        let inv = Invocation { tool, call, class, amt, epoch, t, nonce };
        let p = self.sys.present(&mut self.r, &self.m, &inv, j, escrow).map_err(pyo3::exceptions::PyValueError::new_err)?;
        Ok(PyBytes::new_bound(py, &p.to_bytes()))
    }
}

#[pyclass(unsendable)]
struct Verifier { sys: System, tool: Tool, r: rand::rngs::StdRng }

#[pymethods]
impl Verifier {
    #[new]
    fn new(seed: u64, tool: String, require_escrow: bool) -> Self {
        let mut r = rng(seed);
        let sys = System::setup(&mut r, 1000);
        Verifier { sys, tool: Tool::new(&tool, require_escrow), r: rng(seed + 3) }
    }
    fn verify(&mut self, call: String, class: usize, amt: u64, epoch: u64, t: u64, nonce: String, blob: &[u8]) -> (bool, String) {
        let p = match Presentation::from_bytes(blob) { Ok(p) => p, Err(e) => return (false, e) };
        let inv = Invocation { tool: self.tool.name.clone(), call, class, amt, epoch, t, nonce };
        match self.sys.verify(&mut self.r, &mut self.tool, &inv, &p) { Ok(()) => (true, String::new()), Err(e) => (false, e) }
    }
}

#[pymodule]
fn mmpy(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Wallet>()?;
    m.add_class::<Verifier>()?;
    Ok(())
}
