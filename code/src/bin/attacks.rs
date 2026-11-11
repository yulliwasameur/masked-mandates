//! Attack suite (A2–A6) and correctness checks. Output: results/attacks.json
use vb_accumulator::prelude::Accumulator;
use ark_bls12_381::{Fr, G1Affine};
use ark_ec::{AffineRepr, CurveGroup};
use ark_ff::Field;
use ark_std::UniformRand;
use mmcore::*;
use serde_json::json;

/// Principals registered with the escrow committee.
const REGISTERED: &[u64] = &[7, 9, 42, 43];

struct Ctx { sys: System, r: rand::rngs::StdRng }

fn scope(cls: &[usize]) -> Vec<bool> { let mut s = vec![false; NCLS]; for &c in cls { s[c] = true; } s }
fn inv(tool: &str, class: usize, amt: u64, epoch: u64, t: u64, nonce: &str) -> Invocation {
    Invocation { tool: tool.into(), call: format!("{{\"arguments\":{{\"amt\":{amt}}},\"name\":\"op{class}\"}}"), class, amt, epoch, t, nonce: nonce.into() }
}
/// Outcome of an attempted attack: who stopped it.
fn outcome(r: Result<Result<(), String>, String>) -> (bool, &'static str, String) {
    match r {
        // errors raised by the issuer's checks (delegation proof, child PoK, seen-set, root attributes)
        Err(e) if ["deleg verify", "child pok", "delegation pseudonym replay", "root:"].iter().any(|p| e.starts_with(p)) => (true, "issuer", e),
        Err(e) => (true, "prover", e),
        Ok(Err(e)) => (true, "verifier", e),
        Ok(Ok(())) => (false, "ACCEPTED", String::new()),
    }
}

