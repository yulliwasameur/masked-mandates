//! mm-core — Masked Mandates (reconstruction du 11/11/2026 d'après la section V du manuscrit).
//! BBS+ (bbs_plus 0.25), VB universal accumulator (vb_accumulator 0.29),
//! Bulletproofs++ (bulletproofs_plus_plus 0.9), composite proofs (proof_system 0.34), BLS12-381.
#![allow(non_snake_case)]
use ark_bls12_381::{Bls12_381, Fr, G1Affine, G1Projective};
use ark_ec::{AffineRepr, CurveGroup};
use ark_ff::{One, PrimeField, Zero};
use ark_serialize::CanonicalSerialize;
use ark_std::{
    collections::{BTreeMap, BTreeSet},
    rand::{rngs::StdRng, RngCore, SeedableRng},
    UniformRand,
};
use bbs_plus::prelude::{KeypairG2, SignatureG1, SignatureParamsG1};
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
    Accumulator, Keypair as AccKeypair,
    NonMembershipProvingKey, NonMembershipWitness, Omega, SetupParams as AccParams,
    UniversalAccumulator,
};

pub type E = Bls12_381;

pub const NCLS: usize = 16; // default
pub const I_S: usize = 0;
pub const I_ID: usize = 1;
pub const I_ANC: usize = 2; // 2..=5
pub const I_DEPTH: usize = 6;
pub const I_SCOPE: usize = 7; // 7..7+n
#[derive(Clone, Copy, Debug)]
pub struct Lay { pub n: usize }
impl Lay {
    pub fn l(&self) -> usize { 12 + self.n }
    pub fn budget(&self) -> usize { 7 + self.n }
    pub fn k(&self) -> usize { 8 + self.n }
    pub fn exp(&self) -> usize { 9 + self.n }
    pub fn uid(&self) -> usize { 10 + self.n }
    pub fn ver(&self) -> usize { 11 + self.n }
}
pub const MAXV: u64 = 1u64 << 40;
pub const MAXDEPTH: u64 = 4;

pub fn fr(x: u64) -> Fr { Fr::from(x) }
pub fn h2g(label: &[u8]) -> G1Affine { affine_group_elem_from_try_and_incr::<G1Affine, Blake2b512>(label) }
fn wref(a: usize, b: usize) -> WitnessRef { (a, b) }
fn eq(v: &[(usize, usize)]) -> EqualWitnesses { EqualWitnesses(v.iter().map(|&(a, b)| wref(a, b)).collect::<BTreeSet<_>>()) }
pub fn ser_len<T: CanonicalSerialize>(t: &T) -> usize { t.compressed_size() }

#[derive(Clone, Debug)]
pub struct Attrs {
    pub id: u64,
    pub anc: [u64; 4],
    pub depth: u64,
    pub scope: Vec<bool>,
    pub budget: u64,
    pub k: u64,
    pub exp: u64,
    pub uid: u64,
}

impl Attrs {
    pub fn lay(&self) -> Lay { Lay { n: self.scope.len() } }
    /// m_1..m_{L-2} (id .. uid) as field elements, indexed by message index.
    pub fn msgs_1_uid(&self) -> Vec<(usize, Fr)> {
        let mut v = vec![(I_ID, fr(self.id))];
        for i in 0..4 { v.push((I_ANC + i, fr(self.anc[i]))); }
        v.push((I_DEPTH, fr(self.depth)));
        let y = self.lay();
        for c in 0..y.n { v.push((I_SCOPE + c, if self.scope[c] { Fr::one() } else { Fr::zero() })); }
        v.push((y.budget(), fr(self.budget)));
        v.push((y.k(), fr(self.k)));
        v.push((y.exp(), fr(self.exp)));
        v.push((y.uid(), fr(self.uid)));
        v
    }
    /// a' ⪯ a (plaintext check, used by honest parties and by the test oracle)
    pub fn attenuates(&self, p: &Attrs) -> bool {
        (0..self.scope.len()).all(|c| !self.scope[c] || p.scope[c])
            && self.budget <= p.budget && self.k <= p.k && self.exp <= p.exp
            && self.depth == p.depth + 1 && self.depth <= MAXDEPTH
            && self.anc == [p.id, p.anc[0], p.anc[1], p.anc[2]] && self.uid == p.uid
    }
}

