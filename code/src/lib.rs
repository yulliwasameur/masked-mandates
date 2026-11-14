//! mm-core — Masked Mandates, version 2.2 (revision after the second round of reviews, 13-14/11/2026).
//! BBS+ (bbs_plus 0.25), VB universal accumulator (vb_accumulator 0.29),
//! Bulletproofs++ (bulletproofs_plus_plus 0.9), composite proofs (proof_system 0.34), BLS12-381.
//!
//! Construction (see the paper, Sec. IV, and the supplement):
//!  * the `uid` slot of a mandate holds the per-root tag t (T = g^t), bound to the principal by a Schnorr signature
//!    under its registered key pk_P = g^{u_P} on (label, T); u_P never leaves the principal; Judge checks the binding
//!    against a registry held outside the issuer (`judge_with`);
//!  * the issuer chooses every mandate identifier (root and delegated), non-zero and unique;
//!  * the link secret s and the tag t are shared by a delegation tree; each call uses a hidden counter j in the
//!    mandate's interval [lo, k): nym = B_{tool,e}^{1/(s+j+1)} (Dodis-Yampolskiy), with j - lo + 1 in [1, 2^40) and
//!    k - j - 1 in [0, 2^40); children receive disjoint sub-intervals; the issuer bounds root intervals by QMAX;
//!  * the escrow encrypts g^t and g^id under a key from a 3-party DKG (Pedersen VSS, then Feldman reveal);
//!  * all bases and proving keys are derived by hashing public labels; tools hold public data only (`Pub`);
//!  * v2.2: the revocation log accepts a revocation of identifier X only with an authorization (`RevocationAuth`):
//!    an anonymous proof, by a holder of the credential of the live mandate whose own id is X (its holder, or the parent
//!    that keeps the child credential it obtained when delegating; v2.2.1: never a descendant), or Schnorr signatures
//!    of two distinct escrow committee members on (X, log nonce); identifier 0 is never revocable (`System::revoke_authorized`).
#![allow(non_snake_case)]
use ark_bls12_381::{Bls12_381, Fr, G1Affine, G1Projective};
use ark_ec::{AffineRepr, CurveGroup};
use ark_ff::{Field, One, PrimeField, Zero};
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use ark_std::{
    collections::{BTreeMap, BTreeSet},
    rand::{rngs::StdRng, RngCore, SeedableRng},
    UniformRand,
};
use bbs_plus::prelude::{KeypairG2, PublicKeyG2, SignatureG1, SignatureParamsG1};
use blake2::Blake2b512;
use bulletproofs_plus_plus::prelude::SetupParams as BppParams;
use dock_crypto_utils::hashing_utils::affine_group_elem_from_try_and_incr;
use proof_system::{
    prelude::{EqualWitnesses, MetaStatements, Proof, Witness, WitnessRef, Witnesses},
    proof_spec::ProofSpec,
    statement::{
        accumulator::VBAccumulatorNonMembership as NonMemStmt,
        bbs_plus::{PoKBBSSignatureG1Prover as BbsP, PoKBBSSignatureG1Verifier as BbsV},
        bound_check_bpp::BoundCheckBpp,
        ped_comm::PedersenCommitment as PedStmt,
        Statements,
    },
    witness::{NonMembership as NonMemWit, PoKBBSSignatureG1 as BbsWit},
};
use sha2::{Digest, Sha256};
use vb_accumulator::prelude::{
    Accumulator, Keypair as AccKeypair, NonMembershipProvingKey, NonMembershipWitness, Omega,
    PublicKey as AccPublicKey, SetupParams as AccParams, UniversalAccumulator,
};

pub type E = Bls12_381;
pub use ark_bls12_381::{Fr as Scalar, G1Affine as G1};

pub const NCLS: usize = 16; // default
pub const I_S: usize = 0;
pub const I_ID: usize = 1;
pub const I_ANC: usize = 2; // 2..=5
pub const I_DEPTH: usize = 6;
pub const I_SCOPE: usize = 7; // 7..7+n
#[derive(Clone, Copy, Debug)]
pub struct Lay { pub n: usize }
impl Lay {
    pub fn l(&self) -> usize { 13 + self.n }
    pub fn budget(&self) -> usize { 7 + self.n }
    /// Counter interval [lo, k): the mandate may use pseudonym counters lo <= j < k (disjoint sub-intervals for children).
    pub fn lo(&self) -> usize { 8 + self.n }
    pub fn k(&self) -> usize { 9 + self.n }
    pub fn exp(&self) -> usize { 10 + self.n }
    pub fn uid(&self) -> usize { 11 + self.n }
    pub fn ver(&self) -> usize { 12 + self.n }
    /// Message indices committed by the parent in a delegation (all but id and ver).
    pub fn deleg_committed(&self) -> Vec<usize> {
        let mut v = vec![I_S];
        for i in I_ANC..=self.uid() { v.push(i); }
        v
    }
}
pub const MAXDEPTH: u64 = 4;
pub const MAXV: u64 = 1 << 40;
/// Issuer policy Q: largest root counter interval k0 - l0 (bounds the DY counter domain; see the UNL theorem).
pub const QMAX: u64 = 1 << 20;
/// Marker for DelegCheat::rebind: the delegation counter's upper bound (j < k) instead of a message index.
pub const REBIND_COUNTER: usize = usize::MAX;

pub fn fr(x: u64) -> Fr { Fr::from(x) }
/// Hash to G1 with an explicit domain tag and length-prefixed fields (injective encoding).
pub fn h2g_parts(domain: &str, parts: &[&[u8]]) -> G1Affine {
    let mut b = Vec::new();
    for p in std::iter::once(domain.as_bytes()).chain(parts.iter().copied()) {
        b.extend_from_slice(&(p.len() as u64).to_le_bytes());
        b.extend_from_slice(p);
    }
    affine_group_elem_from_try_and_incr::<G1Affine, Blake2b512>(&b)
}
pub fn h2g(label: &[u8]) -> G1Affine { h2g_parts("MM-v2-generator", &[label]) }
fn wref(a: usize, b: usize) -> WitnessRef { (a, b) }
fn eq(v: &[(usize, usize)]) -> EqualWitnesses { EqualWitnesses(v.iter().map(|&(a, b)| wref(a, b)).collect::<BTreeSet<_>>()) }
pub fn ser_len<T: CanonicalSerialize>(t: &T) -> usize { t.compressed_size() }
fn ser<T: CanonicalSerialize>(t: &T, b: &mut Vec<u8>) { t.serialize_compressed(b).unwrap() }

#[derive(Clone, Debug)]
pub struct Attrs {
    pub id: u64,        // chosen by the issuer; ignored on input
    pub anc: [u64; 4],
    pub depth: u64,
    pub scope: Vec<bool>,
    pub budget: u64,    // per-call amount bound
    pub lo: u64,        // counter interval [lo, k) per tool and epoch; children get disjoint sub-intervals
    pub k: u64,         // upper end (exclusive) of the counter interval
    pub exp: u64,
    pub uid: u64,       // label of the principal in the registry (the signed value in this slot is the per-root tag t)
}
impl Attrs {
    pub fn lay(&self) -> Lay { Lay { n: self.scope.len() } }
    /// Public numeric messages id..exp (uid and s excluded: they are secrets of the holder).
    pub fn msgs_public(&self) -> Vec<(usize, Fr)> {
        let mut v = vec![(I_ID, fr(self.id))];
        for i in 0..4 { v.push((I_ANC + i, fr(self.anc[i]))); }
        v.push((I_DEPTH, fr(self.depth)));
        let y = self.lay();
        for c in 0..y.n { v.push((I_SCOPE + c, if self.scope[c] { Fr::one() } else { Fr::zero() })); }
        v.push((y.budget(), fr(self.budget)));
        v.push((y.lo(), fr(self.lo)));
        v.push((y.k(), fr(self.k)));
        v.push((y.exp(), fr(self.exp)));
        v
    }
    /// a' ⪯ a (plaintext check, used by honest parties and by the test oracle)
    pub fn attenuates(&self, p: &Attrs) -> bool {
        (0..self.scope.len()).all(|c| !self.scope[c] || p.scope[c])
            && self.budget <= p.budget && self.lo >= p.lo && self.k <= p.k && self.lo < self.k && self.exp <= p.exp
            && self.depth == p.depth + 1 && self.depth <= MAXDEPTH
            && self.anc == [p.id, p.anc[0], p.anc[1], p.anc[2]] && self.uid == p.uid
    }
    /// Honest child attributes derived from a parent; the child receives the top `size` counters of the parent's interval.
    pub fn child_of(p: &Attrs, scope: Vec<bool>, budget: u64, size: u64, exp: u64) -> Attrs {
        let size = size.min(p.k - p.lo);
        Self::child_range(p, scope, budget, p.k - size, p.k, exp)
    }
    /// Child attributes with an explicit counter interval [lo, hi) inside the parent's.
    pub fn child_range(p: &Attrs, scope: Vec<bool>, budget: u64, lo: u64, hi: u64, exp: u64) -> Attrs {
        Attrs { id: 0, anc: [p.id, p.anc[0], p.anc[1], p.anc[2]], depth: p.depth + 1, scope, budget, lo, k: hi, exp, uid: p.uid }
    }
}

#[derive(Clone, Debug, serde::Serialize)]
pub struct Invocation {
    pub tool: String, // authenticated tool identity: "<server origin>|<tool name>"
    pub call: String, // canonical JSON (RFC 8785) of tools/call
    pub class: usize,
    pub amt: u64,
    pub cur: String,   // ISO 4217 currency of `amt` (minor units)
    pub epoch: u64,
    pub t: u64,
    pub nonce: String, // issued by the tool
}
impl Invocation {
    pub fn ctx(&self) -> Vec<u8> {
        let mut h = Sha256::new();
        h.update(b"MM-v2-invocation");
        h.update(serde_json::to_vec(self).unwrap());
        h.finalize().to_vec()
    }
}

#[derive(Clone)]
pub struct Mandate {
    pub s: Fr,           // link secret (shared by the subtree)
    pub u: Fr,           // per-root tag t of the tree (signed in the uid slot; T = g^t is bound to the principal by its signature)
    pub a: Attrs,
    pub ver: u64,
    pub sig: SignatureG1<E>,
    pub nm: Vec<NonMembershipWitness<G1Affine>>, // 5 witnesses for id, anc1..4
}
impl Mandate {
    pub fn msgs(&self) -> Vec<Fr> {
        let y = self.a.lay();
        let mut m = vec![Fr::zero(); y.l()];
        m[I_S] = self.s;
        for (i, v) in self.a.msgs_public() { m[i] = v; }
        m[y.uid()] = self.u;
        m[y.ver()] = fr(self.ver);
        m
    }
    pub fn ids(&self) -> [u64; 5] { [self.a.id, self.a.anc[0], self.a.anc[1], self.a.anc[2], self.a.anc[3]] }
}

/// Public data held by every tool and by agents (no secret).
#[derive(Clone)]
pub struct Pub {
    pub y: Lay,
    pub sp: SignatureParamsG1<E>,
    pub ipk: PublicKeyG2<E>,
    pub ap: AccParams<E>,
    pub apk: AccPublicKey<E>,
    pub nmk: NonMembershipProvingKey<G1Affine>,
    pub bpp: BppParams<G1Affine>,
    pub g: G1Affine,
    pub esc_pk: G1Affine,
    pub X: [G1Affine; 3],
    pub accv: G1Affine,
    /// Previous accumulator values still accepted (grace window, most recent last; empty = revocation immediate).
    pub acc_window: Vec<G1Affine>,
    pub ver: u64,
}

