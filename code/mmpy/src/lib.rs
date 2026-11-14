//! Python bindings, version 2.1: separated roles.
//!  * `Authority`: issuer + escrow committee + registered principals + the agents' wallet (holds the secret keys);
//!    builds mandates and delegations, allocates disjoint counter intervals, revokes, exports public parameters.
//!  * `Verifier`: tool side, built from the exported public parameters only (no secret key); in strict mode it
//!    issues single-use nonces and checks the epoch and the time; errors are uniform unless `debug=True`.
//! Agents' mandates live in the Authority object of the harness process (the agent wallet); tools never see them.
//!
//! Version 2.2 additions (E4 v2.2, reviewer requests R2-B1 and R2-B3; the core crate is unchanged):
//!  * `Authority.present_dishonest(...)`: TEST/DEBUG ONLY. A dishonest wallet that ignores the wallet's policy checks
//!    (revoked/stale mandate, quota exhausted) but never the cryptography: it proves with the witnesses it actually holds
//!    (the snapshot taken just before its mandate was revoked, against the accumulator value of that moment, or its
//!    current, partially refreshed witnesses against the current value) and with counters it chooses (reuse of a counter
//!    of its own part, or a counter outside its interval). The tools decide.
//!  * `Verifier(..., grace_ms=D)`: time-bounded grace rule at the tool. The tool records when it installed each new
//!    accumulator value (`update`) and accepts a presentation against a previous value only if that value's successor
//!    was installed at this tool less than D ms before the verification (on top of the issuer's count window, if any).
//!  * `Verifier.last_reason()` / `last_path()`: tool-side diagnostics of the last verification (internal reason and
//!    acceptance path), for the tool's own logs; the error returned to the caller stays uniform unless `debug=True`.
//!
//! Version 2.2.0: `release_counter` only allows an immediate retry of the SAME call. The released counter is stored with
//! (idx, tool, epoch, SHA-256 of the canonical call); the next `present` for (idx, tool, epoch) reuses it only if the call
//! hash matches; otherwise the released counter is burned (never reused) and a fresh counter is drawn.
use mmcore::*;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::time::Instant;

fn sc(cls: &[usize]) -> Vec<bool> { let mut s = vec![false; NCLS]; for &c in cls { s[c] = true; } s }
fn err(e: String) -> PyErr { pyo3::exceptions::PyValueError::new_err(e) }

#[pyclass(unsendable)]
struct Authority {
    sys: System,
    r: rand::rngs::StdRng,
    mandates: Vec<Mandate>,
    parent: Vec<Option<usize>>,
    /// Top of the part of each mandate's interval not yet given to children: the mandate itself uses [lo, carve).
    carve: Vec<u64>,
    /// Wallet refuses to present with a mandate whose witnesses could not be refreshed (revoked id or ancestor).
    stale: Vec<bool>,
    /// Next counter offset per (mandate, tool or delegation domain, epoch).
    counters: HashMap<(usize, String, u64), u64>,
    /// Snapshot of a mandate taken just before the revocation that made it stale, with the accumulator value its
    /// witnesses were valid against (used only by `present_dishonest`).
    snap: Vec<Option<(Mandate, G1)>>,
    /// Issuer misbehaviour detected by the wallets (update data failing the public check, witnesses that fail while not revoked).
    misbehaviour: Vec<String>,
    /// Last honest presentation per (mandate, tool, epoch): (counter offset, SHA-256 of the canonical call).
    last_call: HashMap<(usize, String, u64), (u64, [u8; 32])>,
    /// Counter released for an immediate retry per (mandate, tool, epoch): (counter offset, SHA-256 of the call).
    released: HashMap<(usize, String, u64), (u64, [u8; 32])>,
    /// Released counters that were burned (next call differed), per (mandate, tool, epoch), for diagnostics.
    burned: HashMap<(usize, String, u64), Vec<u64>>,
}
fn call_hash(call: &str) -> [u8; 32] { Sha256::digest(call.as_bytes()).into() }