fn main() {
    let seed = 20261109;
    let mut c = Ctx { sys: System::setup(&mut rng(seed), 1000), r: rng(seed + 1) };
    let r = &mut c.r;
    let sys = &mut c.sys;
    let root_a = Attrs { id: 101, anc: [0; 4], depth: 0, scope: scope(&[0, 1, 2]), budget: 800, k: 3, exp: 2_000_000, uid: 42 };
    let root = sys.issue_root(r, &root_a).unwrap();
    let child_a = Attrs { id: 0, anc: [101, 0, 0, 0], depth: 1, scope: scope(&[1]), budget: 300, k: 2, exp: 1_500_000, uid: 42 };
    let (child, _, _) = sys.delegate(r, &root, &child_a, 7, 0).unwrap();
    let gc_a = Attrs { id: 0, anc: [child.a.id, 101, 0, 0], depth: 2, scope: scope(&[1]), budget: 100, k: 1, exp: 1_400_000, uid: 42 };
    let (gchild, _, _) = sys.delegate(r, &child, &gc_a, 7, 0).unwrap();

    let mut checks = vec![];
    let mut attacks = vec![];
    let mut n = 0u32;
    let mut nonce = || { n += 1; format!("n{n}") };

    // ---------------- correctness checks ----------------
    let mut tool = Tool::new("hotel", false);
    let mut etool = Tool::new("pay", true);
    // depths 0..4 (build a chain up to depth 4)
    let mut chain = vec![];
    let mut cur = sys.issue_root(r, &Attrs { id: 1000, anc: [0; 4], depth: 0, scope: scope(&[1]), budget: 500, k: 4, exp: 2_000_000, uid: 7 }).unwrap();
    for d in 1..=4u64 {
        let a = Attrs { id: 1000 + d, anc: { let mut x = [0u64; 4]; x[0] = cur.a.id; x[1] = cur.a.anc[0]; x[2] = cur.a.anc[1]; x[3] = cur.a.anc[2]; x },
                        depth: d, scope: scope(&[1]), budget: 500 - d * 50, k: 4, exp: 2_000_000 - d, uid: 7 };
        let (m, _, _) = sys.delegate(r, &cur, &a, 7, 0).unwrap();
        chain.push(std::mem::replace(&mut cur, m));
    }
    chain.push(cur);
    for m in &chain {
        let i = inv("hotel", 1, 10, 7, 1_000_000, &nonce());
        let ok = sys.present(r, m, &i, 0, false).and_then(|p| sys.verify(r, &mut tool, &i, &p)).is_ok();
        checks.push(json!({"check": format!("honest presentation, depth {}", m.a.depth), "ok": ok}));
    }
    for (name, m) in [("escrow presentation, root", &root), ("escrow presentation, depth 2", &gchild)] {
        let i = inv("pay", 1, 50, 7, 1_000_000, &nonce());
        let ok = sys.present(r, m, &i, 0, true).and_then(|p| sys.verify(r, &mut etool, &i, &p)).is_ok();
        checks.push(json!({"check": name, "ok": ok}));
    }
    // within quota: root k=3, counters 0,1,2 at a fresh tool
    let mut qtool = Tool::new("air", false);
    let okq = (0..3).all(|j| { let i = inv("air", 0, 10, 7, 1_000_000, &nonce()); sys.present(r, &root, &i, j, false).and_then(|p| sys.verify(r, &mut qtool, &i, &p)).is_ok() });
    checks.push(json!({"check": "all k=3 counters accepted within quota", "ok": okq}));
    // 2-of-3 openings, all pairs, and judge
    let i = inv("pay", 1, 50, 8, 1_000_000, &nonce());
    let p = sys.present(r, &gchild, &i, 0, true).unwrap();
    sys.verify(r, &mut etool, &i, &p).unwrap();
    let (c1, c2) = p.esc.unwrap();
    for (a, b) in [(0usize, 1usize), (0, 2), (1, 2)] {
        let (da, pa) = sys.share(r, a, &c1); let (db, pb) = sys.share(r, b, &c1);
        let ok = sys.judge(&c1, &c2, [(a, da, pa), (b, db, pb)], REGISTERED) == Ok(42);
        checks.push(json!({"check": format!("2-of-3 opening with members {}+{} returns the root principal", a + 1, b + 1), "ok": ok}));
    }

    // delegated identifiers are drawn at random by the parent (Sec. IV, Delegate)
    { let ids: Vec<u64> = [&child, &gchild].iter().map(|m| m.a.id).chain(chain[1..].iter().map(|m| m.a.id)).collect();
      let mut u = ids.clone(); u.sort(); u.dedup();
      checks.push(json!({"check": "delegated identifiers are random, non-zero and distinct (none equals the value requested by the caller)",
                         "ok": u.len() == ids.len() && ids.iter().all(|&x| x != 0 && x != 202 && x != 303 && !(1001..=1004).contains(&x))})); }
    // ---------------- attacks ----------------
    macro_rules! atk { ($cls:expr, $name:expr, $res:expr) => {{ let (rej, by, why) = outcome($res); attacks.push(json!({"class": $cls, "attack": $name, "rejected": rej, "by": by, "detail": why.chars().take(120).collect::<String>()})); }} }
    // atk_cause!: the attack counts as rejected only if it fails for the expected reason
    // (e.g. the non-membership statement of the revoked ancestor, not a stale witness of the holder itself).
    macro_rules! atk_cause { ($cls:expr, $name:expr, $res:expr, $why:expr) => {{ let (rej, by, why) = outcome($res);
        let good = rej && why.contains($why);
        attacks.push(json!({"class": $cls, "attack": $name, "rejected": good, "by": if good { by } else if rej { "OTHER CAUSE" } else { by },
                            "expected_cause": $why, "detail": why.chars().take(120).collect::<String>()})); }} }
    let mut t1 = Tool::new("hotel2", false);
    let mut t2 = Tool::new("air2", false);
    let pv = |sys: &System, r: &mut rand::rngs::StdRng, m: &Mandate, i: &Invocation, j: u64, e: bool, t: &mut Tool| -> Result<Result<(), String>, String> {
        let p = sys.present(r, m, i, j, e)?; Ok(sys.verify(r, t, i, &p))
    };
    // A2 — overreach by a compromised agent
    atk!("A2", "class outside the mandate's scope", pv(sys, r, &child, &inv("hotel2", 2, 10, 7, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A2", "amount above budget", pv(sys, r, &child, &inv("hotel2", 1, 301, 7, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A2", "use after expiry", pv(sys, r, &child, &inv("hotel2", 1, 10, 7, 1_500_001, &nonce()), 0, false, &mut t1));
    { let mut m2 = Mandate { s: child.s, a: child.a.clone(), ver: child.ver, sig: child.sig.clone(), nm: child.nm.clone() }; m2.a.budget = 10_000;
      atk!("A2", "inflate budget under an existing signature", pv(sys, r, &m2, &inv("hotel2", 1, 5_000, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    { let mut m2 = Mandate { s: child.s, a: child.a.clone(), ver: child.ver, sig: child.sig.clone(), nm: child.nm.clone() }; m2.a.scope = scope(&[1, 2]);
      atk!("A2", "add a scope bit under an existing signature", pv(sys, r, &m2, &inv("hotel2", 2, 5, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    { let other = System::setup(&mut rng(99), 10); let mut rr = rng(5);
      let mut o = other; let fake = o.issue_root(&mut rr, &Attrs { id: 9, anc: [0;4], depth: 0, scope: scope(&[0,1,2,3]), budget: 1<<30, k: 100, exp: 9_000_000, uid: 1 }).unwrap();
      let fm = Mandate { s: fake.s, a: fake.a.clone(), ver: fake.ver, sig: fake.sig.clone(), nm: child.nm.clone() };
      atk!("A2", "mandate signed by an unrecognised issuer", pv(sys, r, &fm, &inv("hotel2", 1, 10, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    let mut dj = 1u64;
    let mut dl = |sys: &mut System, r: &mut rand::rngs::StdRng, p: &Mandate, a: Attrs| -> Result<Result<(), String>, String> { dj += 1; sys.delegate(r, p, &a, 100 + dj, 0).map(|_| Ok(())) };
    let base = || Attrs { id: 5000, anc: [101, 0, 0, 0], depth: 1, scope: scope(&[1]), budget: 100, k: 2, exp: 1_000_000, uid: 42 };
    atk!("A2", "delegation: child gets a class the parent lacks", dl(sys, r, &root, Attrs { id: 5001, scope: scope(&[1, 5]), ..base() }));
    atk!("A2", "delegation: child budget above parent", dl(sys, r, &root, Attrs { id: 5002, budget: 801, ..base() }));
    atk!("A2", "delegation: child quota above parent", dl(sys, r, &root, Attrs { id: 5003, k: 4, ..base() }));
    atk!("A2", "delegation: child expiry after parent", dl(sys, r, &root, Attrs { id: 5004, exp: 2_000_001, ..base() }));
    atk!("A2", "delegation: depth skip (+2)", dl(sys, r, &root, Attrs { id: 5005, depth: 2, ..base() }));
    atk!("A2", "delegation: beyond maximum depth 4", dl(sys, r, &chain[4], Attrs { id: 5006, depth: 5, anc: [chain[4].a.id, chain[4].a.anc[0], chain[4].a.anc[1], chain[4].a.anc[2]], scope: scope(&[1]), budget: 10, k: 1, exp: 1_000, uid: 7 }));
    atk!("A2", "delegation: ancestry erasure (anc' cleared)", dl(sys, r, &child, Attrs { id: 5007, depth: 2, anc: [0, 0, 0, 0], scope: scope(&[1]), budget: 10, k: 1, exp: 1_000, uid: 42 }));
    atk!("A2", "delegation: ancestry rewrite (wrong grandparent)", dl(sys, r, &child, Attrs { id: 5008, depth: 2, anc: [child.a.id, 999, 0, 0], scope: scope(&[1]), budget: 10, k: 1, exp: 1_000, uid: 42 }));
    atk!("A2", "delegation: principal change (uid')", dl(sys, r, &root, Attrs { id: 5009, uid: 43, ..base() }));
    { let mut fp = Mandate { s: root.s, a: root.a.clone(), ver: root.ver, sig: root.sig.clone(), nm: root.nm.clone() }; fp.a.budget = 1 << 30;
      atk!("A2", "delegation from a forged parent (attributes not signed)", dl(sys, r, &fp, Attrs { id: 5010, budget: 1 << 29, ..base() })); }
    // mix-and-match (Thm. 1, case i): a parent's delegation proof is bound to the session context
    // H(issuer nonce, Cc, Cp); it cannot be reused with another child commitment or in another session.
    {   let n1 = b"issuer-session-1".to_vec();
        let a = Attrs { id: 5011, ..base() };
        let (req, _sec) = sys.deleg_request(r, &root, &a, 21, 0, &n1).unwrap();
        // adversarial child: fresh commitment with a valid PoK under the new context, parent proof unchanged
        let s3 = Fr::rand(r); let r3 = Fr::rand(r);
        let cc3 = sys.sp.commit_to_messages(vec![(I_S, &s3)], &r3).unwrap();
        let cpf3 = sys.child_pok(r, &cc3, r3, s3, &deleg_ctx(&n1, &cc3, &req.Cp)).unwrap();
        let swapped = DelegReq { Cc: cc3, Cp: req.Cp, nymD: req.nymD, epoch: req.epoch, j: req.j, pf: req.pf.clone(), cpf: cpf3 };
        atk_cause!("A2", "delegation proof reused with another child commitment", sys.deleg_issue(r, &swapped, &n1).map(|_| Ok(())), "deleg verify");
        let n2 = b"issuer-session-2".to_vec();
        atk_cause!("A2", "delegation request replayed in a new issuer session", sys.deleg_issue(r, &req, &n2).map(|_| Ok(())), "deleg verify"); }
    // A3 — replay
    let i_ok = inv("hotel2", 1, 10, 9, 1_000_000, &nonce());
    let p_ok = sys.present(r, &child, &i_ok, 0, false).unwrap();
    sys.verify(r, &mut t1, &i_ok, &p_ok).unwrap();
    atk!("A3", "same presentation, same tool (replay)", Ok(sys.verify(r, &mut t1, &i_ok, &p_ok)));
    atk!("A3", "same presentation sent to another tool", Ok(sys.verify(r, &mut t2, &Invocation { tool: "air2".into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "same proof, different call arguments", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &Invocation { call: "{\"name\":\"op1\",\"arguments\":{\"amt\":999}}".into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "same proof, different tool nonce", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &Invocation { nonce: "other".into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "same proof, another epoch", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &Invocation { epoch: 10, ..i_ok.clone() }, &p_ok)));
    atk!("A3", "same proof, larger amount", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &Invocation { amt: 299, ..i_ok.clone() }, &p_ok)));
    atk!("A3", "same proof, other action class", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &Invocation { class: 0, ..i_ok.clone() }, &p_ok)));
    // A4 — rate abuse
    atk!("A4", "reuse a counter j within the epoch (fresh proof)", pv(sys, r, &child, &inv("hotel2", 1, 10, 9, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A4", "counter j = k (beyond quota)", pv(sys, r, &child, &inv("hotel2", 1, 10, 9, 1_000_000, &nonce()), 2, false, &mut t1));
    atk!("A4", "counter j far beyond quota", pv(sys, r, &child, &inv("hotel2", 1, 10, 9, 1_000_000, &nonce()), 1000, false, &mut t1));
    { let mut pp = p_ok.clone(); pp.j = 1;
      atk!("A4", "claim another counter for an existing proof", Ok(sys.verify(r, &mut Tool::new("hotel2", false), &i_ok, &pp))); }
    { let mut pp = p_ok.clone(); pp.nym = (pp.nym.into_group() * Fr::from(2u64)).into_affine();
      atk!("A4", "re-randomise the pseudonym of an accepted proof", Ok(sys.verify(r, &mut t1, &i_ok, &pp))); }
    atk!("A4", "delegation pseudonym reuse (same epoch and counter)", sys.delegate(r, &root, &Attrs { id: 5012, ..base() }, 7, 0).map(|_| Ok(())));
    atk!("A4", "delegation counter beyond the parent's quota", sys.delegate(r, &root, &Attrs { id: 5013, ..base() }, 7, 3).map(|_| Ok(())));
    // A5 — revocation. Holders refresh every witness they can from public data (refresh_partial);
    // a witness for a just-revoked identifier cannot be refreshed. Each attack must fail on the
    // non-membership statement of the revoked identifier: presentation statements 5 (own id), 6 (anc1), 7 (anc2);
    // delegation statements 1 (parent id), 2 (parent's anc1).
    let gc2_a = Attrs { id: 0, anc: [child.a.id, 101, 0, 0], depth: 2, scope: scope(&[1]), budget: 50, k: 1, exp: 1_400_000, uid: 42 };
    let (gc2, _, _) = sys.delegate(r, &child, &gc2_a, 8, 0).unwrap();
    let old_acc: G1Affine = *sys.acc.value();
    let (om, ad) = sys.revoke(&[gchild.a.id]).unwrap();
    let mut root = root; let mut child = child; let mut gchild = gchild; let mut gc2 = gc2;
    root.refresh(&ad, &om).unwrap(); child.refresh(&ad, &om).unwrap(); gc2.refresh(&ad, &om).unwrap();
    let stuck_gc = gchild.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a revocation, the revoked holder cannot refresh its own witness (only position 0 is stuck)", "ok": stuck_gc == vec![0]}));
    { let i = inv("hotel2", 1, 10, 11, 1_000_000, &nonce());
      let ok = sys.present(r, &gc2, &i, 0, false).and_then(|p| sys.verify(r, &mut t1, &i, &p)).is_ok();
      checks.push(json!({"check": "honest presentation after a revocation (sibling of the revoked mandate, refreshed witnesses)", "ok": ok})); }
    let grefok = { let mut g = Mandate { s: gchild.s, a: gchild.a.clone(), ver: gchild.ver, sig: gchild.sig.clone(), nm: gchild.nm.clone() };
        g.refresh(&ad, &om).is_ok() && sys.acc.verify_non_membership(&fr(gchild.a.id), &g.nm[0], &sys.akp.public_key, &sys.ap) };
    atk!("A5", "refresh the witness of a revoked id from public data", Ok(if grefok { Ok(()) } else { Err("refreshed witness does not verify".into()) }));
    atk_cause!("A5", "present after own revocation", pv(sys, r, &gchild, &inv("hotel2", 1, 10, 11, 1_000_000, &nonce()), 0, false, &mut t1), "VBAccumProofContributionFailed(5,");
    atk!("A5", "present with a stale accumulator value", { let i = inv("hotel2", 1, 10, 11, 1_000_000, &nonce());
        sys.present_cheat(r, &gchild, &i, 0, false, &Cheat { acc_value: Some(old_acc), ..Default::default() }).map(|p| sys.verify(r, &mut t1, &i, &p)) });
    // revoke the parent (child.a.id): its child gc2 is not revoked itself and refreshes its own witness
    let (om, ad) = sys.revoke(&[child.a.id]).unwrap(); root.refresh(&ad, &om).unwrap();
    let stuck_c = child.refresh_partial(&ad, &om);
    let stuck_gc2 = gc2.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a parent revocation, the child refreshes its own witness but not the parent's (only position 1 is stuck)", "ok": stuck_gc2 == vec![1] && stuck_c == vec![0]}));
    atk_cause!("A5", "present after parent revocation (own witness up to date)", pv(sys, r, &gc2, &inv("hotel2", 1, 10, 12, 1_000_000, &nonce()), 0, false, &mut t1), "VBAccumProofContributionFailed(6,");
    atk_cause!("A5", "delegate after own revocation", sys.delegate(r, &child, &Attrs { id: 5014, depth: 2, anc: [child.a.id, 101, 0, 0], scope: scope(&[1]), budget: 10, k: 1, exp: 1_000, uid: 42 }, 12, 1).map(|_| Ok(())), "VBAccumProofContributionFailed(1,");
    // grandparent revocation: chain 7000 (root) -> g1 -> g2, revoke 7000
    let g0 = sys.issue_root(r, &Attrs { id: 7000, anc: [0; 4], depth: 0, scope: scope(&[1]), budget: 100, k: 2, exp: 2_000_000, uid: 9 }).unwrap();
    let (g1, _, _) = sys.delegate(r, &g0, &Attrs { id: 7001, anc: [7000, 0, 0, 0], depth: 1, scope: scope(&[1]), budget: 90, k: 2, exp: 1_900_000, uid: 9 }, 13, 0).unwrap();
    let (g2, _, _) = sys.delegate(r, &g1, &Attrs { id: 7002, anc: [g1.a.id, 7000, 0, 0], depth: 2, scope: scope(&[1]), budget: 80, k: 2, exp: 1_800_000, uid: 9 }, 13, 0).unwrap();
    let (om, ad) = sys.revoke(&[7000]).unwrap(); root.refresh(&ad, &om).unwrap();
    let (mut g1, mut g2) = (g1, g2);
    let stuck_g1 = g1.refresh_partial(&ad, &om); let stuck_g2 = g2.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a root revocation, descendants refresh all witnesses except the root's (positions 1 and 2)", "ok": stuck_g1 == vec![1] && stuck_g2 == vec![2]}));
    atk_cause!("A5", "present after grandparent revocation (own and parent witnesses up to date)", pv(sys, r, &g2, &inv("hotel2", 1, 10, 13, 1_000_000, &nonce()), 0, false, &mut t1), "VBAccumProofContributionFailed(7,");
    atk_cause!("A5", "child of a revoked root delegates a new sub-agent", sys.delegate(r, &g1, &Attrs { id: 7003, anc: [g1.a.id, 7000, 0, 0], depth: 2, scope: scope(&[1]), budget: 70, k: 1, exp: 1_700_000, uid: 9 }, 14, 1).map(|_| Ok(())), "VBAccumProofContributionFailed(2,");
    checks.push(json!({"check": "identifier 0 (no ancestor) cannot be revoked", "ok": sys.revoke(&[0]).is_err()}));
    // A6 — accountability. Openings go through the full Judge (distinct members, Chaum–Pedersen proofs,
    // registered principal). Member 1 (index 0) is corrupt; the target is principal 43, who made no presentation.
    let mut pt = Tool::new("pay2", true);
    atk!("A6", "escrow ciphertext encrypts another principal", { let i = inv("pay2", 1, 10, 14, 1_000_000, &nonce());
        sys.present_cheat(r, &root, &i, 0, true, &Cheat { esc_uid: Some(43), ..Default::default() }).map(|p| sys.verify(r, &mut pt, &i, &p)) });
    atk!("A6", "omit escrow where the tool requires it", { let i = inv("pay2", 1, 10, 14, 1_000_000, &nonce()); sys.present(r, &root, &i, 0, false).map(|p| sys.verify(r, &mut pt, &i, &p)) });
    let i6 = inv("pay2", 0, 10, 15, 1_000_000, &nonce());
    let p6 = sys.present(r, &root, &i6, 0, true).unwrap();
    sys.verify(r, &mut pt, &i6, &p6).unwrap();
    let (c1, c2) = p6.esc.unwrap();
    let judged = |res: Result<u64, String>| -> Result<Result<(), String>, String> { Ok(match res { Ok(u) if u == 43 => Ok(()), Ok(u) => Err(format!("Judge opens to {u}, not the target")), Err(e) => Err(e) }) };
    let (d0, pf0) = sys.share(r, 0, &c1); let (d1, pf1) = sys.share(r, 1, &c1);
    let (l0, l1) = lagrange_at0(1, 2);
    // share for member 2 such that c2 / (D1^l0 D2^l1) = g^43
    let d1_forged = ((c2.into_group() - sys.g_uid(43).into_group() - d0.into_group() * l0) * l1.inverse().unwrap()).into_affine();
    atk_cause!("A6", "corrupt member forges the second share to frame principal 43 (reuses the honest proof)", judged(sys.judge(&c1, &c2, [(0, d0, pf0), (1, d1_forged, pf1)], REGISTERED)), "invalid share proof from member 2");
    atk_cause!("A6", "corrupt member forges the second share to frame principal 43 (random proof)", judged(sys.judge(&c1, &c2, [(0, d0, pf0), (1, d1_forged, (Fr::rand(r), Fr::rand(r)))], REGISTERED)), "invalid share proof from member 2");
    { let d0_bad = (d0.into_group() * Fr::from(3u64)).into_affine();
      atk_cause!("A6", "malicious member submits a wrong decryption share", judged(sys.judge(&c1, &c2, [(0, d0_bad, pf0), (1, d1, pf1)], REGISTERED)), "invalid share proof from member 1"); }
    { let (_, pf2) = sys.share(r, 2, &c1);
      atk_cause!("A6", "share with a proof made for another member", judged(sys.judge(&c1, &c2, [(0, d0, pf0), (1, d1, pf2)], REGISTERED)), "invalid share proof from member 2"); }
    atk_cause!("A6", "corrupt member submits its own share twice", judged(sys.judge(&c1, &c2, [(0, d0, pf0), (0, d0, pf0)], REGISTERED)), "two distinct committee members");
    { let i = inv("pay2", 1, 10, 16, 1_000_000, &nonce()); let mut p = sys.present(r, &root, &i, 0, true).unwrap(); p.esc = Some((c1, c2));
      atk!("A6", "graft another presentation's escrow ciphertext", Ok(sys.verify(r, &mut pt, &i, &p))); }

    let n_att = attacks.len();
    let n_rej = attacks.iter().filter(|a| a["rejected"] == true).count();
    let n_chk = checks.len();
    let n_ok = checks.iter().filter(|c| c["ok"] == true).count();
    let out = json!({"seed": seed, "attacks": attacks, "checks": checks, "n_attacks": n_att, "n_rejected": n_rej, "n_checks": n_chk, "n_checks_ok": n_ok});
    std::fs::create_dir_all("results").unwrap();
    std::fs::write("results/attacks.json", serde_json::to_string_pretty(&out).unwrap()).unwrap();
    println!("attacks rejected {}/{} ; checks ok {}/{}", n_rej, n_att, n_ok, n_chk);
    for a in out["attacks"].as_array().unwrap() { if a["rejected"] == false { println!("NOT REJECTED: {}", a["attack"]); } }
    for c in out["checks"].as_array().unwrap() { if c["ok"] == false { println!("CHECK FAILED: {}", c["check"]); } }
}