pub struct Escrow { pub shares: [Fr; 3] } // each member keeps its own share (output of the DKG)

pub struct System {
    pub p: Pub,
    pub ikp: KeypairG2<E>,
    pub akp: AccKeypair<E>,
    pub acc: UniversalAccumulator<G1Affine>,
    pub init: InMemoryInitialElements<Fr>,
    pub state: InMemoryState<Fr>,
    pub esc: Escrow,
    pub seen_deleg: BTreeSet<Vec<u8>>, // issuer-side delegation pseudonyms
    pub revoked: Vec<Fr>,
    pub issued: BTreeSet<u64>,         // identifiers issued (for opening and uniqueness)
    pub registry: BTreeMap<u64, G1Affine>, // label -> g^u (registered long-term principal keys)
    /// Per-root tag bindings: ser(g^t) -> (label, Schnorr signature by the principal's key on (label, g^t)).
    /// Published by the issuer; Judge re-verifies the signature, so the issuer cannot forge a binding.
    pub bindings: BTreeMap<Vec<u8>, (u64, (Fr, Fr))>,
    /// Issuer clock: the current epoch (delegation requests for another epoch are refused).
    pub epoch: u64,
    /// ser(g^id) -> id for every issued identifier (Judge lookup).
    pub issued_g: BTreeMap<Vec<u8>, u64>,
    /// Number of previous accumulator values tools keep accepting after a revocation (0 = immediate).
    pub acc_grace: usize,
    /// issuer policy: roots per principal label (the Sybil boundary) and roots issued so far
    pub root_limit: u64,
    pub roots_per_label: BTreeMap<u64, u64>,
    /// Test harness only: principals' secrets (held by the principals in a deployment).
    pub principal_secret: BTreeMap<u64, Fr>,
    /// Revocation log: single-use nonces it issued (see `log_nonce` and `revoke_authorized`).
    pub log_nonces: BTreeSet<Vec<u8>>,
}

#[derive(Clone)]
pub struct Presentation {
    pub accv: G1Affine,  // accumulator value the proof was made against (must be current or within the grace window)
    pub nym: G1Affine,
    pub esc: Option<[G1Affine; 4]>, // (g^r1, g^t X^r1, g^r2, g^id X^r2): escrow of the per-root tag and of the mandate id
    pub proof: Proof<E>,
}
impl Presentation {
    pub fn size(&self) -> usize { self.to_bytes().len() }
}

#[derive(Default, Clone)]
pub struct Cheat {
    pub esc_u: Option<Fr>,
    pub esc_id: Option<u64>,
    pub acc_value: Option<G1Affine>,
    /// Malicious prover: build the proof for a weaker statement than the verifier's (amount lower bound 0).
    pub weaken_amount: bool,
    /// Malicious prover: expiry lower bound 0 instead of t.
    pub weaken_expiry: bool,
    /// Malicious prover: reveal this class bit instead of the invoked one.
    pub reveal_class: Option<usize>,
    /// Malicious prover: the quota statement is not tied to the signed k (k becomes a free witness).
    pub free_quota: Option<u64>,
}

pub struct Tool {
    pub name: String,
    pub seen: BTreeSet<(u64, Vec<u8>)>,
    pub require_escrow: bool,
    /// Deployment checks (None = not checked, for micro-benchmarks only): the tool's current epoch,
    /// its clock and tolerance (seconds), and the single-use nonces it issued.
    pub epoch: Option<u64>,
    pub clock: Option<(u64, u64)>,
    pub nonces: Option<BTreeSet<String>>,
}
impl Tool {
    pub fn new(name: &str, require_escrow: bool) -> Self { Tool { name: name.into(), seen: BTreeSet::new(), require_escrow, epoch: None, clock: None, nonces: None } }
    /// A tool that checks the epoch, the time and its own nonces.
    pub fn strict(name: &str, require_escrow: bool, epoch: u64, now: u64, tol: u64) -> Self {
        Tool { epoch: Some(epoch), clock: Some((now, tol)), nonces: Some(BTreeSet::new()), ..Self::new(name, require_escrow) }
    }
    /// Issues a fresh single-use nonce.
    pub fn issue_nonce(&mut self, rng: &mut StdRng) -> String {
        let mut b = [0u8; 16]; rng.fill_bytes(&mut b);
        let n: String = b.iter().map(|x| format!("{x:02x}")).collect();
        if let Some(ns) = self.nonces.as_mut() { ns.insert(n.clone()); }
        n
    }
    /// Moves the tool's clock (a new epoch clears the seen-set of the previous one only for memory; keys carry the epoch).
    pub fn set_clock(&mut self, epoch: u64, now: u64) {
        self.epoch = Some(epoch);
        if let Some((_, tol)) = self.clock { self.clock = Some((now, tol)); }
        self.seen.retain(|(e, _)| *e >= epoch);
    }
}

pub fn nym_base(tool: &str, epoch: u64) -> G1Affine { h2g_parts("MM-v2-nym-tool", &[tool.as_bytes(), &epoch.to_le_bytes()]) }
pub fn deleg_base(epoch: u64) -> G1Affine { h2g_parts("MM-v2-nym-delegation", &[&epoch.to_le_bytes()]) }
/// Dodis–Yampolskiy pseudonym B^{1/(s+j+1)}.
pub fn dy(base: &G1Affine, s: Fr, j: u64) -> G1Affine {
    let w = s + fr(j) + Fr::one();
    (base.into_group() * w.inverse().expect("s+j+1 != 0")).into_affine()
}

pub fn lagrange_at0(i: u64, jj: u64) -> (Fr, Fr) {
    let (xi, xj) = (fr(i), fr(jj));
    (xj / (xj - xi), xi / (xi - xj))
}

/// Adds the statements proving nym = base^{1/(s+j+1)} with hidden j in [lo, k).
/// `s_ref`, `lo_ref` and `k_ref` are witness references of s, lo and k; returns the next statement index.
fn add_dy(st: &mut Statements<E>, eqs: &mut Vec<Vec<(usize, usize)>>, p: &Pub, idx: usize, base: G1Affine, nym: G1Affine,
          s_ref: (usize, usize), lo_ref: (usize, usize), k_ref: (usize, usize)) -> Result<usize, String> { add_dy_opt(st, eqs, p, idx, base, nym, s_ref, lo_ref, Some(k_ref)) }
fn add_dy_opt(st: &mut Statements<E>, eqs: &mut Vec<Vec<(usize, usize)>>, p: &Pub, idx: usize, base: G1Affine, nym: G1Affine,
          s_ref: (usize, usize), lo_ref: (usize, usize), k_ref: Option<(usize, usize)>) -> Result<usize, String> {
    let g = p.g;
    let gneg = (-g.into_group()).into_affine();
    // idx: nym^w = base
    st.add(PedStmt::new_statement_from_params(vec![nym], base));
    // idx+1: g^w g^-s g^-j = g   (w = s + j + 1)
    st.add(PedStmt::new_statement_from_params(vec![g, gneg, gneg], g));
    // idx+2: g^d0 g^lo g^-j = g  (d0 = j - lo + 1)
    st.add(PedStmt::new_statement_from_params(vec![g, g, gneg], g));
    // idx+3: d0 in [1, 2^40)  =>  j >= lo
    st.add(BoundCheckBpp::new_statement_from_params(1, MAXV, p.bpp.clone()).map_err(|e| format!("{e:?}"))?);
    // idx+4: g^d g^j g^-k = g^-1  (d = k - j - 1)
    st.add(PedStmt::new_statement_from_params(vec![g, g, gneg], gneg));
    // idx+5: d in [0, 2^40)  =>  j < k
    st.add(BoundCheckBpp::new_statement_from_params(0, MAXV, p.bpp.clone()).map_err(|e| format!("{e:?}"))?);
    eqs.push(vec![(idx, 0), (idx + 1, 0)]);
    eqs.push(vec![s_ref, (idx + 1, 1)]);
    eqs.push(vec![(idx + 1, 2), (idx + 2, 2), (idx + 4, 1)]);
    eqs.push(vec![lo_ref, (idx + 2, 1)]);
    eqs.push(vec![(idx + 2, 0), (idx + 3, 0)]);
    if let Some(k_ref) = k_ref { eqs.push(vec![k_ref, (idx + 4, 2)]); }
    eqs.push(vec![(idx + 4, 0), (idx + 5, 0)]);
    Ok(idx + 6)
}
fn dy_witnesses(w: &mut Witnesses<E>, s: Fr, j: u64, lo: u64, k: u64) {
    let wv = s + fr(j) + Fr::one();
    w.add(Witness::PedersenCommitment(vec![wv]));
    w.add(Witness::PedersenCommitment(vec![wv, s, fr(j)]));
    let d0 = fr(j) - fr(lo) + Fr::one();
    w.add(Witness::PedersenCommitment(vec![d0, fr(lo), fr(j)]));
    w.add(Witness::BoundCheckBpp(d0));
    let d = fr(k) - fr(j) - Fr::one();
    w.add(Witness::PedersenCommitment(vec![d, fr(j), fr(k)]));
    w.add(Witness::BoundCheckBpp(d));
}
/// Merges equality lists that share a witness reference (proof_system expects disjoint sets).
fn merge_eqs(eqs: Vec<Vec<(usize, usize)>>, ms: &mut MetaStatements) {
    let mut sets: Vec<BTreeSet<(usize, usize)>> = vec![];
    for e in eqs {
        let mut cur: BTreeSet<(usize, usize)> = e.into_iter().collect();
        let mut rest = vec![];
        for s in sets.drain(..) { if s.intersection(&cur).next().is_some() { cur.extend(s); } else { rest.push(s); } }
        rest.push(cur);
        sets = rest;
    }
    for s in sets { ms.add_witness_equality(EqualWitnesses(s)); }
}

/// Statement groups of a presentation (for the cost breakdown in E1).
#[derive(Clone, Copy)]
pub struct Parts { pub dy: bool, pub ranges: bool, pub nm: bool, pub revealed: bool }
impl Parts { pub const ALL: Parts = Parts { dy: true, ranges: true, nm: true, revealed: false }; }
/// Pseudonym base of the revealed-counter variant (ablation only): nym = H(T, e, j)^s with j public.
pub fn nym_base_revealed(tool: &str, epoch: u64, j: u64) -> G1Affine { h2g_parts("MM-v2-nym-revealed", &[tool.as_bytes(), &epoch.to_le_bytes(), &j.to_le_bytes()]) }