#[pymethods]
impl Authority {
    /// Setup; mandate 0 is a root for principal `uid` with classes 0..2, per-call cap `budget`, counter interval [0, k),
    /// expiry `exp`; `grace` previous accumulator values stay accepted after a revocation (0 = immediate).
    #[new]
    #[pyo3(signature = (seed, uid=42, budget=100_000, k=100_000, exp=1u64<<39, grace=0))]
    fn new(seed: u64, uid: u64, budget: u64, k: u64, exp: u64, grace: usize) -> PyResult<Self> {
        if k > QMAX { return Err(err("wallet: root interval wider than the public bound Q".into())); }
        let mut r = rng(seed);
        let mut sys = System::setup(&mut r, 10_000);
        sys.acc_grace = grace;
        let root = sys.issue_root(&mut r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: sc(&[0, 1, 2]), lo: 0, budget, k, exp, uid }).map_err(err)?;
        let carve = root.a.k;
        Ok(Authority { sys, r, mandates: vec![root], parent: vec![None], carve: vec![carve], stale: vec![false], counters: HashMap::new(), snap: vec![None], misbehaviour: vec![],
                       last_call: HashMap::new(), released: HashMap::new(), burned: HashMap::new() })
    }
    /// Issuer misbehaviour detected by the wallets so far.
    fn issuer_misbehaviour(&self) -> Vec<String> { self.misbehaviour.clone() }
    /// Public parameters for tools (no secret, no proof-system bases: tools derive those from public labels).
    fn public_params<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> { PyBytes::new_bound(py, &self.sys.p.to_bytes()) }
    /// Delegates from mandate `parent` to a new sub-agent with `k` counters carved from the top of the parent's free
    /// interval; the issuer's clock is set to `epoch`. Returns (index, parent_ms, issuer_ms).
    fn delegate(&mut self, parent: usize, classes: Vec<usize>, budget: u64, k: u64, exp: u64, epoch: u64) -> PyResult<(usize, f64, f64)> {
        if self.stale[parent] { return Err(err("wallet: mandate revoked or witnesses stale".into())); }
        let p = self.mandates[parent].clone();
        let top = self.carve[parent];
        let used_by_parent = self.max_used(parent);
        if k == 0 || top < p.a.lo + k || top - k < p.a.lo + used_by_parent { return Err(err("wallet: not enough free counters in the parent's interval".into())); }
        // reserve the delegation counter first, then make sure the child's interval does not contain it
        let j = self.next_j(parent, "MM-delegation".into(), epoch)?;
        if top - k < p.a.lo + self.max_used(parent).max(j + 1) { return Err(err("wallet: not enough free counters in the parent's interval".into())); }
        let a = Attrs::child_range(&p.a, sc(&classes), budget, top - k, top, exp);
        let (m, pm, im) = self.sys.delegate(&mut self.r, &p, &a, epoch, j).map_err(err)?;
        self.carve[parent] = top - k;
        let c = m.a.k;
        self.mandates.push(m); self.parent.push(Some(parent)); self.carve.push(c); self.stale.push(false); self.snap.push(None);
        Ok((self.mandates.len() - 1, pm, im))
    }
    /// Presentation by mandate `idx` for one canonical tools/call; the hidden counter is the next free one in the
    /// mandate's own part of its interval for this tool and epoch, except for an immediate retry of the same call after
    /// `release_counter` (same canonical call: the released counter is reused; another call: it is burned).
    #[pyo3(signature = (idx, tool, call, class_, amt, epoch, t, nonce, escrow, cur="EUR".to_string()))]
    fn present<'py>(&mut self, py: Python<'py>, idx: usize, tool: String, call: String, class_: usize, amt: u64, epoch: u64, t: u64, nonce: String, escrow: bool, cur: String) -> PyResult<Bound<'py, PyBytes>> {
        if self.stale[idx] { return Err(err("wallet: mandate revoked or witnesses stale".into())); }
        let m = self.mandates[idx].clone();
        let key = (idx, tool.clone(), epoch);
        let h = call_hash(&call);
        let j = match self.released.remove(&key) {
            Some((j, hr)) if hr == h => j,
            Some((j, _)) => { self.burned.entry(key.clone()).or_default().push(j); self.next_j(idx, tool.clone(), epoch)? }
            None => self.next_j(idx, tool.clone(), epoch)?,
        };
        self.last_call.insert(key, (j, h));
        let inv = Invocation { tool, call, class: class_, amt, cur, epoch, t, nonce };
        let p = self.sys.present(&mut self.r, &m, &inv, j, escrow).map_err(err)?;
        Ok(PyBytes::new_bound(py, &p.to_bytes()))
    }
    /// Revokes mandate `idx` (and therefore its subtree); every other mandate refreshes its witnesses from public data;
    /// mandates that cannot refresh are marked stale and the wallet refuses to present with them.
    /// Returns the new public parameters (new accumulator value) to distribute to tools.
    fn revoke<'py>(&mut self, py: Python<'py>, idx: usize) -> PyResult<Bound<'py, PyBytes>> {
        let id = self.mandates[idx].a.id;
        let old = self.sys.p.accv;
        let (om, ad, chk) = self.sys.revoke_checked(&[id]).map_err(err)?;
        // wallets check the published update data before refreshing (issuer misbehaviour otherwise)
        // the update must start from the value the wallets hold (log binding) and pass the public spot check; otherwise the
        // wallets refuse to refresh and stop presenting (issuer misbehaviour)
        if chk.v_old != old || !self.sys.p.check_update(&ad, &om, &chk) {
            self.misbehaviour.push(format!("update data for revocation of {id} failed the public check"));
            for s in self.stale.iter_mut() { *s = true; }
            return Ok(PyBytes::new_bound(py, &self.sys.p.to_bytes()));
        }
        for i in 0..self.mandates.len() {
            // dishonest-wallet test support: keep the last valid state (witnesses valid against `old`) of a mandate hit by this batch
            let hit = !self.stale[i] && self.mandates[i].ids().iter().any(|x| *x != 0 && ad.contains(&fr(*x)));
            let before = if hit { Some(self.mandates[i].clone()) } else { None };
            let stuck = !self.mandates[i].refresh_partial(&ad, &om).is_empty();
            // a non-revoked mandate whose refreshed witnesses do not verify signals issuer misbehaviour: stop presenting
            let bad_witness = !stuck && !self.sys.p.witnesses_valid(&self.mandates[i]);
            if bad_witness { self.misbehaviour.push(format!("mandate {i}: witness fails although not revoked")); }
            if stuck || bad_witness {
                if !self.stale[i] { if let Some(b) = before { self.snap[i] = Some((b, old)); } }
                self.stale[i] = true;
            }
        }
        Ok(PyBytes::new_bound(py, &self.sys.p.to_bytes()))
    }
    /// TEST/DEBUG ONLY -- dishonest wallet. Same as `present` but bypasses the wallet's policy checks (never the proof):
    ///  * revoked/stale mandate: `acc="stale"` proves with the snapshot taken just before the revocation, against the
    ///    accumulator value of that moment; `acc="current"` proves with the current (partially refreshed) witnesses against
    ///    the current value (the witness of a revoked identifier cannot be valid: the proof fails or is rejected);
    ///    `acc="refuse"` behaves like the honest wallet;
    ///  * quota exhausted (own part [lo, carve) used up for this tool and epoch): `counter="reuse"` reuses the counters of
    ///    its own part cyclically (same pseudonym as an earlier call: the tool's seen-set must reject), `counter="beyond"`
    ///    uses the next counters past its own part (outside its interval if it has no children), `counter="refuse"` behaves
    ///    like the honest wallet.
    /// Returns (presentation, counter offset used, accumulator path used, policy checks bypassed: "", "revoked", "quota",
    /// "revoked+quota"). Raises ValueError if the proof cannot be built (e.g. the prover rejects an invalid witness).
    #[pyo3(signature = (idx, tool, call, class_, amt, epoch, t, nonce, escrow, cur="EUR".to_string(), acc="stale".to_string(), counter="reuse".to_string()))]
    fn present_dishonest<'py>(&mut self, py: Python<'py>, idx: usize, tool: String, call: String, class_: usize, amt: u64, epoch: u64, t: u64,
                              nonce: String, escrow: bool, cur: String, acc: String, counter: String) -> PyResult<(Bound<'py, PyBytes>, u64, String, String)> {
        let mut bypass = vec![];
        let (m, ch, path) = if self.stale[idx] {
            bypass.push("revoked");
            match acc.as_str() {
                "stale" => match &self.snap[idx] {
                    Some((sm, v)) => (sm.clone(), Cheat { acc_value: Some(*v), ..Default::default() }, "stale_snapshot"),
                    None => return Err(err("dishonest wallet: no pre-revocation snapshot of this mandate".into())),
                },
                "current" => (self.mandates[idx].clone(), Cheat::default(), "current_with_stale_witness"),
                "refuse" => return Err(err("wallet: mandate revoked or witnesses stale".into())),
                _ => return Err(err(format!("unknown acc policy {acc}"))),
            }
        } else { (self.mandates[idx].clone(), Cheat::default(), "current") };
        let (lo, top) = (self.mandates[idx].a.lo, self.carve[idx]);
        let own = top - lo;
        // a dishonest presentation ends any pending retry for this key (a released counter is burned)
        let key = (idx, tool.clone(), epoch);
        self.last_call.remove(&key);
        if let Some((jr, _)) = self.released.remove(&key) { self.burned.entry(key).or_default().push(jr); }
        let used = self.counters.entry((idx, tool.clone(), epoch)).or_insert(0);
        let j = if *used < own { *used } else {
            bypass.push("quota");
            match counter.as_str() {
                "reuse" => { if own == 0 { return Err(err("dishonest wallet: no counter of its own to reuse".into())); } (*used - own) % own }
                "beyond" => *used,
                "refuse" => return Err(err("wallet: quota exhausted for this tool and epoch".into())),
                _ => return Err(err(format!("unknown counter policy {counter}"))),
            }
        };
        *used += 1;
        let inv = Invocation { tool, call, class: class_, amt, cur, epoch, t, nonce };
        let p = self.sys.p.present_cheat(&mut self.r, &m, &inv, j, escrow, &ch).map_err(err)?;
        Ok((PyBytes::new_bound(py, &p.to_bytes()), j, path.to_string(), bypass.join("+")))
    }
    /// Honest-wallet retry support, for an IMMEDIATE retry of the same call only: releases the counter of the last
    /// presentation made by mandate `idx` for (`tool`, `epoch`) after the tool REJECTED it (a tool never records the
    /// pseudonym of a rejected presentation: the core verifier checks the accumulator value before the seen-set and releases
    /// its reservation on failure). The released counter is stored with the SHA-256 of that presentation's canonical call;
    /// the next `present` for (idx, tool, epoch) reuses it only for the same call, otherwise it is burned (never reused).
    /// The counter is never returned to the free pool. Returns false if there is nothing to release (no presentation since
    /// the last release or retry).
    fn release_counter(&mut self, idx: usize, tool: String, epoch: u64) -> bool {
        let key = (idx, tool, epoch);
        match self.last_call.remove(&key) {
            Some(v) => {
                if let Some((jr, _)) = self.released.insert(key.clone(), v) { self.burned.entry(key).or_default().push(jr); }
                true
            }
            None => false,
        }
    }
    /// Retry diagnostics for (`idx`, `tool`, `epoch`): (counters consumed, released counter pending a retry, burned counters).
    fn retry_state(&self, idx: usize, tool: String, epoch: u64) -> (u64, Option<u64>, Vec<u64>) {
        let key = (idx, tool, epoch);
        (*self.counters.get(&key).unwrap_or(&0), self.released.get(&key).map(|v| v.0), self.burned.get(&key).cloned().unwrap_or_default())
    }
    fn mandate_id(&self, idx: usize) -> u64 { self.mandates[idx].a.id }
    /// Counter interval [lo, k) of a mandate and the top of its own part.
    fn interval(&self, idx: usize) -> (u64, u64, u64) { let a = &self.mandates[idx].a; (a.lo, a.k, self.carve[idx]) }
    fn is_stale(&self, idx: usize) -> bool { self.stale[idx] }
}
impl Authority {
    /// Offset (from lo) of the next counter of mandate `idx` in a domain and epoch, inside [lo, carve).
    fn next_j(&mut self, idx: usize, dom: String, epoch: u64) -> PyResult<u64> {
        let (lo, top) = (self.mandates[idx].a.lo, self.carve[idx]);
        let used = self.counters.entry((idx, dom, epoch)).or_insert(0);
        if lo + *used >= top { return Err(err("wallet: quota exhausted for this tool and epoch".into())); }
        let j = *used; *used += 1;
        Ok(j)
    }
    fn max_used(&self, idx: usize) -> u64 { self.counters.iter().filter(|((i, _, _), _)| *i == idx).map(|(_, v)| *v).max().unwrap_or(0) }
}