#[derive(Clone, Debug, serde::Serialize)]
pub struct Invocation {
    pub tool: String,
    pub call: String, // canonical JSON of tools/call
    pub class: usize,
    pub amt: u64,
    pub epoch: u64,
    pub t: u64,
    pub nonce: String,
}
impl Invocation {
    pub fn ctx(&self) -> Vec<u8> { Sha256::digest(serde_json::to_vec(self).unwrap()).to_vec() }
}

pub struct Mandate {
    pub s: Fr,
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
        for (i, v) in self.a.msgs_1_uid() { m[i] = v; }
        m[y.ver()] = fr(self.ver);
        m
    }
    pub fn ids(&self) -> [u64; 5] { [self.a.id, self.a.anc[0], self.a.anc[1], self.a.anc[2], self.a.anc[3]] }
}

pub struct Escrow {
    pub pk: G1Affine,
    pub shares: [Fr; 3], // Shamir 2-of-3 of x (dealer in the prototype)
    pub X: [G1Affine; 3],
}

pub struct System {
    pub y: Lay,
    pub sp: SignatureParamsG1<E>,
    pub ikp: KeypairG2<E>,
    pub ap: AccParams<E>,
    pub akp: AccKeypair<E>,
    pub acc: UniversalAccumulator<G1Affine>,
    pub init: InMemoryInitialElements<Fr>,
    pub state: InMemoryState<Fr>,
    pub nmk: NonMembershipProvingKey<G1Affine>,
    pub bpp: BppParams<G1Affine>,
    pub g: G1Affine,
    pub esc: Escrow,
    pub ver: u64,
    pub seen_deleg: BTreeSet<Vec<u8>>, // issuer-side delegation pseudonyms
    pub revoked: Vec<Fr>,
}

#[derive(Clone)]
pub struct Presentation {
    pub nym: G1Affine,
    pub j: u64,
    pub esc: Option<(G1Affine, G1Affine)>,
    pub proof: Proof<E>,
}
impl Presentation {
    pub fn size(&self) -> usize {
        ser_len(&self.nym) + 8 + self.esc.map(|(a, b)| ser_len(&a) + ser_len(&b)).unwrap_or(0) + ser_len(&self.proof)
    }
}

#[derive(Default, Clone)]
pub struct Cheat { pub esc_uid: Option<u64>, pub acc_value: Option<G1Affine> }

pub struct Tool {
    pub name: String,
    pub seen: BTreeSet<(u64, Vec<u8>)>,
    pub require_escrow: bool,
}
impl Tool {
    pub fn new(name: &str, require_escrow: bool) -> Self { Tool { name: name.into(), seen: BTreeSet::new(), require_escrow } }
}

pub fn nym_base(tool: &str, epoch: u64, j: u64) -> G1Affine {
    h2g(format!("MM-nym|{}|{}|{}", tool, epoch, j).as_bytes())
}
pub fn deleg_base(epoch: u64, j: u64) -> G1Affine { h2g(format!("MM-nym|delegate|{}|{}", epoch, j).as_bytes()) }

fn lagrange_at0(i: u64, jj: u64) -> (Fr, Fr) {
    // coefficients for points i, jj (1-based) at x = 0
    let (xi, xj) = (fr(i), fr(jj));
    (xj / (xj - xi), xi / (xi - xj))
}