impl Pub {
    /// Cost breakdown: prove and verify only the selected statement groups (BBS+ PoK always included).
    /// Returns (prove_ms, verify_ms, bytes).
    pub fn ablation(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, parts: Parts, escrow: bool) -> Result<(f64, f64, usize), String> {
        let j = m.a.lo + j;
        let msgs = m.msgs();
        let t0 = std::time::Instant::now();
        let nym = if parts.revealed { (nym_base_revealed(&inv.tool, inv.epoch, j).into_group() * m.s).into_affine() } else { dy(&nym_base(&inv.tool, inv.epoch), m.s, j) };
        let (r1, r2) = (Fr::rand(rng), Fr::rand(rng));
        let g = self.g.into_group();
        let esc = if escrow { Some([(g * r1).into_affine(), (g * m.u + self.esc_pk.into_group() * r1).into_affine(),
                                    (g * r2).into_affine(), (g * fr(m.a.id) + self.esc_pk.into_group() * r2).into_affine()]) } else { None };
        let (st, ms) = self.present_statements_parts_j(inv, &nym, &esc, true, self.accv, &Cheat::default(), parts, j)?;
        let mut w = Witnesses::new();
        let unrev: BTreeMap<usize, Fr> = msgs.iter().enumerate().filter(|(i, _)| *i != I_SCOPE + inv.class).map(|(i, v)| (i, *v)).collect();
        w.add(BbsWit::new_as_witness(m.sig.clone(), unrev));
        if parts.dy { dy_witnesses(&mut w, m.s, j, m.a.lo, m.a.k); }
        if parts.revealed {
            w.add(Witness::PedersenCommitment(vec![m.s]));
            let d0 = fr(j) - fr(m.a.lo) + Fr::one();
            w.add(Witness::PedersenCommitment(vec![d0, fr(m.a.lo)])); w.add(Witness::BoundCheckBpp(d0));
            let d = fr(m.a.k) - fr(j) - Fr::one();
            w.add(Witness::PedersenCommitment(vec![d, fr(m.a.k)])); w.add(Witness::BoundCheckBpp(d));
        }
        if parts.ranges { w.add(Witness::BoundCheckBpp(msgs[self.y.budget()])); w.add(Witness::BoundCheckBpp(msgs[self.y.exp()])); }
        if parts.nm { for (i, id) in m.ids().iter().enumerate() { w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: m.nm[i].clone() })); } }
        if escrow { w.add(Witness::PedersenCommitment(vec![r1])); w.add(Witness::PedersenCommitment(vec![m.u, r1]));
                    w.add(Witness::PedersenCommitment(vec![r2])); w.add(Witness::PedersenCommitment(vec![fr(m.a.id), r2])); }
        let spec = ProofSpec::new(st, ms, vec![], Some(inv.ctx()));
        let proof = Proof::new::<StdRng, Blake2b512>(rng, spec, w, Some(inv.nonce.as_bytes().to_vec()), Default::default()).map_err(|e| format!("{e:?}"))?.0;
        let tp = t0.elapsed().as_secs_f64() * 1e3;
        let bytes = Presentation { accv: self.accv, nym, esc, proof: proof.clone() }.size();
        let t1 = std::time::Instant::now();
        let (st, ms) = self.present_statements_parts_j(inv, &nym, &esc, false, self.accv, &Cheat::default(), parts, j)?;
        proof.verify::<StdRng, Blake2b512>(rng, ProofSpec::new(st, ms, vec![], Some(inv.ctx())), Some(inv.nonce.as_bytes().to_vec()), Default::default()).map_err(|e| format!("{e:?}"))?;
        Ok((tp, t1.elapsed().as_secs_f64() * 1e3, bytes))
    }
    /// Statements of a presentation. Witness layout (statement, index).
    fn present_statements(&self, inv: &Invocation, nym: &G1Affine, esc: &Option<[G1Affine; 4]>, prover: bool, accv: G1Affine, weaken: &Cheat)
        -> Result<(Statements<E>, MetaStatements), String> { self.present_statements_parts(inv, nym, esc, prover, accv, weaken, Parts::ALL) }
    fn present_statements_parts(&self, inv: &Invocation, nym: &G1Affine, esc: &Option<[G1Affine; 4]>, prover: bool, accv: G1Affine, weaken: &Cheat, parts: Parts)
        -> Result<(Statements<E>, MetaStatements), String> { self.present_statements_parts_j(inv, nym, esc, prover, accv, weaken, parts, 0) }
    fn present_statements_parts_j(&self, inv: &Invocation, nym: &G1Affine, esc: &Option<[G1Affine; 4]>, prover: bool, accv: G1Affine, weaken: &Cheat, parts: Parts, rj: u64)
        -> Result<(Statements<E>, MetaStatements), String> {
        let y = self.y;
        let mut st = Statements::<E>::new();
        let mut eqs: Vec<Vec<(usize, usize)>> = vec![];
        let mut rev = BTreeMap::new();
        rev.insert(I_SCOPE + weaken.reveal_class.unwrap_or(inv.class), Fr::one());
        if prover { st.add(BbsP::new_statement_from_params(self.sp.clone(), rev)); }
        else { st.add(BbsV::new_statement_from_params(self.sp.clone(), self.ipk.clone(), rev)); }
        // 1..5: pseudonym with hidden counter j in [0, k)
        let mut idx = 1;
        if parts.dy { idx = add_dy_opt(&mut st, &mut eqs, self, 1, nym_base(&inv.tool, inv.epoch), *nym, (0, I_S), (0, y.lo()), if weaken.free_quota.is_some() { None } else { Some((0, y.k())) })?; }
        if parts.revealed {
            // ablation: revealed counter j (k-TAA style): nym = H(T,e,j)^s, lo <= j < k proved on the hidden lo and k
            let g = self.g; let gneg = (-g.into_group()).into_affine();
            st.add(PedStmt::new_statement_from_params(vec![nym_base_revealed(&inv.tool, inv.epoch, rj)], *nym));
            eqs.push(vec![(0, I_S), (idx, 0)]);
            let gj1 = (g.into_group() * (fr(rj) + Fr::one())).into_affine();
            st.add(PedStmt::new_statement_from_params(vec![g, g], gj1));                 // d0 + lo = j + 1
            st.add(BoundCheckBpp::new_statement_from_params(1, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            eqs.push(vec![(idx + 1, 0), (idx + 2, 0)]); eqs.push(vec![(0, y.lo()), (idx + 1, 1)]);
            let gmj1 = (gneg.into_group() * (fr(rj) + Fr::one())).into_affine();
            st.add(PedStmt::new_statement_from_params(vec![g, gneg], gmj1));             // d - k = -(j + 1)
            st.add(BoundCheckBpp::new_statement_from_params(0, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            eqs.push(vec![(idx + 3, 0), (idx + 4, 0)]); eqs.push(vec![(0, y.k()), (idx + 3, 1)]);
            idx += 5;
        }
        // 6, 7: budget >= amt, exp >= t
        let amt_lo = if weaken.weaken_amount { 0 } else { inv.amt };
        let t_lo = if weaken.weaken_expiry { 0 } else { inv.t };
        for (mi, lo) in [(y.budget(), amt_lo), (y.exp(), t_lo)] {
            if !parts.ranges { break; }
            st.add(BoundCheckBpp::new_statement_from_params(lo, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            eqs.push(vec![(0, mi), (idx, 0)]);
            idx += 1;
        }
        // 8..12: non-membership of id and ancestors
        for i in 0..5 {
            if !parts.nm { break; }
            st.add(NonMemStmt::new_statement_from_params(self.ap.clone(), self.apk.clone(), self.nmk.clone(), accv));
            eqs.push(vec![(0, I_ID + i), (idx, 0)]);
            idx += 1;
        }
        // optional escrow: (g^r1, g^u pk^r1), (g^r2, g^id pk^r2)
        if let Some(c) = esc {
            st.add(PedStmt::new_statement_from_params(vec![self.g], c[0]));
            st.add(PedStmt::new_statement_from_params(vec![self.g, self.esc_pk], c[1]));
            st.add(PedStmt::new_statement_from_params(vec![self.g], c[2]));
            st.add(PedStmt::new_statement_from_params(vec![self.g, self.esc_pk], c[3]));
            eqs.push(vec![(0, y.uid()), (idx + 1, 0)]);
            eqs.push(vec![(idx, 0), (idx + 1, 1)]);
            eqs.push(vec![(0, I_ID), (idx + 3, 0)]);
            eqs.push(vec![(idx + 2, 0), (idx + 3, 1)]);
        }
        let mut ms = MetaStatements::new();
        merge_eqs(eqs, &mut ms);
        Ok((st, ms))
    }

    /// Agent: present mandate `m` for invocation `inv` with (hidden) counter j < k.
    pub fn present(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, escrow: bool) -> Result<Presentation, String> {
        self.present_cheat(rng, m, inv, j, escrow, &Cheat::default())
    }
    /// `j` is the offset of the counter inside the mandate's interval: the counter used is lo + j.
    pub fn present_cheat(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, escrow: bool, ch: &Cheat) -> Result<Presentation, String> {
        let j = m.a.lo + j;
        let msgs = m.msgs();
        let nym = dy(&nym_base(&inv.tool, inv.epoch), m.s, j);
        let mut esc_w = None;
        let esc = if escrow {
            let (r1, r2) = (Fr::rand(rng), Fr::rand(rng));
            let u = ch.esc_u.unwrap_or(m.u);
            let id = fr(ch.esc_id.unwrap_or(m.a.id));
            let g = self.g.into_group();
            let c = [(g * r1).into_affine(), (g * u + self.esc_pk.into_group() * r1).into_affine(),
                     (g * r2).into_affine(), (g * id + self.esc_pk.into_group() * r2).into_affine()];
            esc_w = Some((r1, r2, u, id));
            Some(c)
        } else { None };
        let (st, ms) = self.present_statements(inv, &nym, &esc, true, ch.acc_value.unwrap_or(self.accv), ch)?;
        let mut w = Witnesses::new();
        let rc = ch.reveal_class.unwrap_or(inv.class);
        let unrev: BTreeMap<usize, Fr> = msgs.iter().enumerate().filter(|(i, _)| *i != I_SCOPE + rc).map(|(i, v)| (i, *v)).collect();
        w.add(BbsWit::new_as_witness(m.sig.clone(), unrev));
        dy_witnesses(&mut w, m.s, j, m.a.lo, ch.free_quota.unwrap_or(m.a.k));
        w.add(Witness::BoundCheckBpp(msgs[self.y.budget()]));
        w.add(Witness::BoundCheckBpp(msgs[self.y.exp()]));
        for (i, id) in m.ids().iter().enumerate() {
            w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: m.nm[i].clone() }));
        }
        if let Some((r1, r2, u, id)) = esc_w {
            w.add(Witness::PedersenCommitment(vec![r1]));
            w.add(Witness::PedersenCommitment(vec![u, r1]));
            w.add(Witness::PedersenCommitment(vec![r2]));
            w.add(Witness::PedersenCommitment(vec![id, r2]));
        }
        let spec = ProofSpec::new(st, ms, vec![], Some(inv.ctx()));
        let nonce = Some(inv.nonce.as_bytes().to_vec());
        let proof = guard(|| Proof::new::<StdRng, Blake2b512>(rng, spec, w, nonce, Default::default()).map_err(|e| format!("prove: {e:?}")))?.0;
        Ok(Presentation { accv: ch.acc_value.unwrap_or(self.accv), nym, esc, proof })
    }

    /// Tool: verify and record. Uses only public data.
    /// Wallet check: every non-membership witness of the mandate verifies against the current accumulator value.
    /// A wallet that holds a non-revoked mandate whose witness fails treats it as issuer misbehaviour.
    pub fn witnesses_valid(&self, m: &Mandate) -> bool {
        m.nm.len() == 5 && m.ids().iter().zip(m.nm.iter()).all(|(id, w)|
            UniversalAccumulator::<G1Affine>::verify_non_membership_given_accumulated(&self.accv, &fr(*id), w, &self.apk, &self.ap))
    }

    pub fn verify(&self, rng: &mut StdRng, tool: &mut Tool, inv: &Invocation, p: &Presentation) -> Result<(), String> {
        if inv.tool != tool.name { return Err("wrong tool".into()); }
        if inv.class >= self.y.n { return Err("class index out of range".into()); }
        if tool.require_escrow && p.esc.is_none() { return Err("escrow required".into()); }
        if let Some(e) = tool.epoch { if inv.epoch != e { return Err("wrong epoch".into()); } }
        if let Some((now, tol)) = tool.clock { if inv.t + tol < now || inv.t > now + tol { return Err("time out of tolerance".into()); } }
        if let Some(ns) = tool.nonces.as_mut() { if !ns.remove(&inv.nonce) { return Err("unknown or already used tool nonce".into()); } }
        if !(p.accv == self.accv || self.acc_window.contains(&p.accv)) { return Err("accumulator value not accepted".into()); }
        // reserve the pseudonym before verifying (no check-then-act race under parallel verification); release on failure
        let key = (inv.epoch, { let mut b = vec![]; ser(&p.nym, &mut b); b });
        if !tool.seen.insert(key.clone()) { return Err("pseudonym replay (counter reused)".into()); }
        let r = (|| {
            let (st, ms) = self.present_statements(inv, &p.nym, &p.esc, false, p.accv, &Cheat::default())?;
            let spec = ProofSpec::new(st, ms, vec![], Some(inv.ctx()));
            guard(|| p.proof.clone().verify::<StdRng, Blake2b512>(rng, spec, Some(inv.nonce.as_bytes().to_vec()), Default::default())
                .map_err(|e| format!("verify: {e:?}")))
        })();
        if r.is_err() { tool.seen.remove(&key); }
        r
    }

    /// Root issuance request: commits to (s, t) and proves t = log_g(T) for the per-root tag T.
    fn root_statements(&self, C: &G1Affine, T: &G1Affine) -> (Statements<E>, MetaStatements) {
        let mut st = Statements::<E>::new();
        st.add(PedStmt::new_statement_from_params(vec![self.sp.h_0, self.sp.h[I_S], self.sp.h[self.y.uid()]], *C));
        st.add(PedStmt::new_statement_from_params(vec![self.g], *T));
        let mut ms = MetaStatements::new();
        ms.add_witness_equality(eq(&[(0, 2), (1, 0)]));
        (st, ms)
    }

    /// Delegation statements (parent proves to the issuer).
    fn deleg_statements(&self, Cp: &G1Affine, nymD: &G1Affine, epoch: u64, prover: bool, omit_child_ranges: bool, rebind: Option<usize>) -> Result<(Statements<E>, MetaStatements), String> {
        let rb = |mi: usize| rebind == Some(mi); // prover: malicious re-binding; verifier: debug issuer without this relation (positive control)
        let y = self.y;
        let mut st = Statements::<E>::new();
        let mut eqs: Vec<Vec<(usize, usize)>> = vec![];
        if prover { st.add(BbsP::new_statement_from_params(self.sp.clone(), BTreeMap::new())); }
        else { st.add(BbsV::new_statement_from_params(self.sp.clone(), self.ipk.clone(), BTreeMap::new())); }
        // 1..5 non-membership of parent's id and ancestors
        for i in 0..5 {
            st.add(NonMemStmt::new_statement_from_params(self.ap.clone(), self.apk.clone(), self.nmk.clone(), self.accv));
            eqs.push(vec![(0, I_ID + i), (1 + i, 0)]);
        }
        // 6: commitment to the child's messages except id and ver: bases h0, h[s], h[anc..uid]
        let cidx = y.deleg_committed();
        let mut bases = vec![self.sp.h_0];
        for i in &cidx { bases.push(self.sp.h[*i]); }
        st.add(PedStmt::new_statement_from_params(bases, *Cp));
        let cw = |mi: usize| 1 + cidx.iter().position(|x| *x == mi).unwrap();
        // inheritance: s' = s, anc'_1 = id, anc'_{i+1} = anc_i, u' = u
        eqs.push(vec![(0, I_S), (6, cw(I_S))]);
        eqs.push(vec![(0, I_ID), (6, cw(I_ANC))]);
        for i in 0..3 { eqs.push(vec![(0, I_ANC + i), (6, cw(I_ANC + i + 1))]); }
        eqs.push(vec![(0, y.uid()), (6, cw(y.uid()))]);
        let g = self.g;
        let gneg = (-g.into_group()).into_affine();
        let mut idx = 7;
        // depth' - depth = 1 ; depth' in [1, 5)
        st.add(PedStmt::new_statement_from_params(vec![g, gneg], g));
        if rb(I_DEPTH) { eqs.push(vec![(idx, 0), (idx + 1, 0)]); } else { eqs.push(vec![(6, cw(I_DEPTH)), (idx, 0), (idx + 1, 0)]); }
        eqs.push(vec![(0, I_DEPTH), (idx, 1)]);
        st.add(BoundCheckBpp::new_statement_from_params(1, MAXDEPTH + 1, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
        idx += 2;
        // numeric attenuation: d + x' - x = 1, d in [1, 2^40); scope: d_c + b'_c - b_c = 1, d_c in [1, 3)
        let mut items: Vec<(usize, u64)> = vec![(y.budget(), MAXV), (y.k(), MAXV), (y.exp(), MAXV)];
        for c in 0..y.n { items.push((I_SCOPE + c, 3)); }
        for (mi, hi) in items {
            st.add(PedStmt::new_statement_from_params(vec![g, g, gneg], g));
            eqs.push(vec![(idx, 0), (idx + 1, 0)]);
            if !rb(mi) { eqs.push(vec![(6, cw(mi)), (idx, 1)]); }
            eqs.push(vec![(0, mi), (idx, 2)]);
            st.add(BoundCheckBpp::new_statement_from_params(1, hi, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            idx += 2;
        }
        // counter interval: lo' >= lo, i.e. d + lo - lo' = 1 with d in [1, 2^40)
        st.add(PedStmt::new_statement_from_params(vec![g, g, gneg], g));
        eqs.push(vec![(idx, 0), (idx + 1, 0)]);
        eqs.push(vec![(0, y.lo()), (idx, 1)]);
        if !rb(y.lo()) { eqs.push(vec![(6, cw(y.lo())), (idx, 2)]); }
        st.add(BoundCheckBpp::new_statement_from_params(1, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
        idx += 2;
        // delegation pseudonym with hidden counter (same quota space as the parent's calls)
        idx = add_dy_opt(&mut st, &mut eqs, self, idx, deleg_base(epoch), *nymD, (0, I_S), (0, y.lo()), if rb(REBIND_COUNTER) { None } else { Some((0, y.k())) })?;
        // child's own numeric values in [0, 2^40): rules out wrap-around modulo p
        // (malicious-prover test: the same range statements bound to the PARENT's values instead of the child's)
        for mi in [y.budget(), y.lo(), y.k(), y.exp()] {
            st.add(BoundCheckBpp::new_statement_from_params(0, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            if omit_child_ranges { eqs.push(vec![(0, mi), (idx, 0)]); } else { eqs.push(vec![(6, cw(mi)), (idx, 0)]); }
            idx += 1;
        }
        let mut ms = MetaStatements::new();
        merge_eqs(eqs, &mut ms);
        Ok((st, ms))
    }

    /// Parent side of a delegation session bound to the issuer's nonce. The child receives s and u from the parent.
    pub fn deleg_request(&self, rng: &mut StdRng, parent: &Mandate, child: &Attrs, epoch: u64, j: u64, issuer_nonce: &[u8])
        -> Result<(DelegReq, DelegSecret), String> { self.deleg_request_opt(rng, parent, child, epoch, j, issuer_nonce, DelegCheat::default()) }

    pub fn deleg_request_opt(&self, rng: &mut StdRng, parent: &Mandate, child: &Attrs, epoch: u64, j: u64, issuer_nonce: &[u8], ch: DelegCheat)
        -> Result<(DelegReq, DelegSecret), String> {
        let j = parent.a.lo + j; // offset inside the parent's counter interval
        let y = self.y;
        let r2 = Fr::rand(rng);
        let mut cmv: BTreeMap<usize, Fr> = child.msgs_public().into_iter().filter(|(i, _)| *i != I_ID).collect();
        cmv.insert(I_S, parent.s);
        cmv.insert(y.uid(), parent.u);
        if ch.wrap_budget { cmv.insert(y.budget(), fr(parent.a.budget) - fr(parent.a.budget + 5) + Fr::one()); }
        let cidx = y.deleg_committed();
        let Cp = self.sp.commit_to_messages(cidx.iter().map(|i| (*i, &cmv[i])).collect::<Vec<_>>(), &r2).map_err(|e| format!("{e:?}"))?;
        let ctx = deleg_ctx(issuer_nonce, &Cp);
        let nymD = dy(&deleg_base(epoch), parent.s, j);
        let pf = self.deleg_proof(rng, parent, &cmv, r2, &Cp, &nymD, epoch, j, &ctx, ch.malicious_omit_child_ranges, ch.rebind)?;
        Ok((DelegReq { Cp, nymD, epoch, pf }, DelegSecret { r2, child: child.clone(), s: parent.s, u: parent.u }))
    }

    fn deleg_proof(&self, rng: &mut StdRng, p: &Mandate, cmv: &BTreeMap<usize, Fr>, r2: Fr, Cp: &G1Affine, nymD: &G1Affine, epoch: u64, j: u64, ctx: &[u8], omit: bool, rebind: Option<usize>) -> Result<Proof<E>, String> {
        let y = self.y;
        let (st, ms) = self.deleg_statements(Cp, nymD, epoch, true, omit, rebind)?;
        let rb = |mi: usize| rebind == Some(mi);
        let pm = p.msgs();
        let mut w = Witnesses::new();
        w.add(BbsWit::new_as_witness(p.sig.clone(), pm.iter().enumerate().map(|(i, v)| (i, *v)).collect()));
        for (i, id) in p.ids().iter().enumerate() {
            w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: p.nm[i].clone() }));
        }
        let mut cw = vec![r2];
        for i in y.deleg_committed() { cw.push(cmv[&i]); }
        w.add(Witness::PedersenCommitment(cw));
        let dd = if rb(I_DEPTH) { pm[I_DEPTH] + Fr::one() } else { cmv[&I_DEPTH] };
        w.add(Witness::PedersenCommitment(vec![dd, pm[I_DEPTH]]));
        w.add(Witness::BoundCheckBpp(dd));
        let mut items: Vec<usize> = vec![y.budget(), y.k(), y.exp()];
        for cc in 0..y.n { items.push(I_SCOPE + cc); }
        for mi in items {
            let cv = if rb(mi) { pm[mi] } else { cmv[&mi] };
            let d = pm[mi] - cv + Fr::one();
            w.add(Witness::PedersenCommitment(vec![d, cv, pm[mi]]));
            w.add(Witness::BoundCheckBpp(d));
        }
        { let cl = if rb(y.lo()) { pm[y.lo()] } else { cmv[&y.lo()] };
          let d = cl - pm[y.lo()] + Fr::one();
          w.add(Witness::PedersenCommitment(vec![d, pm[y.lo()], cl]));
          w.add(Witness::BoundCheckBpp(d)); }
        dy_witnesses(&mut w, p.s, j, p.a.lo, if rb(REBIND_COUNTER) { j + 1 } else { p.a.k });
        for mi in [y.budget(), y.lo(), y.k(), y.exp()] { w.add(Witness::BoundCheckBpp(if omit { pm[mi] } else { cmv[&mi] })); }
        let spec = ProofSpec::new(st, ms, vec![], Some(ctx.to_vec()));
        Ok(guard(|| Proof::new::<StdRng, Blake2b512>(rng, spec, w, None, Default::default()).map_err(|e| format!("deleg prove: {e:?}")))?.0)
    }

    /// Positive control for the malicious-delegator attacks: an issuer that does NOT check attenuation relation `rebind`.
    /// A malicious delegation re-bound on that relation must be ACCEPTED here and rejected by `deleg_verify`.
    pub fn deleg_verify_without(&self, rng: &mut StdRng, q: &DelegReq, issuer_nonce: &[u8], rebind: usize) -> Result<(), String> {
        let ctx = deleg_ctx(issuer_nonce, &q.Cp);
        let (st, ms) = self.deleg_statements(&q.Cp, &q.nymD, q.epoch, false, false, Some(rebind))?;
        let spec = ProofSpec::new(st, ms, vec![], Some(ctx.to_vec()));
        guard(|| q.pf.clone().verify::<StdRng, Blake2b512>(rng, spec, None, Default::default()).map_err(|e| format!("deleg verify: {e:?}")))
    }

    fn deleg_verify(&self, rng: &mut StdRng, q: &DelegReq, ctx: &[u8]) -> Result<(), String> {
        let (st, ms) = self.deleg_statements(&q.Cp, &q.nymD, q.epoch, false, false, None)?;
        let spec = ProofSpec::new(st, ms, vec![], Some(ctx.to_vec()));
        guard(|| q.pf.clone().verify::<StdRng, Blake2b512>(rng, spec, None, Default::default()).map_err(|e| format!("deleg verify: {e:?}")))
    }

    /// Escrow: member i's decryption share of c (c1 or c3) with a Chaum–Pedersen proof.
    pub fn judge_share(&self, i: usize, c: &G1Affine, D: &G1Affine, pf: &(Fr, Fr)) -> bool {
        let (ch, z) = *pf;
        let a1 = (self.g.into_group() * z - self.X[i].into_group() * ch).into_affine();
        let a2 = (c.into_group() * z - D.into_group() * ch).into_affine();
        cp_challenge(&self.g, c, &self.X[i], D, &a1, &a2) == ch
    }
    /// Combines two shares (0-based member indices): returns c_b / c_a^x.
    pub fn open_pair(&self, cb: &G1Affine, s: [(usize, G1Affine); 2]) -> G1Affine {
        let (l0, l1) = lagrange_at0(s[0].0 as u64 + 1, s[1].0 as u64 + 1);
        let k = s[0].1.into_group() * l0 + s[1].1.into_group() * l1;
        (cb.into_group() - k).into_affine()
    }

    pub fn to_bytes(&self) -> Vec<u8> {
        let mut b = vec![];
        b.extend_from_slice(&(self.y.n as u64).to_le_bytes());
        // signature, accumulator and range-proof parameters and g are derived from public labels and not shipped
        ser(&self.ipk, &mut b); ser(&self.apk, &mut b); ser(&self.esc_pk, &mut b);
        for x in &self.X { ser(x, &mut b); }
        ser(&self.accv, &mut b);
        b.extend_from_slice(&(self.acc_window.len() as u64).to_le_bytes());
        for v in &self.acc_window { ser(v, &mut b); }
        b.extend_from_slice(&self.ver.to_le_bytes());
        b
    }
    pub fn from_bytes(b: &[u8]) -> Result<Self, String> {
        let mut rd = b;
        let n = u64::from_le_bytes(rd[..8].try_into().map_err(|_| "short")?) as usize; rd = &rd[8..];
        macro_rules! de { ($t:ty) => { <$t>::deserialize_compressed(&mut rd).map_err(|e| e.to_string())? } }
        if n == 0 || n > 64 { return Err("bad layout".into()); }
        let (sp, ap, nmk, bpp) = public_params(Lay { n });
        let g = h2g(b"g");
        let ipk = de!(PublicKeyG2<E>); let apk = de!(AccPublicKey<E>); let esc_pk = de!(G1Affine);
        if ipk.0.is_zero() || apk.0.is_zero() || esc_pk.is_zero() { return Err("degenerate public key".into()); }
        let X = [de!(G1Affine), de!(G1Affine), de!(G1Affine)];
        let accv = de!(G1Affine);
        let nw = u64::from_le_bytes(rd.get(..8).ok_or("short")?.try_into().map_err(|_| "short")?) as usize; rd = &rd[8..];
        if nw > 64 { return Err("window too long".into()); }
        let mut acc_window = vec![]; for _ in 0..nw { acc_window.push(de!(G1Affine)); }
        let ver = u64::from_le_bytes(rd.get(..8).ok_or("short")?.try_into().map_err(|_| "short")?);
        if rd.len() != 8 { return Err("trailing bytes".into()); }
        Ok(Pub { y: Lay { n }, sp, ipk, ap, apk, nmk, bpp, g, esc_pk, X, accv, acc_window, ver })
    }
}

impl System {
    /// Setup with an accumulator able to hold `max_rev` revoked ids.
    pub fn setup(rng: &mut StdRng, max_rev: u64) -> Self { Self::setup_n(rng, max_rev, NCLS) }
    pub fn setup_n(rng: &mut StdRng, max_rev: u64, n: usize) -> Self {
        let y = Lay { n };
        let sp = SignatureParamsG1::<E>::new::<Blake2b512>(b"MaskedMandates-v2-BBS+", y.l() as u32);
        let ikp = KeypairG2::<E>::generate_using_rng(rng, &sp);
        // Public parameters derived by hashing public labels: nobody (including the issuer) knows discrete-log
        // relations between them. A trapdoored accumulator proving key would let its author strip the
        // randomisation of non-membership proofs and link or de-anonymise presentations.
        let (sp_, ap, nmk, bpp) = public_params(y);
        let _ = sp_;
        let akp = AccKeypair::<E>::generate_using_rng(rng, &ap);
        let mut init = InMemoryInitialElements::new();
        let acc = UniversalAccumulator::initialize_with_all_random(rng, &ap, max_rev, &akp.secret_key, &mut init);
        let g = h2g(b"g");
        let (esc_pk, X, shares) = dkg_2of3(rng, &g).expect("DKG");
        let p = Pub { y, sp, ipk: ikp.public_key.clone(), ap, apk: akp.public_key.clone(), nmk, bpp, g, esc_pk, X, accv: *acc.value(), acc_window: vec![], ver: 1 };
        System { p, ikp, akp, acc, init, state: InMemoryState::new(), esc: Escrow { shares },
                 seen_deleg: BTreeSet::new(), revoked: vec![], issued: BTreeSet::new(), registry: BTreeMap::new(), principal_secret: BTreeMap::new(),
                 bindings: BTreeMap::new(), epoch: 0, issued_g: BTreeMap::new(), acc_grace: 0, root_limit: u64::MAX, roots_per_label: BTreeMap::new(),
                 log_nonces: BTreeSet::new() }
    }

    pub fn nm_witness(&self, id: u64) -> Option<NonMembershipWitness<G1Affine>> {
        self.acc.get_non_membership_witness(&fr(id), &self.akp.secret_key, &self.state, &self.p.ap).ok()
    }
    fn fresh_id(&mut self, rng: &mut StdRng) -> u64 {
        loop { let x = rng.next_u64() >> 1; if x != 0 && !self.issued.contains(&x) && !self.revoked.contains(&fr(x)) {
            self.issued.insert(x);
            let mut b = vec![]; ser(&(self.p.g.into_group() * fr(x)).into_affine(), &mut b); self.issued_g.insert(b, x);
            return x; } }
    }
    /// Registers a principal: the principal draws u and registers g^u under `label` (harness keeps u).
    pub fn register(&mut self, rng: &mut StdRng, label: u64) -> Fr {
        if let Some(u) = self.principal_secret.get(&label) { return *u; }
        let u = Fr::rand(rng);
        let pk = (self.p.g.into_group() * u).into_affine();
        assert!(!self.registry.values().any(|x| *x == pk), "duplicate principal key");
        self.registry.insert(label, pk);
        self.principal_secret.insert(label, u);
        u
    }

    /// Root issuance for principal `a.uid`. The wallet draws (s, t), commits to them, proves t = log_g(T) and signs (label, T) with u_P;
    /// the issuer checks the binding under the registered key, the layout, the bounds and Q, chooses id and blind-signs.
    pub fn issue_root(&mut self, rng: &mut StdRng, a: &Attrs) -> Result<Mandate, String> {
        let u = self.register(rng, a.uid);
        self.issue_root_with(rng, a, u)
    }
    pub fn issue_root_with(&mut self, rng: &mut StdRng, a: &Attrs, u: Fr) -> Result<Mandate, String> {
        let y = self.p.y;
        let issuer_nonce = { let mut b = [0u8; 16]; rng.fill_bytes(&mut b); b.to_vec() };
        // principal side: a fresh per-root tag t (signed as the uid attribute); u never leaves the principal
        let s = Fr::rand(rng);
        let t = Fr::rand(rng);
        let r = Fr::rand(rng);
        let T = (self.p.g.into_group() * t).into_affine();
        let binding = schnorr_sign(rng, &self.p.g, u, &binding_msg(a.uid, &T));
        let C = self.p.sp.commit_to_messages(vec![(I_S, &s), (y.uid(), &t)], &r).map_err(|e| format!("{e:?}"))?;
        let ctx = root_ctx(&issuer_nonce, &C, &T);
        let (st, ms) = self.p.root_statements(&C, &T);
        let mut w = Witnesses::new();
        w.add(Witness::PedersenCommitment(vec![r, s, t]));
        w.add(Witness::PedersenCommitment(vec![t]));
        let pf = Proof::new::<StdRng, Blake2b512>(rng, ProofSpec::new(st, ms, vec![], Some(ctx.clone())), w, None, Default::default()).map_err(|e| format!("{e:?}"))?.0;
        // issuer side (after authenticating the principal by the domain's ordinary means)
        self.root_issue(rng, a, &C, &T, binding, &pf, &issuer_nonce).map(|(blind, a)| {
            let sig = blind.unblind(&r);
            Mandate { s, u: t, a, ver: self.p.ver, sig, nm: vec![] }
        }).and_then(|mut m| {
            m.sig.verify(&m.msgs(), self.ikp.public_key.clone(), self.p.sp.clone()).map_err(|e| format!("root sig: {e:?}"))?;
            m.nm = m.ids().iter().map(|id| self.nm_witness(*id).ok_or("nm witness")).collect::<Result<_, _>>()?;
            if !self.p.witnesses_valid(&m) { return Err("wallet: invalid non-membership witness from the issuer".into()); }
            Ok(m)
        })
    }
    /// Issuer side of IssueRoot: checks the proof of the committed tag, the principal's binding signature, the bounds;
    /// records the binding; chooses id; blind-signs.
    pub fn root_issue(&mut self, rng: &mut StdRng, a: &Attrs, C: &G1Affine, T: &G1Affine, binding: (Fr, Fr), pf: &Proof<E>, issuer_nonce: &[u8])
        -> Result<(SignatureG1<E>, Attrs), String> {
        let y = self.p.y;
        let ctx = root_ctx(issuer_nonce, C, T);
        let (st, ms) = self.p.root_statements(C, T);
        guard(|| pf.clone().verify::<StdRng, Blake2b512>(rng, ProofSpec::new(st, ms, vec![], Some(ctx)), None, Default::default()).map_err(|e| format!("root pok: {e:?}")))?;
        let pk = *self.registry.get(&a.uid).ok_or("root: no principal registered under this label")?;
        if !schnorr_verify(&self.p.g, &pk, &binding_msg(a.uid, T), binding) { return Err("root: binding signature invalid".into()); }
        let key = { let mut b = vec![]; ser(T, &mut b); b };
        if self.bindings.contains_key(&key) || T.is_zero() { return Err("root: tag already bound".into()); }
        if a.scope.len() != y.n { return Err("root: attribute layout differs from the issuer's".into()); }
        if a.depth != 0 || a.anc != [0; 4] { return Err("root: bad public attributes".into()); }
        if *self.roots_per_label.get(&a.uid).unwrap_or(&0) >= self.root_limit { return Err("root: per-principal root limit reached".into()); }
        if a.budget >= MAXV || a.k >= MAXV || a.exp >= MAXV || a.lo >= a.k { return Err("root: numeric attribute out of range".into()); }
        if a.k - a.lo > QMAX { return Err("root: counter interval wider than the issuer's bound Q".into()); }
        let mut a = a.clone();
        a.id = self.fresh_id(rng);
        let mut unc: BTreeMap<usize, Fr> = a.msgs_public().into_iter().collect();
        unc.insert(y.ver(), fr(self.p.ver));
        let expected: Vec<usize> = (0..y.l()).filter(|i| *i != I_S && *i != y.uid()).collect();
        if unc.keys().cloned().collect::<Vec<_>>() != expected { return Err("root: signed index set differs from the issuer's layout".into()); }
        let blind = SignatureG1::<E>::new_with_committed_messages(rng, C, unc.iter().map(|(i, m)| (*i, m)).collect(), &self.ikp.secret_key, &self.p.sp)
            .map_err(|e| format!("{e:?}"))?;
        self.bindings.insert(key, (a.uid, binding));
        *self.roots_per_label.entry(a.uid).or_insert(0) += 1;
        Ok((blind, a))
    }

    pub fn present(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, escrow: bool) -> Result<Presentation, String> { self.p.present(rng, m, inv, j, escrow) }
    pub fn verify(&self, rng: &mut StdRng, tool: &mut Tool, inv: &Invocation, p: &Presentation) -> Result<(), String> { self.p.verify(rng, tool, inv, p) }

    /// Delegation (parent and issuer). Returns the child mandate and timings (parent_ms, issuer_ms).
    /// Convenience for tests and benchmarks: moves the issuer's clock to `epoch` and runs the whole protocol.
    pub fn delegate(&mut self, rng: &mut StdRng, parent: &Mandate, child: &Attrs, epoch: u64, j: u64) -> Result<(Mandate, f64, f64), String> {
        self.epoch = epoch;
        let issuer_nonce = { let mut b = [0u8; 16]; rng.fill_bytes(&mut b); b.to_vec() };
        let t0 = std::time::Instant::now();
        let (req, sec) = self.p.deleg_request(rng, parent, child, epoch, j, &issuer_nonce)?;
        let parent_ms = t0.elapsed().as_secs_f64() * 1e3;
        let t1 = std::time::Instant::now();
        let (blind, id) = self.deleg_issue(rng, &req, &issuer_nonce)?;
        let issuer_ms = t1.elapsed().as_secs_f64() * 1e3;
        let m = self.deleg_finish(parent, &sec, blind, id)?;
        Ok((m, parent_ms, issuer_ms))
    }

    /// Issuer: checks the parent's proof under its own nonce and the delegation seen-set, chooses id', blind-signs.
    pub fn deleg_issue(&mut self, rng: &mut StdRng, q: &DelegReq, issuer_nonce: &[u8]) -> Result<(SignatureG1<E>, u64), String> {
        if q.epoch != self.epoch { return Err("delegation: epoch differs from the issuer's clock".into()); }
        let ctx = deleg_ctx(issuer_nonce, &q.Cp);
        self.p.deleg_verify(rng, q, &ctx)?;
        let key = { let mut b = q.epoch.to_le_bytes().to_vec(); ser(&q.nymD, &mut b); b };
        if self.seen_deleg.contains(&key) { return Err("delegation pseudonym replay".into()); }
        self.seen_deleg.insert(key);
        let id = self.fresh_id(rng);
        let mut unc = BTreeMap::new();
        let (idf, verf) = (fr(id), fr(self.p.ver));
        unc.insert(I_ID, &idf);
        unc.insert(self.p.y.ver(), &verf);
        let sig = SignatureG1::<E>::new_with_committed_messages(rng, &q.Cp, unc, &self.ikp.secret_key, &self.p.sp).map_err(|e| format!("{e:?}"))?;
        Ok((sig, id))
    }

    /// Child: unblinds, checks the signature, fetches its own witness, inherits the ancestors' witnesses.
    pub fn deleg_finish(&self, parent: &Mandate, sec: &DelegSecret, blind: SignatureG1<E>, id: u64) -> Result<Mandate, String> {
        let sig = blind.unblind(&sec.r2);
        let mut a = sec.child.clone();
        a.id = id;
        let mut m = Mandate { s: sec.s, u: sec.u, a, ver: self.p.ver, sig, nm: vec![] };
        m.sig.verify(&m.msgs(), self.ikp.public_key.clone(), self.p.sp.clone()).map_err(|e| format!("child sig: {e:?}"))?;
        let mut nm = vec![self.nm_witness(id).ok_or("nm")?];
        nm.push(parent.nm[0].clone()); nm.push(parent.nm[1].clone()); nm.push(parent.nm[2].clone()); nm.push(parent.nm[3].clone());
        m.nm = nm;
        if !self.p.witnesses_valid(&m) { return Err("wallet: invalid non-membership witness from the issuer".into()); }
        Ok(m)
    }

    /// Revocation log: issues a fresh single-use nonce for one revocation request.
    pub fn log_nonce(&mut self, rng: &mut StdRng) -> Vec<u8> {
        let mut b = vec![0u8; 16]; rng.fill_bytes(&mut b);
        self.log_nonces.insert(b.clone());
        b
    }
    /// Revocation as performed by a deployment's log: `ids` must be the single identifier X covered by `auth`, X != 0,
    /// not yet revoked, and `nonce` a single-use nonce issued by the log (`log_nonce`); `auth` is either an anonymous
    /// proof by the holder of a live mandate whose id or one of its ancestor ids is X, or Schnorr signatures of two
    /// distinct escrow committee members on (X, nonce). Then the accumulator is updated as in `revoke_checked`.
    /// Every rejection message starts with "log:".
    pub fn revoke_authorized(&mut self, rng: &mut StdRng, ids: &[u64], auth: &RevocationAuth, nonce: &[u8]) -> Result<(Omega<G1Affine>, Vec<Fr>, UpdateCheck), String> {
        if ids.contains(&0) { return Err("log: identifier 0 (no ancestor) can never be revoked".into()); }
        let x = auth.target();
        if ids != [x] { return Err("log: the authorization covers another identifier".into()); }
        if !self.log_nonces.remove(nonce) { return Err("log: unknown or already used log nonce".into()); }
        if self.revoked.contains(&fr(x)) { return Err("log: identifier already revoked".into()); }
        self.p.verify_revocation_auth(rng, auth, nonce)?;
        self.revoke_checked(ids).map_err(|e| format!("log: {e}"))
    }
    /// Escrow committee member `i` (0-based) signs a revocation of `x` under the log nonce (harness: uses the member's share).
    pub fn committee_sign(&self, rng: &mut StdRng, i: usize, x: u64, nonce: &[u8]) -> (usize, (Fr, Fr)) {
        committee_sign(rng, &self.p.g, i, self.esc.shares[i], x, nonce)
    }

    /// HARNESS ONLY: revoke a batch of ids without authorization (additions only: the accumulator never removes an
    /// element). Returns (omega, additions). A deployment's log uses `revoke_authorized`.
    pub fn revoke(&mut self, ids: &[u64]) -> Result<(Omega<G1Affine>, Vec<Fr>), String> {
        self.revoke_checked(ids).map(|(o, a, _)| (o, a))
    }
    /// Revocation with a publicly checkable update: besides Omega, the issuer publishes non-membership witnesses for a
    /// point y* = H(V_old, V_new, additions, Omega) under the old and the new value. Anyone checks both, and that the public
    /// update rule maps the old witness to the new one; update data tampered to break chosen wallets fail this check
    /// except with negligible probability (y* is unpredictable to the issuer when it fixes Omega).
    /// HARNESS ONLY when called directly (no authorization check); a deployment's log uses `revoke_authorized`.
    pub fn revoke_checked(&mut self, ids: &[u64]) -> Result<(Omega<G1Affine>, Vec<Fr>, UpdateCheck), String> {
        if ids.contains(&0) { return Err("identifier 0 (no ancestor) can never be revoked".into()); }
        let add: Vec<Fr> = ids.iter().map(|i| fr(*i)).collect();
        let old = *self.acc.value();
        let omega = Omega::new(&add, &[], &old, &self.akp.secret_key);
        let (acc_old, state_old) = (self.acc.clone(), self.state.clone());
        self.acc = self.acc.add_batch(add.clone(), &self.akp.secret_key, &self.init, &mut self.state).map_err(|e| format!("{e:?}"))?;
        let ys = update_point(&old, self.acc.value(), &add, &omega);
        let w_old = acc_old.get_non_membership_witness(&ys, &self.akp.secret_key, &state_old, &self.p.ap).map_err(|e| format!("{e:?}"))?;
        let w_new = self.acc.get_non_membership_witness(&ys, &self.akp.secret_key, &self.state, &self.p.ap).map_err(|e| format!("{e:?}"))?;
        let chk = UpdateCheck { v_old: old, w_old, w_new };
        if self.acc_grace > 0 { self.p.acc_window.push(self.p.accv); while self.p.acc_window.len() > self.acc_grace { self.p.acc_window.remove(0); } }
        self.p.accv = *self.acc.value();
        self.revoked.extend(add.iter().cloned());
        Ok((omega, add, chk))
    }

    /// Escrow member i (0-based): decryption share of c with a Chaum–Pedersen proof.
    pub fn share(&self, rng: &mut StdRng, i: usize, c: &G1Affine) -> (G1Affine, (Fr, Fr)) {
        let xi = self.esc.shares[i];
        let D = (c.into_group() * xi).into_affine();
        let w = Fr::rand(rng);
        let a1 = (self.p.g.into_group() * w).into_affine();
        let a2 = (c.into_group() * w).into_affine();
        let ch = cp_challenge(&self.p.g, c, &self.p.X[i], &D, &a1, &a2);
        (D, (ch, w + ch * xi))
    }

    /// Judge: checks two shares of distinct members for both ciphertext pairs; returns (principal label, mandate id).
    pub fn judge(&self, esc: &[G1Affine; 4], s1: [(usize, G1Affine, (Fr, Fr)); 2], s2: [(usize, G1Affine, (Fr, Fr)); 2]) -> Result<(u64, u64), String> {
        self.judge_with(&self.registry, esc, s1, s2)
    }
    /// Judge against a registry of principal keys held outside the issuer (self-certified registrations in the public
    /// log, monitored by principals). The issuer's own copy `self.registry` is only used for its admission checks.
    pub fn judge_with(&self, registry: &BTreeMap<u64, G1Affine>, esc: &[G1Affine; 4], s1: [(usize, G1Affine, (Fr, Fr)); 2], s2: [(usize, G1Affine, (Fr, Fr)); 2]) -> Result<(u64, u64), String> {
        for s in [&s1, &s2] {
            if s[0].0 == s[1].0 || s[0].0 > 2 || s[1].0 > 2 { return Err("Judge: two distinct committee members required".into()); }
        }
        for (i, d, pf) in &s1 { if !self.p.judge_share(*i, &esc[0], d, pf) { return Err(format!("Judge: invalid share proof from member {}", i + 1)); } }
        for (i, d, pf) in &s2 { if !self.p.judge_share(*i, &esc[2], d, pf) { return Err(format!("Judge: invalid share proof from member {}", i + 1)); } }
        let gu = self.p.open_pair(&esc[1], [(s1[0].0, s1[0].1), (s1[1].0, s1[1].1)]);
        let gid = self.p.open_pair(&esc[3], [(s2[0].0, s2[0].1), (s2[1].0, s2[1].1)]);
        let key = { let mut b = vec![]; ser(&gu, &mut b); b };
        let (label, sig) = *self.bindings.get(&key).ok_or("Judge: opening is no bound root tag (no registered principal)")?;
        let pk = registry.get(&label).ok_or("Judge: no registered principal")?;
        if !schnorr_verify(&self.p.g, pk, &binding_msg(label, &gu), sig) { return Err("Judge: binding signature invalid".into()); }
        let key = { let mut b = vec![]; ser(&gid, &mut b); b };
        let id = *self.issued_g.get(&key).ok_or("Judge: opening is no issued mandate")?;
        Ok((label, id))
    }
}

/// 3-party DKG for a 2-of-3 sharing of x, following Gennaro, Jarecki, Krawczyk and Rabin: shares are first dealt with
/// Pedersen VSS (commitments g^a h^b, perfectly hiding, so no dealer can bias the key after seeing the others'),
/// then each qualified dealer reveals g^{a_i0}, g^{a_i1}, checked against the shares. Returns (pk, X_i, shares).
pub fn dkg_2of3(rng: &mut StdRng, g: &G1Affine) -> Result<(G1Affine, [G1Affine; 3], [Fr; 3]), String> {
    let gp = g.into_group();
    let hp = h2g(b"escrow-dkg-h").into_group();
    let a: Vec<[Fr; 2]> = (0..3).map(|_| [Fr::rand(rng), Fr::rand(rng)]).collect();
    let bb: Vec<[Fr; 2]> = (0..3).map(|_| [Fr::rand(rng), Fr::rand(rng)]).collect();
    // phase 1: Pedersen-VSS
    let C: Vec<[G1Projective; 2]> = (0..3).map(|i| [gp * a[i][0] + hp * bb[i][0], gp * a[i][1] + hp * bb[i][1]]).collect();
    let mut x = [Fr::zero(); 3];
    let mut qual = vec![true; 3];
    for j in 0..3 {
        let jj = fr(j as u64 + 1);
        for i in 0..3 {
            let (sij, tij) = (a[i][0] + a[i][1] * jj, bb[i][0] + bb[i][1] * jj);
            if (gp * sij + hp * tij).into_affine() != (C[i][0] + C[i][1] * jj).into_affine() { qual[i] = false; }
        }
    }
    if qual.iter().filter(|q| **q).count() < 2 { return Err("DKG: fewer than two qualified dealers".into()); }
    // phase 2: qualified dealers reveal A_ik = g^{a_ik}; members check them against their shares
    let A: Vec<[G1Projective; 2]> = (0..3).map(|i| [gp * a[i][0], gp * a[i][1]]).collect();
    for j in 0..3 {
        let jj = fr(j as u64 + 1);
        for i in (0..3).filter(|i| qual[*i]) {
            let sij = a[i][0] + a[i][1] * jj;
            if (gp * sij).into_affine() != (A[i][0] + A[i][1] * jj).into_affine() { return Err(format!("DKG: dealer {i} revealed inconsistent values")); }
            x[j] += sij;
        }
    }
    let pk = (0..3).filter(|i| qual[*i]).fold(G1Projective::zero(), |acc, i| acc + A[i][0]).into_affine();
    let X = [(gp * x[0]).into_affine(), (gp * x[1]).into_affine(), (gp * x[2]).into_affine()];
    Ok((pk, X, x))
}

/// Messages of a delegation session (parent -> issuer).
pub struct DelegReq { pub Cp: G1Affine, pub nymD: G1Affine, pub epoch: u64, pub pf: Proof<E> }
/// Secrets passed from the parent to the child for unblinding.
pub struct DelegSecret { pub r2: Fr, pub child: Attrs, pub s: Fr, pub u: Fr }
#[derive(Default, Clone, Copy)]
pub struct DelegCheat { pub wrap_budget: bool, pub malicious_omit_child_ranges: bool,
    /// malicious delegator: the prover's statement for this attenuation relation (message index, or REBIND_COUNTER) is
    /// re-bound to the parent's own value, so that an inflated child value in the commitment passes the client side
    pub rebind: Option<usize> }

/// Session context: issuer nonce and the parent's commitment.
pub fn deleg_ctx(issuer_nonce: &[u8], Cp: &G1Affine) -> Vec<u8> {
    let mut h = Sha256::new(); h.update(b"MM-v2-delegation"); h.update((issuer_nonce.len() as u64).to_le_bytes()); h.update(issuer_nonce);
    let mut b = vec![]; ser(Cp, &mut b); h.update(b);
    h.finalize().to_vec()
}

fn cp_challenge(g: &G1Affine, c1: &G1Affine, X: &G1Affine, D: &G1Affine, a1: &G1Affine, a2: &G1Affine) -> Fr {
    let mut b = b"MM-v2-chaum-pedersen".to_vec();
    for p in [g, c1, X, D, a1, a2] { ser(p, &mut b); }
    Fr::from_le_bytes_mod_order(&Sha256::digest(&b))
}

/// Authorization of a revocation of identifier `x` (checked by the log in `System::revoke_authorized`).
#[derive(Clone)]
pub enum RevocationAuth {
    /// Anonymous: proof of a BBS+ signature on a mandate whose message I_ID + pos is revealed and equals x;
    /// the log accepts only pos 0 (own id: v2.2.1, so that a descendant cannot revoke an ancestor and its siblings), and of the non-membership of its five identifiers in the accumulator value `accv`
    /// (the log requires the current value). Fiat–Shamir context H("MM-v2.2-revoke" || x || log nonce).
    Anonymous { x: u64, pos: usize, accv: G1Affine, proof: Proof<E> },
    /// Committee: Schnorr signatures (member index 0..2, signature) under X_i = g^{x_i} on (x, log nonce).
    Committee { x: u64, sigs: Vec<(usize, (Fr, Fr))> },
}
impl RevocationAuth {
    pub fn target(&self) -> u64 { match self { RevocationAuth::Anonymous { x, .. } | RevocationAuth::Committee { x, .. } => *x } }
}
/// Fiat–Shamir context of an anonymous revocation request.
pub fn revoke_ctx(x: u64, nonce: &[u8]) -> Vec<u8> {
    let mut h = Sha256::new(); h.update(b"MM-v2.2-revoke"); h.update(x.to_le_bytes());
    h.update((nonce.len() as u64).to_le_bytes()); h.update(nonce); h.finalize().to_vec()
}
/// Message signed by committee members to authorize the revocation of `x` under a log nonce.
pub fn revoke_committee_msg(x: u64, nonce: &[u8]) -> Vec<u8> {
    let mut b = b"MM-v2.2-revoke-committee".to_vec(); b.extend_from_slice(&x.to_le_bytes());
    b.extend_from_slice(&(nonce.len() as u64).to_le_bytes()); b.extend_from_slice(nonce); b
}
/// Committee member `i` (0-based, share `xi` from the DKG, public key X_i = g^{xi}) signs the revocation of `x`.
pub fn committee_sign(rng: &mut StdRng, g: &G1Affine, i: usize, xi: Fr, x: u64, nonce: &[u8]) -> (usize, (Fr, Fr)) {
    (i, schnorr_sign(rng, g, xi, &revoke_committee_msg(x, nonce)))
}
impl Pub {
    /// Statements of an anonymous revocation request: 0 BBS+ PoK revealing message I_ID + pos; 1 g^e = g^x; 2..6
    /// non-membership of the five identifiers, the element at the revealed position being e (bound to the public x).
    fn revoke_statements(&self, x: u64, pos: usize, accv: G1Affine, prover: bool) -> (Statements<E>, MetaStatements) {
        let mut st = Statements::<E>::new();
        let mut rev = BTreeMap::new(); rev.insert(I_ID + pos, fr(x));
        if prover { st.add(BbsP::new_statement_from_params(self.sp.clone(), rev)); }
        else { st.add(BbsV::new_statement_from_params(self.sp.clone(), self.ipk.clone(), rev)); }
        // the Pedersen statement precedes the non-membership statements: proof_system takes the response of an element in
        // an equality from an earlier statement (as for the BBS+ messages in a presentation)
        st.add(PedStmt::new_statement_from_params(vec![self.g], (self.g.into_group() * fr(x)).into_affine()));
        let mut eqs: Vec<Vec<(usize, usize)>> = vec![];
        for i in 0..5 {
            st.add(NonMemStmt::new_statement_from_params(self.ap.clone(), self.apk.clone(), self.nmk.clone(), accv));
            if i == pos { eqs.push(vec![(1, 0), (2 + i, 0)]); } else { eqs.push(vec![(0, I_ID + i), (2 + i, 0)]); }
        }
        let mut ms = MetaStatements::new();
        merge_eqs(eqs, &mut ms);
        (st, ms)
    }
    /// Requester (holder of `m`): anonymous request to revoke `x`, which must be the mandate's own id (the parent revokes a
    /// child with the child credential it obtained when delegating); proves against the current accumulator value, bound to the log nonce.
    pub fn revocation_request(&self, rng: &mut StdRng, m: &Mandate, x: u64, nonce: &[u8]) -> Result<RevocationAuth, String> {
        if x == 0 { return Err("revocation request: identifier 0 cannot be revoked".into()); }
        if m.ids()[0] != x { return Err("revocation request: x is not the mandate's own identifier (only the holder or the parent holding this credential may revoke it)".into()); }
        self.revocation_request_at(rng, m, x, 0, nonce)
    }
    /// Same, revealing position `pos` with value `x` (no plaintext check: malicious-requester tests).
    pub fn revocation_request_at(&self, rng: &mut StdRng, m: &Mandate, x: u64, pos: usize, nonce: &[u8]) -> Result<RevocationAuth, String> {
        if pos > 4 { return Err("revocation request: position out of range".into()); }
        let (st, ms) = self.revoke_statements(x, pos, self.accv, true);
        let msgs = m.msgs();
        let mut w = Witnesses::new();
        let unrev: BTreeMap<usize, Fr> = msgs.iter().enumerate().filter(|(i, _)| *i != I_ID + pos).map(|(i, v)| (i, *v)).collect();
        w.add(BbsWit::new_as_witness(m.sig.clone(), unrev));
        w.add(Witness::PedersenCommitment(vec![fr(m.ids()[pos])]));
        for (i, id) in m.ids().iter().enumerate() {
            w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: m.nm[i].clone() }));
        }
        let spec = ProofSpec::new(st, ms, vec![], Some(revoke_ctx(x, nonce)));
        let proof = guard(|| Proof::new::<StdRng, Blake2b512>(rng, spec, w, Some(nonce.to_vec()), Default::default()).map_err(|e| format!("revocation prove: {e:?}")))?.0;
        Ok(RevocationAuth::Anonymous { x, pos, accv: self.accv, proof })
    }
    /// Public check of a revocation authorization (the log, and any auditor of the log). Does not check nonce freshness.
    pub fn verify_revocation_auth(&self, rng: &mut StdRng, auth: &RevocationAuth, nonce: &[u8]) -> Result<(), String> {
        match auth {
            RevocationAuth::Anonymous { x, pos, accv, proof } => {
                if *x == 0 { return Err("log: identifier 0 (no ancestor) can never be revoked".into()); }
                // only the mandate's own identifier may be revealed: its holder, or the parent that keeps the child credential
                // it obtained when delegating, can revoke it; a descendant cannot revoke an ancestor (and its siblings)
                if *pos != 0 { return Err("log: anonymous revocation must reveal the mandate's own identifier (pos 0)".into()); }
                if *accv != self.accv { return Err("log: revocation proof not made against the current accumulator value".into()); }
                let (st, ms) = self.revoke_statements(*x, *pos, *accv, false);
                let spec = ProofSpec::new(st, ms, vec![], Some(revoke_ctx(*x, nonce)));
                guard(|| proof.clone().verify::<StdRng, Blake2b512>(rng, spec, Some(nonce.to_vec()), Default::default())
                    .map_err(|e| format!("log: revocation proof: {e:?}")))
            }
            RevocationAuth::Committee { x, sigs } => {
                if *x == 0 { return Err("log: identifier 0 (no ancestor) can never be revoked".into()); }
                let msg = revoke_committee_msg(*x, nonce);
                let mut members = BTreeSet::new();
                for (i, sig) in sigs {
                    if *i > 2 { return Err("log: committee member index out of range".into()); }
                    if !schnorr_verify(&self.g, &self.X[*i], &msg, *sig) { return Err(format!("log: invalid committee signature from member {}", i + 1)); }
                    members.insert(*i);
                }
                if members.len() < 2 { return Err("log: signatures of two distinct committee members required".into()); }
                Ok(())
            }
        }
    }
}

/// Public spot check of accumulator update data (see `System::revoke_checked`).
#[derive(Clone, Debug)]
pub struct UpdateCheck { pub v_old: G1Affine, pub w_old: NonMembershipWitness<G1Affine>, pub w_new: NonMembershipWitness<G1Affine> }
pub fn update_point(v_old: &G1Affine, v_new: &G1Affine, add: &[Fr], omega: &Omega<G1Affine>) -> Fr {
    let mut b = b"MM-v2.2-update-spot-check".to_vec();
    ser(v_old, &mut b); ser(v_new, &mut b);
    b.extend_from_slice(&(add.len() as u64).to_le_bytes()); for a in add { a.serialize_compressed(&mut b).unwrap(); }
    b.extend_from_slice(&(omega.0.len() as u64).to_le_bytes()); for o in &omega.0 { ser(o, &mut b); }
    Fr::from_le_bytes_mod_order(&Sha256::digest(&b))
}
impl Pub {
    /// Anyone (wallets, tools, auditors): checks published update data against the current public value self.accv.
    pub fn check_update(&self, add: &[Fr], omega: &Omega<G1Affine>, c: &UpdateCheck) -> bool {
        let ys = update_point(&c.v_old, &self.accv, add, omega);
        let ok_old = UniversalAccumulator::<G1Affine>::verify_non_membership_given_accumulated(&c.v_old, &ys, &c.w_old, &self.apk, &self.ap);
        let ok_new = UniversalAccumulator::<G1Affine>::verify_non_membership_given_accumulated(&self.accv, &ys, &c.w_new, &self.apk, &self.ap);
        let upd = c.w_old.update_using_public_info_after_batch_updates(add, &[], omega, &ys).map(|w| w == c.w_new).unwrap_or(false);
        ok_old && ok_new && upd
    }
}

pub fn rng(seed: u64) -> StdRng { StdRng::seed_from_u64(seed) }

/// Message signed by the principal to bind a per-root tag T = g^t to its registered label.
pub fn binding_msg(label: u64, T: &G1Affine) -> Vec<u8> {
    let mut b = b"MM-v2-root-binding".to_vec(); b.extend_from_slice(&label.to_le_bytes()); ser(T, &mut b); b
}
fn root_ctx(nonce: &[u8], C: &G1Affine, T: &G1Affine) -> Vec<u8> {
    let mut h = Sha256::new(); h.update(b"MM-v2-issue-root"); h.update((nonce.len() as u64).to_le_bytes()); h.update(nonce);
    let mut b = vec![]; ser(C, &mut b); ser(T, &mut b); h.update(b); h.finalize().to_vec()
}
/// Schnorr signature over G1 (challenge, response).
pub fn schnorr_sign(rng: &mut StdRng, g: &G1Affine, x: Fr, msg: &[u8]) -> (Fr, Fr) {
    let k = Fr::rand(rng);
    let R = (g.into_group() * k).into_affine();
    let X = (g.into_group() * x).into_affine();
    let c = schnorr_ch(&R, &X, msg);
    (c, k + c * x)
}
pub fn schnorr_verify(g: &G1Affine, X: &G1Affine, msg: &[u8], sig: (Fr, Fr)) -> bool {
    let (c, z) = sig;
    let R = (g.into_group() * z - X.into_group() * c).into_affine();
    schnorr_ch(&R, X, msg) == c
}
fn schnorr_ch(R: &G1Affine, X: &G1Affine, msg: &[u8]) -> Fr {
    let mut b = b"MM-v2-schnorr".to_vec(); ser(R, &mut b); ser(X, &mut b); b.extend_from_slice(&(msg.len() as u64).to_le_bytes()); b.extend_from_slice(msg);
    Fr::from_le_bytes_mod_order(&Sha256::digest(&b))
}

/// Hash-derived public parameters (BBS+ bases, accumulator P and P~, non-membership proving key, Bulletproofs++ bases).
pub fn public_params(y: Lay) -> (SignatureParamsG1<E>, AccParams<E>, NonMembershipProvingKey<G1Affine>, BppParams<G1Affine>) {
    let sp = SignatureParamsG1::<E>::new::<Blake2b512>(b"MaskedMandates-v2-BBS+", y.l() as u32);
    let ap = AccParams::<E>::new::<Blake2b512>(b"MaskedMandates-v2-VB-accumulator");
    let nmk = NonMembershipProvingKey::<G1Affine>::new::<Blake2b512>(b"MaskedMandates-v2-VB-non-membership");
    let bpp = BppParams::<G1Affine>::new_for_arbitrary_range_proof::<Blake2b512>(b"MaskedMandates-v2-BPP", 2, 64, 1);
    (sp, ap, nmk, bpp)
}

// ---- In-memory stores (vb_accumulator ships them only under cfg(test)) ----
use std::collections::HashSet;
use vb_accumulator::persistence::{InitialElementsStore, State, UniversalAccumulatorState};
#[derive(Clone, Debug, Default)]
pub struct InMemoryInitialElements<T: Clone + std::hash::Hash + Eq> { pub db: HashSet<T> }
impl<T: Clone + std::hash::Hash + Eq> InMemoryInitialElements<T> { pub fn new() -> Self { Self { db: HashSet::new() } } }
impl<T: Clone + std::hash::Hash + Eq> InitialElementsStore<T> for InMemoryInitialElements<T> {
    fn add(&mut self, e: T) { self.db.insert(e); }
    fn has(&self, e: &T) -> bool { self.db.contains(e) }
}
#[derive(Clone, Debug, Default)]
pub struct InMemoryState<T: Clone + std::hash::Hash + Eq> { pub db: HashSet<T> }
impl<T: Clone + std::hash::Hash + Eq> InMemoryState<T> { pub fn new() -> Self { Self { db: HashSet::new() } } }
impl<T: Clone + std::hash::Hash + Eq> State<T> for InMemoryState<T> {
    fn add(&mut self, e: T) { self.db.insert(e); }
    fn remove(&mut self, e: &T) { self.db.remove(e); }
    fn has(&self, e: &T) -> bool { self.db.contains(e) }
    fn size(&self) -> u64 { self.db.len() as u64 }
}
impl<'a, T: Clone + std::hash::Hash + Eq + 'a> UniversalAccumulatorState<'a, T> for InMemoryState<T> {
    type ElementIterator = std::collections::hash_set::Iter<'a, T>;
    fn elements(&'a self) -> Self::ElementIterator { self.db.iter() }
}

impl Mandate {
    /// Holder refreshes its 5 non-membership witnesses from public data (additions + Omega).
    pub fn refresh(&mut self, additions: &[Fr], omega: &Omega<G1Affine>) -> Result<(), String> {
        let ids = self.ids();
        for i in 0..5 {
            self.nm[i] = self.nm[i].update_using_public_info_after_batch_updates(additions, &[], omega, &fr(ids[i]))
                .map_err(|e| format!("refresh: {e:?}"))?;
        }
        Ok(())
    }
    /// Refreshes every witness whose identifier is not in the published batch; returns the positions
    /// (0 = own id, 1..4 = ancestors) that could not be refreshed (revoked identifiers).
    pub fn refresh_partial(&mut self, additions: &[Fr], omega: &Omega<G1Affine>) -> Vec<usize> {
        let ids = self.ids();
        let mut stuck = vec![];
        for i in 0..5 {
            if additions.contains(&fr(ids[i])) { stuck.push(i); continue; }
            match self.nm[i].update_using_public_info_after_batch_updates(additions, &[], omega, &fr(ids[i])) {
                Ok(w) => self.nm[i] = w,
                Err(_) => stuck.push(i),
            }
        }
        stuck
    }
}

/// Some sub-protocols panic instead of returning an error on invalid inputs.
/// Treat a panic as a rejection (prover: cannot build the proof; verifier: reject).
pub fn guard<T>(f: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(|_| {}));
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));
    std::panic::set_hook(prev);
    match r { Ok(x) => x, Err(_) => Err("rejected (panic caught: invalid witness or malformed input)".into()) }
}

impl Presentation {
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut b = vec![];
        ser(&self.accv, &mut b);
        ser(&self.nym, &mut b);
        match &self.esc { Some(c) => { b.push(1); for x in c { ser(x, &mut b); } } None => b.push(0) }
        ser(&self.proof, &mut b);
        b
    }
    pub fn from_bytes(b: &[u8]) -> Result<Self, String> {
        guard(|| {
            let mut rd = b;
            let accv = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
            let nym = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
            if rd.is_empty() { return Err("short".into()); }
            let flag = rd[0]; rd = &rd[1..];
            let esc = match flag {
                1 => {
                    let mut c = [G1Affine::zero(); 4];
                    for x in c.iter_mut() { *x = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?; }
                    Some(c)
                }
                0 => None,
                _ => return Err("bad escrow flag".into()),
            };
            let proof = Proof::<E>::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
            if !rd.is_empty() { return Err("trailing bytes".into()); }
            Ok(Presentation { accv, nym, esc, proof })
        })
    }
}