#[pyclass(unsendable)]
struct Verifier {
    p: Pub, tool: Tool, r: rand::rngs::StdRng, debug: bool,
    /// Time-bounded grace (ms): previous accumulator values accepted while their successor was installed here < grace_ms ago.
    grace_ms: Option<u64>,
    /// The issuer's count window as received in the public parameters (the effective window is rebuilt before each verify).
    issuer_window: Vec<G1>,
    /// Previous accumulator values and the instant their successor was installed at this tool (most recent last).
    hist: Vec<(G1, Instant)>,
    last_reason: String,
    last_path: String,
}

#[pymethods]
impl Verifier {
    /// `epoch` and `now` switch on the deployment checks (tool epoch, time within `tol` seconds, own single-use nonces).
    #[new]
    /// `grace_ms` (optional) switches on the time-bounded grace rule (see the module documentation).
    #[pyo3(signature = (public_params, tool, require_escrow, seed, epoch=None, now=None, tol=300, debug=false, grace_ms=None))]
    fn new(public_params: &[u8], tool: String, require_escrow: bool, seed: u64, epoch: Option<u64>, now: Option<u64>, tol: u64, debug: bool, grace_ms: Option<u64>) -> PyResult<Self> {
        let p = Pub::from_bytes(public_params).map_err(err)?;
        let tool = match (epoch, now) { (Some(e), Some(n)) => Tool::strict(&tool, require_escrow, e, n, tol), _ => Tool::new(&tool, require_escrow) };
        let issuer_window = p.acc_window.clone();
        Ok(Verifier { p, tool, r: rng(seed), debug, grace_ms, issuer_window, hist: vec![], last_reason: String::new(), last_path: String::new() })
    }
    /// Installs new public parameters (after a revocation); records the installation instant of a new accumulator value.
    fn update(&mut self, public_params: &[u8]) -> PyResult<()> {
        let np = Pub::from_bytes(public_params).map_err(err)?;
        let now = Instant::now();
        if np.accv != self.p.accv { self.hist.push((self.p.accv, now)); }
        match self.grace_ms {
            Some(g) => self.hist.retain(|(_, t)| now.duration_since(*t).as_millis() < g as u128 + 1000),
            None => self.hist.clear(),
        }
        self.issuer_window = np.acc_window.clone();
        self.p = np;
        Ok(())
    }
    /// Time-bounded grace window in ms (None = off).
    #[getter]
    fn grace_ms(&self) -> Option<u64> { self.grace_ms }
    /// Internal reason of the last verification ("" if accepted): for the tool's own logs, never for the caller.
    fn last_reason(&self) -> String { self.last_reason.clone() }
    /// Acceptance path of the last verification: "current", "count_window" (issuer's W), "time_window" (grace_ms), or "".
    fn last_path(&self) -> String { self.last_path.clone() }
    /// Previous accumulator values currently accepted by the time rule (for diagnostics).
    fn time_window_len(&self) -> usize {
        let now = Instant::now();
        match self.grace_ms { Some(g) => self.hist.iter().filter(|(_, t)| now.duration_since(*t).as_millis() < g as u128).count(), None => 0 }
    }
    /// Issues a single-use nonce (strict mode).
    fn challenge(&mut self) -> String { self.tool.issue_nonce(&mut self.r) }
    /// Moves the tool's clock.
    fn set_clock(&mut self, epoch: u64, now: u64) { self.tool.set_clock(epoch, now) }
    #[pyo3(signature = (call, class_, amt, epoch, t, nonce, blob, cur="EUR".to_string()))]
    fn verify(&mut self, call: String, class_: usize, amt: u64, epoch: u64, t: u64, nonce: String, blob: &[u8], cur: String) -> (bool, String) {
        // effective window = issuer's count window + values whose successor was installed here less than grace_ms ago
        let mut tw: Vec<G1> = vec![];
        if let Some(g) = self.grace_ms {
            let now = Instant::now();
            for (v, ti) in &self.hist { if now.duration_since(*ti).as_millis() < g as u128 && !self.issuer_window.contains(v) { tw.push(*v); } }
        }
        let mut w = self.issuer_window.clone(); w.extend(tw.iter().cloned());
        self.p.acc_window = w;
        let mut path = String::new();
        let r = Presentation::from_bytes(blob).map_err(|e| format!("parse: {e}")).and_then(|p| {
            path = if p.accv == self.p.accv { "current" } else if self.issuer_window.contains(&p.accv) { "count_window" } else if tw.contains(&p.accv) { "time_window" } else { "" }.to_string();
            let inv = Invocation { tool: self.tool.name.clone(), call, class: class_, amt, cur, epoch, t, nonce };
            self.p.verify(&mut self.r, &mut self.tool, &inv, &p)
        });
        self.p.acc_window = self.issuer_window.clone();
        match r {
            Ok(()) => { self.last_reason = String::new(); self.last_path = path; (true, String::new()) }
            Err(e) => { self.last_reason = e.clone(); self.last_path = String::new(); (false, if self.debug { e } else { "rejected".into() }) }
        }
    }
}

#[pymodule]
fn mmpy(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Authority>()?;
    m.add_class::<Verifier>()?;
    Ok(())
}