impl System {
    /// Setup with an accumulator able to hold `max_rev` revoked ids.
    pub fn setup(rng: &mut StdRng, max_rev: u64) -> Self { Self::setup_n(rng, max_rev, NCLS) }
    pub fn setup_n(rng: &mut StdRng, max_rev: u64, n: usize) -> Self {
        let y = Lay { n };
        let sp = SignatureParamsG1::<E>::new::<Blake2b512>(b"MaskedMandates-BBS+", y.l() as u32);
        let ikp = KeypairG2::<E>::generate_using_rng(rng, &sp);
        let ap = AccParams::<E>::generate_using_rng(rng);
        let akp = AccKeypair::<E>::generate_using_rng(rng, &ap);
        let mut init = InMemoryInitialElements::new();
        let acc = UniversalAccumulator::initialize_with_all_random(rng, &ap, max_rev, &akp.secret_key, &mut init);
        let nmk = NonMembershipProvingKey::<G1Affine>::generate_using_rng(rng);
        let bpp = BppParams::<G1Affine>::new_for_arbitrary_range_proof::<Blake2b512>(b"MaskedMandates-BPP", 2, 64, 1);
        let g = h2g(b"MM-g");
        // escrow: x shared 2-of-3 by a dealer
        let x = Fr::rand(rng);
        let a1 = Fr::rand(rng);
        let shares = [x + a1, x + a1 * fr(2), x + a1 * fr(3)];
        let gp = g.into_group();
        let pk = (gp * x).into_affine();
        let X = [(gp * shares[0]).into_affine(), (gp * shares[1]).into_affine(), (gp * shares[2]).into_affine()];
        System { y, sp, ikp, ap, akp, acc, init, state: InMemoryState::new(), nmk, bpp, g, esc: Escrow { pk, shares, X },
                 ver: 1, seen_deleg: BTreeSet::new(), revoked: vec![] }
    }

    pub fn nm_witness(&self, id: u64) -> Option<NonMembershipWitness<G1Affine>> {
        self.acc.get_non_membership_witness(&fr(id), &self.akp.secret_key, &self.state, &self.ap).ok()
    }

    /// Root issuance: holder sends C = h0^r h[0]^s with a PoK of opening; issuer signs the rest in clear.
    pub fn issue_root(&mut self, rng: &mut StdRng, a: &Attrs) -> Result<Mandate, String> {
        // holder side
        let s = Fr::rand(rng);
        let r = Fr::rand(rng);
        let C = self.sp.commit_to_messages(vec![(I_S, &s)], &r).map_err(|e| format!("{e:?}"))?;
        let ctx = b"MM-issue-root".to_vec();
        let bases = vec![self.sp.h_0, self.sp.h[I_S]];
        let pf = ped_pok(rng, &bases, &C, vec![r, s], &ctx)?;
        // issuer side
        ped_verify(rng, &bases, &C, &pf, &ctx)?;
        if a.depth != 0 || a.anc != [0; 4] || a.id == 0 { return Err("root: bad public attributes".into()); }
        let mut unc: BTreeMap<usize, Fr> = a.msgs_1_uid().into_iter().collect();
        unc.insert(self.y.ver(), fr(self.ver));
        let blind = SignatureG1::<E>::new_with_committed_messages(rng, &C, unc.iter().map(|(i, m)| (*i, m)).collect(), &self.ikp.secret_key, &self.sp)
            .map_err(|e| format!("{e:?}"))?;
        // holder unblinds and checks
        let sig = blind.unblind(&r);
        let mut m = Mandate { s, a: a.clone(), ver: self.ver, sig, nm: vec![] };
        m.sig.verify(&m.msgs(), self.ikp.public_key.clone(), self.sp.clone()).map_err(|e| format!("root sig: {e:?}"))?;
        m.nm = m.ids().iter().map(|id| self.nm_witness(*id).ok_or("nm witness")).collect::<Result<_, _>>()?;
        Ok(m)
    }

    fn present_statements(&self, inv: &Invocation, j: u64, nym: &G1Affine, esc: &Option<(G1Affine, G1Affine)>, prover: bool, accv: G1Affine)
        -> Result<(Statements<E>, MetaStatements), String> {
        let mut st = Statements::<E>::new();
        let mut ms = MetaStatements::new();
        let mut rev = BTreeMap::new();
        rev.insert(I_SCOPE + inv.class, Fr::one());
        if prover { st.add(BbsP::new_statement_from_params(self.sp.clone(), rev)); }
        else { st.add(BbsV::new_statement_from_params(self.sp.clone(), self.ikp.public_key.clone(), rev)); }
        // 1: pseudonym
        st.add(PedStmt::new_statement_from_params(vec![nym_base(&inv.tool, inv.epoch, j)], *nym));
        ms.add_witness_equality(eq(&[(0, I_S), (1, 0)]));
        // 2..4: ranges
        let mut idx = 2;
        for (mi, lo) in [(self.y.budget(), inv.amt), (self.y.k(), j + 1), (self.y.exp(), inv.t)] {
            st.add(BoundCheckBpp::new_statement_from_params(lo, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            ms.add_witness_equality(eq(&[(0, mi), (idx, 0)]));
            idx += 1;
        }
        // 5..9: non-membership of id and ancestors
        for i in 0..5 {
            st.add(NonMemStmt::new_statement_from_params(self.ap.clone(), self.akp.public_key.clone(), self.nmk.clone(), accv));
            ms.add_witness_equality(eq(&[(0, I_ID + i), (idx, 0)]));
            idx += 1;
        }
        // optional escrow: c1 = g^r ; c2 = g^uid pk^r
        if let Some((c1, c2)) = esc {
            st.add(PedStmt::new_statement_from_params(vec![self.g], *c1));
            st.add(PedStmt::new_statement_from_params(vec![self.g, self.esc.pk], *c2));
            ms.add_witness_equality(eq(&[(0, self.y.uid()), (idx + 1, 0)]));
            ms.add_witness_equality(eq(&[(idx, 0), (idx + 1, 1)]));
        }
        Ok((st, ms))
    }

    /// Agent: present mandate `m` for invocation `inv` with counter j.
    pub fn present(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, escrow: bool) -> Result<Presentation, String> {
        self.present_cheat(rng, m, inv, j, escrow, &Cheat::default())
    }
    pub fn present_cheat(&self, rng: &mut StdRng, m: &Mandate, inv: &Invocation, j: u64, escrow: bool, ch: &Cheat) -> Result<Presentation, String> {
        let msgs = m.msgs();
        let nym = (nym_base(&inv.tool, inv.epoch, j).into_group() * m.s).into_affine();
        let mut esc_w = None;
        let esc = if escrow {
            let r = Fr::rand(rng);
            let c1 = (self.g.into_group() * r).into_affine();
            let c2 = (self.g.into_group() * fr(ch.esc_uid.unwrap_or(m.a.uid)) + self.esc.pk.into_group() * r).into_affine();
            esc_w = Some(r);
            Some((c1, c2))
        } else { None };
        let (st, ms) = self.present_statements(inv, j, &nym, &esc, true, ch.acc_value.unwrap_or(*self.acc.value()))?;
        let mut w = Witnesses::new();
        let unrev: BTreeMap<usize, Fr> = msgs.iter().enumerate().filter(|(i, _)| *i != I_SCOPE + inv.class).map(|(i, v)| (i, *v)).collect();
        w.add(BbsWit::new_as_witness(m.sig.clone(), unrev));
        w.add(Witness::PedersenCommitment(vec![m.s]));
        w.add(Witness::BoundCheckBpp(msgs[self.y.budget()]));
        w.add(Witness::BoundCheckBpp(msgs[self.y.k()]));
        w.add(Witness::BoundCheckBpp(msgs[self.y.exp()]));
        for (i, id) in m.ids().iter().enumerate() {
            w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: m.nm[i].clone() }));
        }
        if let Some(r) = esc_w {
            w.add(Witness::PedersenCommitment(vec![r]));
            w.add(Witness::PedersenCommitment(vec![fr(ch.esc_uid.unwrap_or(m.a.uid)), r]));
        }
        let spec = ProofSpec::new(st, ms, vec![], Some(inv.ctx()));
        let nonce = Some(inv.nonce.as_bytes().to_vec());
        let proof = guard(|| Proof::new::<StdRng, Blake2b512>(rng, spec, w, nonce, Default::default()).map_err(|e| format!("prove: {e:?}")))?.0;
        Ok(Presentation { nym, j, esc, proof })
    }

    /// Tool: verify and record.
    pub fn verify(&self, rng: &mut StdRng, tool: &mut Tool, inv: &Invocation, p: &Presentation) -> Result<(), String> {
        if inv.tool != tool.name { return Err("wrong tool".into()); }
        if tool.require_escrow && p.esc.is_none() { return Err("escrow required".into()); }
        let key = (inv.epoch, { let mut b = vec![]; p.nym.serialize_compressed(&mut b).unwrap(); b });
        if tool.seen.contains(&key) { return Err("pseudonym replay".into()); }
        let (st, ms) = self.present_statements(inv, p.j, &p.nym, &p.esc, false, *self.acc.value())?;
        let spec = ProofSpec::new(st, ms, vec![], Some(inv.ctx()));
        p.proof.clone().verify::<StdRng, Blake2b512>(rng, spec, Some(inv.nonce.as_bytes().to_vec()), Default::default())
            .map_err(|e| format!("verify: {e:?}"))?;
        tool.seen.insert(key);
        Ok(())
    }

    /// Delegation (three parties). Returns the child mandate and timings (parent_ms, issuer_ms).
    pub fn delegate(&mut self, rng: &mut StdRng, parent: &Mandate, child: &Attrs, epoch: u64, j: u64)
        -> Result<(Mandate, f64, f64), String> {
        let t0 = std::time::Instant::now();
        // child: commit to its link secret
        let s2 = Fr::rand(rng);
        let r1 = Fr::rand(rng);
        let Cc = self.sp.commit_to_messages(vec![(I_S, &s2)], &r1).map_err(|e| format!("{e:?}"))?;
        // parent: commit to child attributes m'_1..uid
        let r2 = Fr::rand(rng);
        let cm = child.msgs_1_uid();
        let Cp = self.sp.commit_to_messages(cm.iter().map(|(i, v)| (*i, v)).collect::<Vec<_>>(), &r2).map_err(|e| format!("{e:?}"))?;
        let issuer_nonce = { let mut b = [0u8; 16]; rng.fill_bytes(&mut b); b.to_vec() };
        let ctx = { let mut h = Sha256::new(); h.update(&issuer_nonce); for c in [&Cc, &Cp] { let mut b = vec![]; c.serialize_compressed(&mut b).unwrap(); h.update(b); } h.finalize().to_vec() };
        let nymD = (deleg_base(epoch, j).into_group() * parent.s).into_affine();
        let pf = self.deleg_proof(rng, parent, child, r2, &Cp, &nymD, epoch, j, &ctx)?;
        // child: PoK of opening of Cc, same context
        let cb = vec![self.sp.h_0, self.sp.h[I_S]];
        let cpf = ped_pok(rng, &cb, &Cc, vec![r1, s2], &ctx)?;
        let parent_ms = t0.elapsed().as_secs_f64() * 1e3;
        // issuer
        let t1 = std::time::Instant::now();
        self.deleg_verify(rng, &Cp, &nymD, epoch, j, &pf, &ctx)?;
        ped_verify(rng, &cb, &Cc, &cpf, &ctx)?;
        let key = { let mut b = epoch.to_le_bytes().to_vec(); nymD.serialize_compressed(&mut b).unwrap(); b };
        if self.seen_deleg.contains(&key) { return Err("delegation pseudonym replay".into()); }
        self.seen_deleg.insert(key);
        let C = (Cc.into_group() + Cp.into_group()).into_affine();
        let mut unc = BTreeMap::new();
        let verf = fr(self.ver);
        unc.insert(self.y.ver(), &verf);
        let blind = SignatureG1::<E>::new_with_committed_messages(rng, &C, unc, &self.ikp.secret_key, &self.sp).map_err(|e| format!("{e:?}"))?;
        let issuer_ms = t1.elapsed().as_secs_f64() * 1e3;
        // child unblinds
        let sig = blind.unblind(&(r1 + r2));
        let mut m = Mandate { s: s2, a: child.clone(), ver: self.ver, sig, nm: vec![] };
        m.sig.verify(&m.msgs(), self.ikp.public_key.clone(), self.sp.clone()).map_err(|e| format!("child sig: {e:?}"))?;
        // inherits ancestors' witnesses (parent's id + its first three ancestors), fetches its own
        let mut nm = vec![self.nm_witness(child.id).ok_or("nm")?];
        nm.push(parent.nm[0].clone()); nm.push(parent.nm[1].clone()); nm.push(parent.nm[2].clone()); nm.push(parent.nm[3].clone());
        m.nm = nm;
        Ok((m, parent_ms, issuer_ms))
    }

    fn deleg_statements(&self, Cp: &G1Affine, nymD: &G1Affine, j: u64, prover: bool) -> Result<(Statements<E>, MetaStatements), String> {
        let mut st = Statements::<E>::new();
        let mut ms = MetaStatements::new();
        if prover { st.add(BbsP::new_statement_from_params(self.sp.clone(), BTreeMap::new())); }
        else { st.add(BbsV::new_statement_from_params(self.sp.clone(), self.ikp.public_key.clone(), BTreeMap::new())); }
        // 1..5 non-membership of parent's id and ancestors
        for i in 0..5 {
            st.add(NonMemStmt::new_statement_from_params(self.ap.clone(), self.akp.public_key.clone(), self.nmk.clone(), *self.acc.value()));
            ms.add_witness_equality(eq(&[(0, I_ID + i), (1 + i, 0)]));
        }
        // 6: commitment to child attributes: bases h0, h[1..=uid]; witness order r2, m'_1..m'_uid
        let mut bases = vec![self.sp.h_0];
        for i in I_ID..=self.y.uid() { bases.push(self.sp.h[i]); }
        st.add(PedStmt::new_statement_from_params(bases, *Cp));
        let cw = |mi: usize| mi - I_ID + 1; // witness index of m'_mi inside statement 6
        // ancestry: anc'_1 = id, anc'_{i+1} = anc_i ; uid' = uid
        ms.add_witness_equality(eq(&[(0, I_ID), (6, cw(I_ANC))]));
        for i in 0..3 { ms.add_witness_equality(eq(&[(0, I_ANC + i), (6, cw(I_ANC + i + 1))])); }
        ms.add_witness_equality(eq(&[(0, self.y.uid()), (6, cw(self.y.uid()))]));
        let g = self.g;
        let gneg = (-g.into_group()).into_affine();
        let mut idx = 7;
        // depth' - depth = 1 : g^{depth'} (g^-1)^{depth} = g ; depth' in [1, 5)
        st.add(PedStmt::new_statement_from_params(vec![g, gneg], g));
        ms.add_witness_equality(eq(&[(6, cw(I_DEPTH)), (idx, 0), (idx + 1, 0)]));
        ms.add_witness_equality(eq(&[(0, I_DEPTH), (idx, 1)]));
        st.add(BoundCheckBpp::new_statement_from_params(1, MAXDEPTH + 1, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
        idx += 2;
        // numeric attenuation: d + x' - x = 1, d in [1, 2^40); scope: d_c + b'_c - b_c = 1, d_c in [1, 3)
        let mut items: Vec<(usize, u64)> = vec![(self.y.budget(), MAXV), (self.y.k(), MAXV), (self.y.exp(), MAXV)];
        for c in 0..self.y.n { items.push((I_SCOPE + c, 3)); }
        for (mi, hi) in items {
            st.add(PedStmt::new_statement_from_params(vec![g, g, gneg], g));
            ms.add_witness_equality(eq(&[(idx, 0), (idx + 1, 0)]));
            ms.add_witness_equality(eq(&[(6, cw(mi)), (idx, 1)]));
            ms.add_witness_equality(eq(&[(0, mi), (idx, 2)]));
            st.add(BoundCheckBpp::new_statement_from_params(1, hi, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
            idx += 2;
        }
        // delegation pseudonym and quota: nymD = H(delegate|e|j)^s, k in [j+1, 2^40)
        st.add(PedStmt::new_statement_from_params(vec![deleg_base(0, 0)], *nymD)); // placeholder base replaced below
        ms.add_witness_equality(eq(&[(0, I_S), (idx, 0)]));
        st.add(BoundCheckBpp::new_statement_from_params(j + 1, MAXV, self.bpp.clone()).map_err(|e| format!("{e:?}"))?);
        ms.add_witness_equality(eq(&[(0, self.y.k()), (idx + 1, 0)]));
        Ok((st, ms))
    }

    fn deleg_statements_full(&self, Cp: &G1Affine, nymD: &G1Affine, epoch: u64, j: u64, prover: bool) -> Result<(Statements<E>, MetaStatements), String> {
        let (st, ms) = self.deleg_statements(Cp, nymD, j, prover)?;
        // rebuild with the right pseudonym base (statements are append-only; reconstruct)
        let mut st2 = Statements::<E>::new();
        let n = st.0.len();
        for (i, s) in st.0.into_iter().enumerate() {
            if i == n - 2 { st2.add(PedStmt::new_statement_from_params(vec![deleg_base(epoch, j)], *nymD)); } else { st2.add(s); }
        }
        Ok((st2, ms))
    }

    fn deleg_proof(&self, rng: &mut StdRng, p: &Mandate, c: &Attrs, r2: Fr, Cp: &G1Affine, nymD: &G1Affine, epoch: u64, j: u64, ctx: &[u8]) -> Result<Proof<E>, String> {
        let (st, ms) = self.deleg_statements_full(Cp, nymD, epoch, j, true)?;
        let pm = p.msgs();
        let cmv: BTreeMap<usize, Fr> = c.msgs_1_uid().into_iter().collect();
        let mut w = Witnesses::new();
        w.add(BbsWit::new_as_witness(p.sig.clone(), pm.iter().enumerate().map(|(i, v)| (i, *v)).collect()));
        for (i, id) in p.ids().iter().enumerate() {
            w.add(Witness::VBAccumulatorNonMembership(NonMemWit { element: fr(*id), witness: p.nm[i].clone() }));
        }
        let mut cw = vec![r2];
        for i in I_ID..=self.y.uid() { cw.push(cmv[&i]); }
        w.add(Witness::PedersenCommitment(cw));
        w.add(Witness::PedersenCommitment(vec![cmv[&I_DEPTH], pm[I_DEPTH]]));
        w.add(Witness::BoundCheckBpp(cmv[&I_DEPTH]));
        let mut items: Vec<usize> = vec![self.y.budget(), self.y.k(), self.y.exp()];
        for cc in 0..self.y.n { items.push(I_SCOPE + cc); }
        for mi in items {
            let d = pm[mi] - cmv[&mi] + Fr::one();
            w.add(Witness::PedersenCommitment(vec![d, cmv[&mi], pm[mi]]));
            w.add(Witness::BoundCheckBpp(d));
        }
        w.add(Witness::PedersenCommitment(vec![p.s]));
        w.add(Witness::BoundCheckBpp(pm[self.y.k()]));
        let spec = ProofSpec::new(st, ms, vec![], Some(ctx.to_vec()));
        Ok(guard(|| Proof::new::<StdRng, Blake2b512>(rng, spec, w, None, Default::default()).map_err(|e| format!("deleg prove: {e:?}")))?.0)
    }

    fn deleg_verify(&self, rng: &mut StdRng, Cp: &G1Affine, nymD: &G1Affine, epoch: u64, j: u64, pf: &Proof<E>, ctx: &[u8]) -> Result<(), String> {
        let (st, ms) = self.deleg_statements_full(Cp, nymD, epoch, j, false)?;
        let spec = ProofSpec::new(st, ms, vec![], Some(ctx.to_vec()));
        pf.clone().verify::<StdRng, Blake2b512>(rng, spec, None, Default::default()).map_err(|e| format!("deleg verify: {e:?}"))
    }

    /// Revoke a batch of ids; returns (omega, additions) for holders.
    pub fn revoke(&mut self, ids: &[u64]) -> Result<(Omega<G1Affine>, Vec<Fr>), String> {
        let add: Vec<Fr> = ids.iter().map(|i| fr(*i)).collect();
        let old = *self.acc.value();
        let omega = Omega::new(&add, &[], &old, &self.akp.secret_key);
        self.acc = self.acc.add_batch(add.clone(), &self.akp.secret_key, &self.init, &mut self.state).map_err(|e| format!("{e:?}"))?;
        self.revoked.extend(add.iter().cloned());
        Ok((omega, add))
    }

    /// Escrow: share i (0-based) with a Chaum–Pedersen proof; open with two shares; judge.
    pub fn share(&self, rng: &mut StdRng, i: usize, c1: &G1Affine) -> (G1Affine, (Fr, Fr)) {
        let xi = self.esc.shares[i];
        let D = (c1.into_group() * xi).into_affine();
        let w = Fr::rand(rng);
        let a1 = (self.g.into_group() * w).into_affine();
        let a2 = (c1.into_group() * w).into_affine();
        let ch = cp_challenge(&self.g, c1, &self.esc.X[i], &D, &a1, &a2);
        (D, (ch, w + ch * xi))
    }
    pub fn judge_share(&self, i: usize, c1: &G1Affine, D: &G1Affine, pf: &(Fr, Fr)) -> bool {
        let (ch, z) = *pf;
        let a1 = (self.g.into_group() * z - self.esc.X[i].into_group() * ch).into_affine();
        let a2 = (c1.into_group() * z - D.into_group() * ch).into_affine();
        cp_challenge(&self.g, c1, &self.esc.X[i], D, &a1, &a2) == ch
    }
    /// Returns g^uid from two shares (indices 0-based).
    pub fn open(&self, c2: &G1Affine, s: [(usize, G1Affine); 2]) -> G1Affine {
        let (l0, l1) = lagrange_at0(s[0].0 as u64 + 1, s[1].0 as u64 + 1);
        let k = s[0].1.into_group() * l0 + s[1].1.into_group() * l1;
        (c2.into_group() - k).into_affine()
    }
    pub fn g_uid(&self, uid: u64) -> G1Affine { (self.g.into_group() * fr(uid)).into_affine() }
}

fn cp_challenge(g: &G1Affine, c1: &G1Affine, X: &G1Affine, D: &G1Affine, a1: &G1Affine, a2: &G1Affine) -> Fr {
    let mut b = vec![];
    for p in [g, c1, X, D, a1, a2] { p.serialize_compressed(&mut b).unwrap(); }
    Fr::from_le_bytes_mod_order(&Sha256::digest(&b))
}

pub fn ped_pok(rng: &mut StdRng, bases: &[G1Affine], C: &G1Affine, w: Vec<Fr>, ctx: &[u8]) -> Result<Proof<E>, String> {
    let mut st = Statements::<E>::new();
    st.add(PedStmt::new_statement_from_params(bases.to_vec(), *C));
    let spec = ProofSpec::new(st, MetaStatements::new(), vec![], Some(ctx.to_vec()));
    let mut ws = Witnesses::new();
    ws.add(Witness::PedersenCommitment(w));
    Ok(Proof::new::<StdRng, Blake2b512>(rng, spec, ws, None, Default::default()).map_err(|e| format!("{e:?}"))?.0)
}
pub fn ped_verify(rng: &mut StdRng, bases: &[G1Affine], C: &G1Affine, pf: &Proof<E>, ctx: &[u8]) -> Result<(), String> {
    let mut st = Statements::<E>::new();
    st.add(PedStmt::new_statement_from_params(bases.to_vec(), *C));
    let spec = ProofSpec::new(st, MetaStatements::new(), vec![], Some(ctx.to_vec()));
    pf.clone().verify::<StdRng, Blake2b512>(rng, spec, None, Default::default()).map_err(|e| format!("{e:?}"))
}

pub fn rng(seed: u64) -> StdRng { StdRng::seed_from_u64(seed) }
pub fn _unused(_: G1Projective) {}

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
}

/// Some sub-protocols panic instead of returning an error when the witness is invalid
/// (e.g. a non-membership witness for a member). Treat a panic as "the prover cannot build the proof".
pub fn guard<T>(f: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(|_| {}));
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));
    std::panic::set_hook(prev);
    match r { Ok(x) => x, Err(_) => Err("prover cannot build the proof (invalid witness)".into()) }
}

impl Presentation {
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut b = vec![];
        self.nym.serialize_compressed(&mut b).unwrap();
        b.extend_from_slice(&self.j.to_le_bytes());
        match &self.esc { Some((c1, c2)) => { b.push(1); c1.serialize_compressed(&mut b).unwrap(); c2.serialize_compressed(&mut b).unwrap(); } None => b.push(0) }
        self.proof.serialize_compressed(&mut b).unwrap();
        b
    }
    pub fn from_bytes(b: &[u8]) -> Result<Self, String> {
        use ark_serialize::CanonicalDeserialize;
        let mut rd = b;
        let nym = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
        if rd.len() < 9 { return Err("short".into()); }
        let j = u64::from_le_bytes(rd[..8].try_into().unwrap()); rd = &rd[8..];
        let flag = rd[0]; rd = &rd[1..];
        let esc = if flag == 1 {
            let c1 = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
            let c2 = G1Affine::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
            Some((c1, c2))
        } else { None };
        let proof = Proof::<E>::deserialize_compressed(&mut rd).map_err(|e| e.to_string())?;
        Ok(Presentation { nym, j, esc, proof })
    }
}
