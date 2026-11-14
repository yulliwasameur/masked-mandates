//! Attack suite (A2–A6, plus malicious-prover and mutation tests) and correctness checks, version 2.
//! Output: results/attacks.json. Each attack records who stopped it (prover, verifier, issuer, Judge, parser)
//! and the mechanism that stops it, so that the paper reports a taxonomy rather than a count.
use ark_bls12_381::{Fr, G1Affine};
use ark_ec::{AffineRepr, CurveGroup};
use ark_ff::Field;
use ark_std::{rand::RngCore, UniformRand};
use bbs_plus::prelude::SignatureG1;
use mmcore::*;
use ark_serialize::CanonicalSerialize;
use serde_json::json;

fn scope(cls: &[usize]) -> Vec<bool> { let mut s = vec![false; NCLS]; for &c in cls { s[c] = true; } s }
fn inv(tool: &str, class: usize, amt: u64, epoch: u64, t: u64, nonce: &str) -> Invocation {
    Invocation { tool: tool.into(), call: format!("{{\"arguments\":{{\"amt\":{amt}}},\"name\":\"op{class}\"}}"), class, amt, cur: "EUR".into(), epoch, t, nonce: nonce.into() }
}
type R = Result<Result<(), String>, String>;
/// Outcome: who stopped the attempt.
fn outcome(r: R) -> (bool, &'static str, String) {
    match r {
        Err(e) if ["deleg verify", "delegation pseudonym replay", "delegation: epoch", "root:", "root pok"].iter().any(|p| e.starts_with(p)) => (true, "issuer", e),
        Err(e) if e.starts_with("log") => (true, "log", e),
        Err(e) if e.starts_with("Judge") => (true, "Judge", e),
        Err(e) if e.starts_with("parse") => (true, "parser", e),
        Err(e) => (true, "prover", e),
        Ok(Err(e)) if e.starts_with("Judge") => (true, "Judge", e),
        Ok(Err(e)) if e.starts_with("log") => (true, "log", e),
        Ok(Err(e)) => (true, "verifier", e),
        Ok(Ok(())) => (false, "ACCEPTED", String::new()),
    }
}
fn clone_m(m: &Mandate) -> Mandate { m.clone() }

fn main() {
    let seed = 20261109;
    let mut sys = System::setup(&mut rng(seed), 1000);
    let r = &mut rng(seed + 1);
    for l in [7, 9, 42, 43] { sys.register(r, l); }
    let root = sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[0, 1, 2]), lo: 0, budget: 800, k: 6, exp: 2_000_000, uid: 42 }).unwrap();
    let (child, _, _) = sys.delegate(r, &root, &Attrs::child_of(&root.a, scope(&[1]), 300, 4, 1_500_000), 7, 0).unwrap();
    let (gchild, _, _) = sys.delegate(r, &child, &Attrs::child_of(&child.a, scope(&[1]), 100, 2, 1_400_000), 7, 1).unwrap();

    let mut checks = vec![];
    let mut attacks = vec![];
    let mut n = 0u32;
    let mut nonce = || { n += 1; format!("n{n}") };

    // ---------------- correctness checks ----------------
    let mut tool = Tool::new("https://hotel.example|search", false);
    let mut etool = Tool::new("https://pay.example|pay", true);
    let mut chain = vec![];
    let mut cur = sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 500, k: 8, exp: 2_000_000, uid: 7 }).unwrap();
    for d in 1..=4u64 {
        let a = Attrs::child_of(&cur.a, scope(&[1]), 500 - d * 50, 8, 2_000_000 - d);
        let (m, _, _) = sys.delegate(r, &cur, &a, 7, d - 1).unwrap();
        chain.push(std::mem::replace(&mut cur, m));
    }
    chain.push(cur);
    for (j, m) in chain.iter().enumerate() {
        let i = inv(&tool.name.clone(), 1, 10, 7, 1_000_000, &nonce());
        let ok = sys.present(r, m, &i, j as u64, false).and_then(|p| sys.verify(r, &mut tool, &i, &p)).is_ok();
        checks.push(json!({"check": format!("honest presentation, depth {}", m.a.depth), "ok": ok}));
    }
    for (name, m, j) in [("escrow presentation, root", &root, 0u64), ("escrow presentation, depth 2", &gchild, 1)] {
        let i = inv(&etool.name.clone(), 1, 50, 7, 1_000_000, &nonce());
        let ok = sys.present(r, m, &i, j, true).and_then(|p| sys.verify(r, &mut etool, &i, &p)).is_ok();
        checks.push(json!({"check": name, "ok": ok}));
    }
    // the whole subtree shares the root's quota k = 6 at a tool and epoch: 6 distinct counters accepted, across members
    let mut qtool = Tool::new("https://air.example|book", false);
    // each member uses every counter of its own part of the interval (root: [lo, child.lo); child: [child.lo, gchild.lo); gchild: its interval)
    let okq = [(&root, child.a.lo - root.a.lo), (&child, gchild.a.lo - child.a.lo), (&gchild, gchild.a.k - gchild.a.lo)].iter().all(|(m, n)| (0..*n).all(|j| {
        let i = inv(&qtool.name.clone(), 1, 10, 7, 1_000_000, &nonce()); sys.present(r, m, &i, j, false).and_then(|p| sys.verify(r, &mut qtool, &i, &p)).is_ok() }));
    checks.push(json!({"check": "every member uses its own disjoint part of the tree's counter interval (whole root quota usable, no collision)", "ok": okq}));
    // public-only verifier (no secret key) accepts honest presentations
    { let pv = Pub::from_bytes(&sys.p.to_bytes()).unwrap(); let mut t = Tool::new("https://pub.example|x", false);
      let i = inv(&t.name.clone(), 1, 10, 7, 1_000_000, &nonce());
      let ok = sys.present(r, &child, &i, 0, false).map(|p| Presentation::from_bytes(&p.to_bytes()).unwrap()).and_then(|p| pv.verify(r, &mut t, &i, &p)).is_ok();
      checks.push(json!({"check": "a tool holding only public data (serialized) verifies an honest presentation", "ok": ok})); }
    // 2-of-3 openings with all member pairs return (principal, mandate)
    let i = inv(&etool.name.clone(), 1, 50, 8, 1_000_000, &nonce());
    let p = sys.present(r, &gchild, &i, 0, true).unwrap();
    sys.verify(r, &mut etool, &i, &p).unwrap();
    let c = p.esc.unwrap();
    for (a, b) in [(0usize, 1usize), (0, 2), (1, 2)] {
        let sh = |r: &mut _, k: usize, x: &G1Affine| { let (d, pf) = sys.share(r, k, x); (k, d, pf) };
        let s1 = [sh(r, a, &c[0]), sh(r, b, &c[0])]; let s2 = [sh(r, a, &c[2]), sh(r, b, &c[2])];
        let ok = sys.judge(&c, s1, s2) == Ok((42, gchild.a.id));
        checks.push(json!({"check": format!("2-of-3 opening with members {}+{} returns the principal and the mandate to revoke", a + 1, b + 1), "ok": ok}));
    }
    { let ids: Vec<u64> = [&root, &child, &gchild].iter().map(|m| m.a.id).chain(chain.iter().map(|m| m.a.id)).collect();
      let mut u = ids.clone(); u.sort(); u.dedup();
      checks.push(json!({"check": "identifiers are chosen by the issuer: non-zero and distinct (the requested value is ignored)", "ok": u.len() == ids.len() && ids.iter().all(|&x| x != 0)})); }

    // ---------------- attacks ----------------
    macro_rules! atk { ($cls:expr, $mech:expr, $name:expr, $res:expr) => {{ let (rej, by, why) = outcome($res);
        attacks.push(json!({"class": $cls, "mechanism": $mech, "attack": $name, "rejected": rej, "by": by, "detail": why.chars().take(140).collect::<String>()})); }} }
    macro_rules! atk_cause { ($cls:expr, $mech:expr, $name:expr, $res:expr, $why:expr) => {{ let (rej, by, why) = outcome($res);
        let good = rej && why.contains($why);
        attacks.push(json!({"class": $cls, "mechanism": $mech, "attack": $name, "rejected": good, "by": if good { by } else if rej { "OTHER CAUSE" } else { by },
                            "expected_cause": $why, "detail": why.chars().take(140).collect::<String>()})); }} }
    let t1n = "https://hotel2.example|search"; let t2n = "https://air2.example|search";
    let mut t1 = Tool::new(t1n, false);
    let mut t2 = Tool::new(t2n, false);
    let pv = |sys: &System, r: &mut rand::rngs::StdRng, m: &Mandate, i: &Invocation, j: u64, e: bool, t: &mut Tool| -> R {
        let p = sys.present(r, m, i, j, e)?; Ok(sys.verify(r, t, i, &p))
    };
    // A2 — overreach by a compromised agent
    atk!("A2", "BBS+ revealed scope bit", "class outside the mandate's scope", pv(&sys, r, &child, &inv(t1n, 2, 10, 7, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A2", "range proof", "amount above budget", pv(&sys, r, &child, &inv(t1n, 1, 301, 7, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A2", "range proof", "use after expiry", pv(&sys, r, &child, &inv(t1n, 1, 10, 7, 1_500_001, &nonce()), 0, false, &mut t1));
    { let mut m2 = clone_m(&child); m2.a.budget = 10_000;
      atk!("A2", "BBS+ signature", "inflate budget under an existing signature", pv(&sys, r, &m2, &inv(t1n, 1, 5_000, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    { let mut m2 = clone_m(&child); m2.a.scope = scope(&[1, 2]);
      atk!("A2", "BBS+ signature", "add a scope bit under an existing signature", pv(&sys, r, &m2, &inv(t1n, 2, 5, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    { let mut o = System::setup(&mut rng(99), 10); let mut rr = rng(5);
      let fake = o.issue_root(&mut rr, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[0, 1, 2, 3]), lo: 0, budget: 1 << 30, k: 100, exp: 9_000_000, uid: 1 }).unwrap();
      let mut fm = clone_m(&fake); fm.nm = child.nm.clone();
      atk!("A2", "BBS+ signature", "mandate signed by an unrecognised issuer", pv(&sys, r, &fm, &inv(t1n, 1, 10, 7, 1_000_000, &nonce()), 0, false, &mut t1)); }
    let mut dj = 1u64;
    let mut dl = |sys: &mut System, r: &mut rand::rngs::StdRng, p: &Mandate, a: Attrs| -> R { dj += 1; sys.delegate(r, p, &a, 100 + dj, 0).map(|_| Ok(())) };
    let base = || Attrs::child_of(&root.a, scope(&[1]), 100, 2, 1_000_000);
    atk!("A2", "range proof (scope)", "delegation: child gets a class the parent lacks", dl(&mut sys, r, &root, Attrs { scope: scope(&[1, 5]), ..base() }));
    atk!("A2", "range proof", "delegation: child budget above parent", dl(&mut sys, r, &root, Attrs { budget: 801, ..base() }));
    atk!("A2", "range proof", "delegation: child quota above parent", dl(&mut sys, r, &root, Attrs { k: 7, ..base() }));
    atk!("A2", "range proof", "delegation: child expiry after parent", dl(&mut sys, r, &root, Attrs { exp: 2_000_001, ..base() }));
    atk!("A2", "linear relation (depth)", "delegation: depth skip (+2)", dl(&mut sys, r, &root, Attrs { depth: 2, ..base() }));
    atk!("A2", "range proof (depth)", "delegation: beyond maximum depth 4", dl(&mut sys, r, &chain[4], Attrs::child_of(&chain[4].a, scope(&[1]), 10, 1, 1_000)));
    atk!("A2", "witness equality (ancestry)", "delegation: ancestry erasure (anc' cleared)", dl(&mut sys, r, &child, Attrs { anc: [0; 4], ..Attrs::child_of(&child.a, scope(&[1]), 10, 1, 1_000) }));
    atk!("A2", "witness equality (ancestry)", "delegation: ancestry rewrite (wrong grandparent)", dl(&mut sys, r, &child, Attrs { anc: [child.a.id, 999, 0, 0], ..Attrs::child_of(&child.a, scope(&[1]), 10, 1, 1_000) }));
    { let mut fp = clone_m(&root); fp.a.budget = 1 << 30;
      atk!("A2", "BBS+ signature", "delegation from a forged parent (attributes not signed)", dl(&mut sys, r, &fp, Attrs { budget: 1 << 29, ..base() })); }
    // context binding: the parent's proof is bound to H(issuer nonce, Cp)
    {   sys.epoch = 21; let n1 = b"issuer-session-1".to_vec();
        let (req, _sec) = sys.p.deleg_request(r, &root, &base(), 21, 0, &n1).unwrap();
        let (req2, _) = sys.p.deleg_request(r, &root, &Attrs { budget: 50, ..base() }, 21, 1, &n1).unwrap();
        let swapped = DelegReq { Cp: req2.Cp, nymD: req.nymD, epoch: req.epoch, pf: req.pf.clone() };
        atk_cause!("A2", "Fiat–Shamir context binding", "delegation proof reused with another child commitment", sys.deleg_issue(r, &swapped, &n1).map(|_| Ok(())), "deleg verify");
        let n2 = b"issuer-session-2".to_vec();
        atk_cause!("A2", "Fiat–Shamir context binding", "delegation request replayed in a new issuer session", sys.deleg_issue(r, &req, &n2).map(|_| Ok(())), "deleg verify"); }
    atk_cause!("A4", "issuer policy Q", "root issuance with a counter interval wider than the issuer's bound Q",
        sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 10, k: QMAX + 1, exp: 1_000, uid: 7 }).map(|_| Ok(())), "root: counter interval wider");
    // attribute-layout shift: one extra scope entry moves every later field by one slot (reviewer's proof of concept)
    { let mut sc = scope(&[1]); sc.push(true);
      atk_cause!("A4", "issuer fixes the layout", "root issuance with a shifted attribute layout (extra scope entry; would bypass Q and untraceable tag slot)",
        sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: sc, lo: (1u64 << 40) - 2, budget: 0, k: (1u64 << 40) - 1, exp: 12345, uid: 7 }).map(|_| Ok(())), "root: attribute layout"); }
    // per-principal root limit (Sybil boundary)
    { let lim_before = sys.root_limit; let have = *sys.roots_per_label.get(&9).unwrap_or(&0); sys.root_limit = have + 1;
      let first = sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 10, k: 4, exp: 1_000, uid: 9 }).is_ok();
      checks.push(json!({"check": "per-principal root limit: a root within the limit is issued", "ok": first}));
      atk_cause!("A4", "issuer policy (roots per principal)", "root beyond the per-principal root limit",
        sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 10, k: 4, exp: 1_000, uid: 9 }).map(|_| Ok(())), "root: per-principal root limit");
      sys.root_limit = lim_before; }
    // a malicious issuer publishes update data tampered to break other wallets' refreshes: the public spot check fails
    { let mut s3 = System::setup(&mut rng(seed + 77), 1000); let r3 = &mut rng(seed + 78);
      let (om, ad, chk) = s3.revoke_checked(&[4242]).unwrap();
      checks.push(json!({"check": "public spot check accepts honest accumulator update data", "ok": s3.p.check_update(&ad, &om, &chk)}));
      let mut bad = om.clone(); bad.0[0] = (bad.0[0].into_group() + s3.p.g.into_group()).into_affine();
      atk_cause!("A1", "public update check", "issuer publishes accumulator update data tampered to break chosen wallets' refreshes",
        Ok(if s3.p.check_update(&ad, &bad, &chk) { Ok(()) } else { Err("update data fails the public spot check".into()) }), "spot check");
      let _ = r3; }
    // compliant rebinding (child within the parent's limits): also rejected by the real issuer, accepted by the debug one,
    // i.e. the malicious-delegator rejections are structural (statement binding), as the paper says
    {   sys.epoch = 61; let nn = b"issuer-session-compliant".to_vec();
        let (q, _) = sys.p.deleg_request_opt(r, &root, &Attrs { budget: 100, ..base() }, 61, 0, &nn, DelegCheat { rebind: Some(sys.p.y.budget()), ..Default::default() }).unwrap();
        let ok = sys.p.deleg_verify_without(r, &q, &nn, sys.p.y.budget()).is_ok() && sys.deleg_issue(r, &q, &nn).is_err();
        checks.push(json!({"check": "negative control: a re-bound but compliant delegation is also rejected by the real issuer (rejection is structural) and accepted by the debug issuer", "ok": ok})); }
    // a malicious issuer hands out an invalid non-membership witness: the wallet detects it (no silent disabling)
    { let mut bad = clone_m(&root); bad.nm[0] = bad.nm[1].clone();
      checks.push(json!({"check": "wallet detects an invalid non-membership witness supplied by the issuer", "ok": sys.p.witnesses_valid(&root) && !sys.p.witnesses_valid(&bad)})); }
    atk!("A2", "issuer check", "root issuance with a quota outside [1, 2^40)", sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 10, k: 1 << 41, exp: 1_000, uid: 7 }).map(|_| Ok(())));
    // malicious provers (bypass every client-side check): the verifier or issuer must reject
    {   sys.epoch = 22; let n3 = b"issuer-session-3".to_vec();
        atk!("MP", "range proof (prover-side)", "delegation: child budget wrapped around the group order (honest library)", sys.p.deleg_request_opt(r, &root, &base(), 22, 2, &n3, DelegCheat { wrap_budget: true, ..Default::default() })
            .and_then(|(q, _)| sys.deleg_issue(r, &q, &n3)).map(|_| Ok(())));
        let n4 = b"issuer-session-4".to_vec(); sys.epoch = 23;
        atk_cause!("MP", "issuer verifies the full statement", "malicious parent: wrapped child budget, range statements re-bound to the parent's values",
            sys.p.deleg_request_opt(r, &root, &base(), 23, 3, &n4, DelegCheat { wrap_budget: true, malicious_omit_child_ranges: true, ..Default::default() })
            .and_then(|(q, _)| sys.deleg_issue(r, &q, &n4)).map(|_| Ok(())), "deleg verify");
        // malicious delegator, one attack per attenuation relation: the child's value in the commitment violates the
        // relation, and the prover's statement for that relation is re-bound to the parent's own value (so every
        // client-side check and the library's range checks pass); the issuer rebuilds the statement and must reject
        let yy = sys.p.y;
        let mut ep = 40u64;
        let mut controls: Vec<(String, bool)> = vec![];
        let mut mdel = |sys: &mut System, r: &mut rand::rngs::StdRng, parent: &Mandate, child: Attrs, j: u64, rb: usize| -> R {
            ep += 1; sys.epoch = ep; let nn = format!("issuer-session-md-{ep}").into_bytes();
            let (q, _) = sys.p.deleg_request_opt(r, parent, &child, ep, j, &nn, DelegCheat { rebind: Some(rb), ..Default::default() })?;
            // positive control: the same request is accepted by an issuer that omits exactly this relation
            let rname = if rb == REBIND_COUNTER { "delegation-counter bound".to_string() } else if rb == I_DEPTH { "depth".to_string() } else if rb == sys.p.y.budget() { "budget".to_string() } else if rb == sys.p.y.lo() { "interval lower bound".to_string() } else if rb == sys.p.y.k() { "interval upper bound".to_string() } else if rb == sys.p.y.exp() { "expiry".to_string() } else { format!("scope bit {}", rb - I_SCOPE) };
            controls.push((format!("the {rname} relation"), sys.p.deleg_verify_without(r, &q, &nn, rb).is_ok()));
            sys.deleg_issue(r, &q, &nn).map(|_| Ok(()))
        };
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: child budget above parent, relation re-bound",
            mdel(&mut sys, r, &root, Attrs { budget: 801, ..base() }, 0, yy.budget()), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: child interval starts below parent's (lower bound), relation re-bound",
            mdel(&mut sys, r, &child, Attrs { lo: child.a.lo - 1, ..Attrs::child_of(&child.a, scope(&[1]), 10, 1, 1_000) }, 0, yy.lo()), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: child interval ends above parent's (upper bound), relation re-bound",
            mdel(&mut sys, r, &root, Attrs { k: 7, ..base() }, 0, yy.k()), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: child expiry after parent, relation re-bound",
            mdel(&mut sys, r, &root, Attrs { exp: 2_000_001, ..base() }, 0, yy.exp()), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: child gets a class the parent lacks, scope relation re-bound",
            mdel(&mut sys, r, &root, Attrs { scope: scope(&[1, 5]), ..base() }, 0, I_SCOPE + 5), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: depth skip (+2), depth relation re-bound",
            mdel(&mut sys, r, &root, Attrs { depth: 2, ..base() }, 0, I_DEPTH), "deleg verify");
        atk_cause!("MP", "issuer verifies the full statement", "malicious delegator: delegation counter beyond the parent's quota, upper bound re-bound",
            mdel(&mut sys, r, &root, base(), 9, REBIND_COUNTER), "deleg verify");
        drop(mdel);
        for (name, ok) in controls { checks.push(json!({"check": format!("positive control: an issuer without the binding of {name} to the child commitment accepts the malicious delegation that the real issuer rejects"), "ok": ok})); }
        let i = inv(t1n, 1, 301, 24, 1_000_000, &nonce());
        atk!("MP", "verifier checks its own statement", "malicious agent: amount above budget, proof built for amount bound 0",
            sys.p.present_cheat(r, &child, &i, 0, false, &Cheat { weaken_amount: true, ..Default::default() }).map(|p| sys.verify(r, &mut Tool::new(t1n, false), &i, &p)));
        let i = inv(t1n, 1, 10, 25, 1_600_000, &nonce());
        atk!("MP", "verifier checks its own statement", "malicious agent: after expiry, proof built for time bound 0",
            sys.p.present_cheat(r, &child, &i, 0, false, &Cheat { weaken_expiry: true, ..Default::default() }).map(|p| sys.verify(r, &mut Tool::new(t1n, false), &i, &p)));
        let i = inv(t1n, 0, 10, 26, 1_000_000, &nonce());
        atk!("MP", "verifier checks its own statement", "malicious agent: class outside scope, proof reveals a class it holds",
            sys.p.present_cheat(r, &child, &i, 0, false, &Cheat { reveal_class: Some(1), ..Default::default() }).map(|p| sys.verify(r, &mut Tool::new(t1n, false), &i, &p)));
        let i = inv(t1n, 1, 10, 27, 1_000_000, &nonce());
        atk!("MP", "verifier checks its own statement", "malicious agent: counter beyond quota, quota statement detached from the signed k",
            sys.p.present_cheat(r, &child, &i, 10, false, &Cheat { free_quota: Some(1000), ..Default::default() }).map(|p| sys.verify(r, &mut Tool::new(t1n, false), &i, &p))); }
    // A3 — replay and binding
    let i_ok = inv(t1n, 1, 10, 9, 1_000_000, &nonce());
    let p_ok = sys.present(r, &child, &i_ok, 0, false).unwrap();
    sys.verify(r, &mut t1, &i_ok, &p_ok).unwrap();
    atk!("A3", "seen-set", "same presentation, same tool (replay)", Ok(sys.verify(r, &mut t1, &i_ok, &p_ok)));
    atk!("A3", "tool identity in the pseudonym base", "same presentation sent to another tool", Ok(sys.verify(r, &mut t2, &Invocation { tool: t2n.into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "Fiat–Shamir context binding", "same proof, different call arguments", Ok(sys.verify(r, &mut Tool::new(t1n, false), &Invocation { call: "{\"arguments\":{\"amt\":999},\"name\":\"op1\"}".into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "Fiat–Shamir context binding", "same proof, different tool nonce", Ok(sys.verify(r, &mut Tool::new(t1n, false), &Invocation { nonce: "other".into(), ..i_ok.clone() }, &p_ok)));
    atk!("A3", "Fiat–Shamir context binding", "same proof, another epoch", Ok(sys.verify(r, &mut Tool::new(t1n, false), &Invocation { epoch: 10, ..i_ok.clone() }, &p_ok)));
    atk!("A3", "Fiat–Shamir context binding", "same proof, larger amount", Ok(sys.verify(r, &mut Tool::new(t1n, false), &Invocation { amt: 299, ..i_ok.clone() }, &p_ok)));
    atk!("A3", "Fiat–Shamir context binding", "same proof, other action class", Ok(sys.verify(r, &mut Tool::new(t1n, false), &Invocation { class: 0, ..i_ok.clone() }, &p_ok)));
    atk!("A3", "domain separation", "tool named like the delegation domain", { let i = inv("MM-v2-nym-delegation", 1, 10, 7, 1_000_000, &nonce());
        let p = sys.present(r, &root, &i, 0, false).unwrap(); let dbase = deleg_base(7); Ok(if nym_base(&i.tool, 7) == dbase { Ok(()) } else { Err(format!("distinct bases (nym {} vs delegation)", p.nym == p.nym)) }) });
    // A4 — rate abuse
    atk!("A4", "seen-set (DY pseudonym)", "reuse a counter j within the epoch (fresh proof)", pv(&sys, r, &child, &inv(t1n, 1, 10, 9, 1_000_000, &nonce()), 0, false, &mut t1));
    atk!("A4", "range proof (hidden counter)", "counter j = k (beyond quota)", pv(&sys, r, &child, &inv(t1n, 1, 10, 9, 1_000_000, &nonce()), 4, false, &mut t1));
    atk!("A4", "range proof (hidden counter)", "counter j far beyond quota", pv(&sys, r, &child, &inv(t1n, 1, 10, 9, 1_000_000, &nonce()), 1000, false, &mut t1));
    { let mut pp = p_ok.clone(); pp.nym = (pp.nym.into_group() * Fr::from(2u64)).into_affine();
      atk!("A4", "pseudonym statement", "re-randomise the pseudonym of an accepted proof", Ok(sys.verify(r, &mut t1, &i_ok, &pp))); }
    atk!("A4", "seen-set (one pseudonym space per tree)", "parent uses a counter of its child's interval, then the child uses it", { let i = inv(t1n, 1, 10, 9, 1_000_000, &nonce());
        sys.present(r, &root, &i, gchild.a.lo - root.a.lo, false).and_then(|p| sys.verify(r, &mut t1, &i, &p)).and_then(|_| {
            let i2 = inv(t1n, 1, 10, 9, 1_000_000, &nonce()); sys.present(r, &gchild, &i2, 0, false).map(|p| sys.verify(r, &mut t1, &i2, &p)) }) });
    {   // a parent that hands two children overlapping intervals gains nothing: the second use of a counter is rejected
        let (sib, _, _) = sys.delegate(r, &root, &Attrs::child_range(&root.a, scope(&[1]), 300, child.a.lo, child.a.k, 1_500_000), 7, 2).unwrap();
        atk!("A4", "seen-set (one pseudonym space per tree)", "siblings with overlapping intervals use the same counter", { let i = inv(t2n, 1, 10, 9, 1_000_000, &nonce());
            sys.present(r, &child, &i, 1, false).and_then(|p| sys.verify(r, &mut t2, &i, &p)).and_then(|_| { let i2 = inv(t2n, 1, 10, 9, 1_000_000, &nonce()); sys.present(r, &sib, &i2, 1, false).map(|p| sys.verify(r, &mut t2, &i2, &p)) }) }); }
    atk!("A4", "BBS+ signature (interval is signed)", "child rewrites its interval to use counters reserved for the parent", {
        let i = inv(t2n, 1, 10, 9, 1_000_000, &nonce()); let mut c2 = child.clone(); c2.a.lo = 0; sys.present(r, &c2, &i, 0, false).map(|p| sys.verify(r, &mut t2, &i, &p)) });
    atk!("A4", "issuer seen-set (DY pseudonym)", "delegation pseudonym reuse (same epoch and counter)", sys.delegate(r, &root, &base(), 7, 0).map(|_| Ok(())));
    atk!("A4", "range proof (hidden counter)", "delegation counter beyond the parent's quota", sys.delegate(r, &root, &base(), 7, 6).map(|_| Ok(())));
    // A5 — revocation (NM statements: presentation 13 = own id, 14 = anc1, 15 = anc2 ; delegation 1 = parent id, 2 = parent's anc1)
    let (gc2, _, _) = sys.delegate(r, &child, &Attrs::child_range(&child.a, scope(&[1]), 50, child.a.lo + 1, gchild.a.lo, 1_400_000), 8, 2).unwrap();
    let old_acc: G1Affine = sys.p.accv;
    let (om, ad) = sys.revoke(&[gchild.a.id]).unwrap();
    let mut root = root; let mut child = child; let mut gchild = gchild; let mut gc2 = gc2;
    root.refresh(&ad, &om).unwrap(); child.refresh(&ad, &om).unwrap(); gc2.refresh(&ad, &om).unwrap();
    let stuck_gc = gchild.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a revocation, the revoked holder cannot refresh its own witness (only position 0 is stuck)", "ok": stuck_gc == vec![0]}));
    { let i = inv(t1n, 1, 10, 11, 1_000_000, &nonce());
      let ok = sys.present(r, &gc2, &i, 0, false).and_then(|p| sys.verify(r, &mut t1, &i, &p)).is_ok();
      checks.push(json!({"check": "honest presentation after a revocation (sibling of the revoked mandate, refreshed witnesses)", "ok": ok})); }
    let grefok = { let mut g = clone_m(&gchild); g.refresh(&ad, &om).is_ok() && sys.acc.verify_non_membership(&fr(gchild.a.id), &g.nm[0], &sys.akp.public_key, &sys.p.ap) };
    atk!("A5", "accumulator security", "refresh the witness of a revoked id from public data", Ok(if grefok { Ok(()) } else { Err("refreshed witness does not verify".into()) }));
    atk_cause!("A5", "non-membership (own id)", "present after own revocation", pv(&sys, r, &gchild, &inv(t1n, 1, 10, 11, 1_000_000, &nonce()), 1, false, &mut t1), "VBAccumProofContributionFailed(9,");
    atk!("A5", "current accumulator value", "present with a stale accumulator value", { let i = inv(t1n, 1, 10, 11, 1_000_000, &nonce());
        sys.p.present_cheat(r, &gchild, &i, 1, false, &Cheat { acc_value: Some(old_acc), ..Default::default() }).map(|p| sys.verify(r, &mut t1, &i, &p)) });
    let (om, ad) = sys.revoke(&[child.a.id]).unwrap(); root.refresh(&ad, &om).unwrap();
    let stuck_c = child.refresh_partial(&ad, &om);
    let stuck_gc2 = gc2.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a parent revocation, the child refreshes its own witness but not the parent's (only position 1 is stuck)", "ok": stuck_gc2 == vec![1] && stuck_c == vec![0]}));
    atk_cause!("A5", "non-membership (parent)", "present after parent revocation (own witness up to date)", pv(&sys, r, &gc2, &inv(t1n, 1, 10, 12, 1_000_000, &nonce()), 0, false, &mut t1), "VBAccumProofContributionFailed(10,");
    atk_cause!("A5", "non-membership (parent id)", "delegate after own revocation", sys.delegate(r, &child, &Attrs::child_of(&child.a, scope(&[1]), 10, 1, 1_000), 12, 3).map(|_| Ok(())), "VBAccumProofContributionFailed(1,");
    let g0 = sys.issue_root(r, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 100, k: 4, exp: 2_000_000, uid: 9 }).unwrap();
    let (g1, _, _) = sys.delegate(r, &g0, &Attrs::child_of(&g0.a, scope(&[1]), 90, 4, 1_900_000), 13, 0).unwrap();
    let (g2, _, _) = sys.delegate(r, &g1, &Attrs::child_of(&g1.a, scope(&[1]), 80, 4, 1_800_000), 13, 1).unwrap();
    let (om, ad) = sys.revoke(&[g0.a.id]).unwrap(); root.refresh(&ad, &om).unwrap();
    let (mut g1, mut g2) = (g1, g2);
    let stuck_g1 = g1.refresh_partial(&ad, &om); let stuck_g2 = g2.refresh_partial(&ad, &om);
    checks.push(json!({"check": "after a root revocation, descendants refresh all witnesses except the root's (positions 1 and 2)", "ok": stuck_g1 == vec![1] && stuck_g2 == vec![2]}));
    atk_cause!("A5", "non-membership (grandparent)", "present after grandparent revocation (own and parent witnesses up to date)", pv(&sys, r, &g2, &inv(t1n, 1, 10, 13, 1_000_000, &nonce()), 2, false, &mut t1), "VBAccumProofContributionFailed(11,");
    atk_cause!("A5", "non-membership (parent's ancestor)", "child of a revoked root delegates a new sub-agent", sys.delegate(r, &g1, &Attrs::child_of(&g1.a, scope(&[1]), 70, 1, 1_700_000), 14, 3).map(|_| Ok(())), "VBAccumProofContributionFailed(2,");
    checks.push(json!({"check": "identifier 0 (no ancestor) cannot be revoked", "ok": sys.revoke(&[0]).is_err()}));
    // A6 — accountability (member 1 = index 0 corrupt; target principal 43, who made no presentation)
    let pn = "https://pay2.example|pay";
    let mut pt = Tool::new(pn, true);
    atk!("A6", "witness equality (tag)", "escrow ciphertext encrypts another root tag", { let i = inv(pn, 1, 10, 14, 1_000_000, &nonce()); let ufake = Fr::rand(r);
        sys.p.present_cheat(r, &root, &i, 0, true, &Cheat { esc_u: Some(ufake), ..Default::default() }).map(|p| sys.verify(r, &mut pt, &i, &p)) });
    atk!("A6", "witness equality (id)", "escrow ciphertext encrypts another mandate id", { let i = inv(pn, 1, 10, 14, 1_000_000, &nonce());
        sys.p.present_cheat(r, &root, &i, 0, true, &Cheat { esc_id: Some(g0.a.id), ..Default::default() }).map(|p| sys.verify(r, &mut pt, &i, &p)) });
    atk!("A6", "tool policy", "omit escrow where the tool requires it", { let i = inv(pn, 1, 10, 14, 1_000_000, &nonce()); sys.present(r, &root, &i, 0, false).map(|p| sys.verify(r, &mut pt, &i, &p)) });
    let i6 = inv(pn, 0, 10, 15, 1_000_000, &nonce());
    let p6 = sys.present(r, &root, &i6, 0, true).unwrap();
    sys.verify(r, &mut pt, &i6, &p6).unwrap();
    let c = p6.esc.unwrap();
    let judged = |res: Result<(u64, u64), String>| -> R { Ok(match res { Ok((u, _)) if u == 43 => Ok(()), Ok((u, _)) => Err(format!("Judge opens to {u}, not the target")), Err(e) => Err(e) }) };
    let sh = |sys: &System, r: &mut rand::rngs::StdRng, k: usize, x: &G1Affine| { let (d, pf) = sys.share(r, k, x); (k, d, pf) };
    let s2ok = [sh(&sys, r, 0, &c[2]), sh(&sys, r, 1, &c[2])];
    let (d0, pf0) = sys.share(r, 0, &c[0]); let (d1, pf1) = sys.share(r, 1, &c[0]);
    let (l0, l1) = lagrange_at0(1, 2);
    let pk43 = sys.registry[&43];
    let d1_forged = ((c[1].into_group() - pk43.into_group() - d0.into_group() * l0) * l1.inverse().unwrap()).into_affine();
    atk_cause!("A6", "Chaum–Pedersen share proof", "corrupt member forges the second share to frame principal 43 (reuses the honest proof)", judged(sys.judge(&c, [(0, d0, pf0), (1, d1_forged, pf1)], s2ok.clone())), "invalid share proof from member 2");
    atk_cause!("A6", "Chaum–Pedersen share proof", "corrupt member forges the second share to frame principal 43 (random proof)", judged(sys.judge(&c, [(0, d0, pf0), (1, d1_forged, (Fr::rand(r), Fr::rand(r)))], s2ok.clone())), "invalid share proof from member 2");
    { let d0_bad = (d0.into_group() * Fr::from(3u64)).into_affine();
      atk_cause!("A6", "Chaum–Pedersen share proof", "malicious member submits a wrong decryption share", judged(sys.judge(&c, [(0, d0_bad, pf0), (1, d1, pf1)], s2ok.clone())), "invalid share proof from member 1"); }
    { let (_, pf2) = sys.share(r, 2, &c[0]);
      atk_cause!("A6", "Chaum–Pedersen share proof", "share with a proof made for another member", judged(sys.judge(&c, [(0, d0, pf0), (1, d1, pf2)], s2ok.clone())), "invalid share proof from member 2"); }
    atk_cause!("A6", "Judge: distinct members", "corrupt member submits its own share twice", judged(sys.judge(&c, [(0, d0, pf0), (0, d0, pf0)], s2ok.clone())), "two distinct committee members");
    { let i = inv(pn, 1, 10, 16, 1_000_000, &nonce()); let mut p = sys.present(r, &root, &i, 1, true).unwrap(); p.esc = Some(c);
      atk!("A6", "Fiat–Shamir (escrow statements)", "graft another presentation's escrow ciphertext", Ok(sys.verify(r, &mut pt, &i, &p))); }
    // non-frameability against a malicious issuer: the issuer signs a mandate with a key u' of its choice (it does not know u_43)
    {   let mut a = Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 100, k: 4, exp: 2_000_000, uid: 43 };
        a.id = 4_242_424_242; sys.issued.insert(a.id);
        let uf = Fr::rand(r); let s = Fr::rand(r);
        let mut m = Mandate { s, u: uf, a, ver: sys.p.ver, sig: SignatureG1::<ark_bls12_381::Bls12_381>::new(r, &vec![Fr::from(0u64); 1], &sys.ikp.secret_key, &sys.p.sp).unwrap_or_else(|_| root.sig.clone()), nm: vec![] };
        let msgs = m.msgs();
        m.sig = SignatureG1::new(r, &msgs, &sys.ikp.secret_key, &sys.p.sp).unwrap();
        m.nm = m.ids().iter().map(|id| sys.nm_witness(*id).unwrap()).collect();
        let i = inv(pn, 1, 10, 17, 1_000_000, &nonce());
        let p = sys.present(r, &m, &i, 0, true).unwrap();
        let ok = sys.verify(r, &mut pt, &i, &p);
        let c = p.esc.unwrap();
        let s1 = [sh(&sys, r, 0, &c[0]), sh(&sys, r, 2, &c[0])]; let s2 = [sh(&sys, r, 0, &c[2]), sh(&sys, r, 2, &c[2])];
        atk_cause!("A6", "uid bound to the principal's registered key", "malicious issuer signs a mandate in the name of principal 43 without its secret", ok.map(|_| judged(sys.judge(&c, s1, s2))).and_then(|x| x), "no registered principal"); }
    // deployment checks: epochs fixed by the issuer and the tools, tool nonces, accumulator window, bindings, public parameters
    {   let mut s2 = System::setup(&mut rng(seed + 7), 100);
        let r2 = &mut rng(seed + 8);
        let rt = s2.issue_root(r2, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 500, k: 20, exp: 2_000_000, uid: 77 }).unwrap();
        s2.epoch = 30; let n5 = b"issuer-session-5".to_vec();
        atk_cause!("A4", "issuer clock (epoch)", "delegation request for an epoch other than the issuer's (quota replay across invented epochs)",
            s2.p.deleg_request(r2, &rt, &Attrs::child_of(&rt.a, scope(&[1]), 10, 2, 1_000), 31, 0, &n5).and_then(|(q, _)| s2.deleg_issue(r2, &q, &n5)).map(|_| Ok(())), "epoch differs");
        let tn = "https://strict.example|pay";
        let mut st = Tool::strict(tn, false, 30, 1_000_000, 60);
        let n = st.issue_nonce(r2);
        let i = inv(tn, 1, 10, 31, 1_000_000, &n);
        atk_cause!("A3", "tool clock (epoch)", "presentation for another epoch than the tool's", Ok(s2.present(r2, &rt, &i, 0, false).map(|p| s2.verify(r2, &mut st, &i, &p)).and_then(|x| x)), "wrong epoch");
        let n = st.issue_nonce(r2); let i = inv(tn, 1, 10, 30, 1_000_000 - 3600, &n);
        atk_cause!("A3", "tool clock (time)", "presentation with a time far from the tool's clock", Ok(s2.present(r2, &rt, &i, 1, false).map(|p| s2.verify(r2, &mut st, &i, &p)).and_then(|x| x)), "time out of tolerance");
        let i = inv(tn, 1, 10, 30, 1_000_000, "nonce-never-issued");
        atk_cause!("A3", "tool nonce", "presentation with a nonce the tool never issued", Ok(s2.present(r2, &rt, &i, 2, false).map(|p| s2.verify(r2, &mut st, &i, &p)).and_then(|x| x)), "unknown or already used tool nonce");
        let n = st.issue_nonce(r2); let i = inv(tn, 1, 10, 30, 1_000_000, &n);
        let okp = s2.present(r2, &rt, &i, 3, false).unwrap();
        let first = s2.verify(r2, &mut st, &i, &okp).is_ok();
        checks.push(json!({"check": "a strict tool (epoch, time, own nonce) accepts an honest presentation", "ok": first}));
        let i2 = Invocation { ..i.clone() };
        atk_cause!("A3", "tool nonce (single use)", "same nonce used twice (fresh proof, next counter)", Ok(s2.present(r2, &rt, &i2, 4, false).map(|p| s2.verify(r2, &mut st, &i2, &p)).and_then(|x| x)), "unknown or already used tool nonce");
        // accumulator grace window: with W = 1 the previous value is still accepted, the one before is not
        s2.acc_grace = 1;
        let a0 = s2.p.accv;
        let (o1, d1) = s2.revoke(&[123_456]).unwrap();
        let mut rt1 = clone_m(&rt); rt1.refresh(&d1, &o1).unwrap();
        let mut tw = Tool::new("https://w.example|x", false);
        let iw = inv("https://w.example|x", 1, 10, 30, 1_000_000, &nonce());
        let okw = s2.p.present_cheat(r2, &rt, &iw, 5, false, &Cheat { acc_value: Some(a0), ..Default::default() }).map(|p| s2.verify(r2, &mut tw, &iw, &p).is_ok()).unwrap_or(false);
        checks.push(json!({"check": "grace window: a presentation against the previous accumulator value is still accepted (W = 1)", "ok": okw}));
        let (_o2, _d2) = s2.revoke(&[654_321]).unwrap();
        let iw = inv("https://w.example|x", 1, 10, 30, 1_000_000, &nonce());
        atk_cause!("A5", "accumulator window", "presentation against an accumulator value older than the grace window",
            s2.p.present_cheat(r2, &rt, &iw, 6, false, &Cheat { acc_value: Some(a0), ..Default::default() }).map(|p| s2.verify(r2, &mut tw, &iw, &p)), "accumulator value not accepted");
        // a malicious issuer publishes a binding of a tag of its choice to principal 77 (it cannot sign with 77's key)
        let tf = Fr::rand(r2); let gtf = (s2.p.g.into_group() * tf).into_affine();
        let mut key = vec![]; gtf.serialize_compressed(&mut key).unwrap();
        s2.bindings.insert(key, (77, (Fr::rand(r2), Fr::rand(r2))));
        let mut fake = clone_m(&rt); fake.u = tf;
        let msgs = fake.msgs(); fake.sig = SignatureG1::new(r2, &msgs, &s2.ikp.secret_key, &s2.p.sp).unwrap(); fake.nm = fake.ids().iter().map(|id| s2.nm_witness(*id).unwrap()).collect();
        let ie = inv("https://e.example|pay", 1, 10, 30, 1_000_000, &nonce()); let mut te = Tool::new("https://e.example|pay", true);
        let pe = s2.present(r2, &fake, &ie, 7, true).unwrap(); let okv = s2.verify(r2, &mut te, &ie, &pe);
        let c = pe.esc.unwrap();
        let s1 = [sh(&s2, r2, 0, &c[0]), sh(&s2, r2, 1, &c[0])]; let s2s = [sh(&s2, r2, 0, &c[2]), sh(&s2, r2, 1, &c[2])];
        atk_cause!("A6", "binding signed by the principal's key", "malicious issuer binds a tag of its choice to principal 77 and signs a mandate with it",
            okv.map(|_| judged(s2.judge(&c, s1, s2s))).and_then(|x| x), "binding signature invalid");
        // a malicious issuer that also ran the registry replaces principal 77's key by its own, signs a valid binding with
        // it and opens a presentation to 77; Judge uses the registrations held outside the issuer (self-certified log)
        let indep_registry = s2.registry.clone();
        let ua = Fr::rand(r2); let pka = (s2.p.g.into_group() * ua).into_affine();
        s2.registry.insert(77, pka);
        let tf2 = Fr::rand(r2); let gtf2 = (s2.p.g.into_group() * tf2).into_affine();
        let mut key2 = vec![]; gtf2.serialize_compressed(&mut key2).unwrap();
        s2.bindings.insert(key2, (77, schnorr_sign(r2, &s2.p.g, ua, &binding_msg(77, &gtf2))));
        let mut fake2 = clone_m(&rt); fake2.u = tf2;
        let msgs2 = fake2.msgs(); fake2.sig = SignatureG1::new(r2, &msgs2, &s2.ikp.secret_key, &s2.p.sp).unwrap(); fake2.nm = fake2.ids().iter().map(|id| s2.nm_witness(*id).unwrap()).collect();
        let ie2 = inv("https://e.example|pay", 1, 10, 30, 1_000_000, &nonce());
        let pe2 = s2.present(r2, &fake2, &ie2, 8, true).unwrap(); let okv2 = s2.verify(r2, &mut te, &ie2, &pe2);
        let c2 = pe2.esc.unwrap();
        let t1s = [sh(&s2, r2, 0, &c2[0]), sh(&s2, r2, 1, &c2[0])]; let t2s = [sh(&s2, r2, 0, &c2[2]), sh(&s2, r2, 1, &c2[2])];
        let by_issuer_registry = matches!(s2.judge(&c2, t1s.clone(), t2s.clone()), Ok((77, _)));
        checks.push(json!({"check": "registry held by the issuer is not trusted: with the issuer's tampered copy Judge would open to 77 (motivates the independent registry)", "ok": by_issuer_registry}));
        atk_cause!("A6", "registry outside the issuer", "malicious issuer replaces principal 77's registered key and signs a binding with its own key",
            okv2.map(|_| s2.judge_with(&indep_registry, &c2, t1s, t2s).map(|_| ())), "binding signature invalid");
        s2.registry = indep_registry;
        // tools never use issuer-supplied proof parameters: they are re-derived from public labels
        let pb = s2.p.to_bytes(); let pp = Pub::from_bytes(&pb).unwrap();
        let (sp, ap, nmk, _) = public_params(s2.p.y);
        let same = |a: &dyn Fn(&mut Vec<u8>), b: &dyn Fn(&mut Vec<u8>)| { let (mut x, mut y) = (vec![], vec![]); a(&mut x); b(&mut y); x == y };
        let ok = same(&|v| pp.ap.serialize_compressed(v).unwrap(), &|v| ap.serialize_compressed(v).unwrap())
              && same(&|v| pp.nmk.serialize_compressed(v).unwrap(), &|v| nmk.serialize_compressed(v).unwrap())
              && same(&|v| pp.sp.serialize_compressed(v).unwrap(), &|v| sp.serialize_compressed(v).unwrap())
              && pb.len() < 2_000;
        checks.push(json!({"check": "public parameters carry no accumulator, signature or range-proof bases: tools re-derive them from labels (no issuer trapdoor)", "ok": ok}));
    }
    // parser and mutation tests (fuzzing of serialized presentations)
    {   let i = inv(t1n, 1, 10, 30, 1_000_000, &nonce());
        let p = sys.present(r, &root, &i, 2, true).unwrap();
        let bytes = p.to_bytes();
        let mut accepted = 0usize; let mut tried = 0usize; let mut panics_escaped = 0usize;
        for _ in 0..2000 {
            let mut b = bytes.clone();
            let pos = (r.next_u64() as usize) % b.len();
            b[pos] ^= 1 << (r.next_u64() % 8);
            tried += 1;
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                match Presentation::from_bytes(&b) { Ok(q) => sys.verify(&mut rng(1), &mut Tool::new(t1n, true), &i, &q).is_ok(), Err(_) => false }
            }));
            match res { Ok(true) => accepted += 1, Ok(false) => {}, Err(_) => panics_escaped += 1 }
        }
        atk!("PARSE", "parser and verifier (2,000 single-bit mutations)", "bit-flip mutations of a valid presentation",
            Ok(if accepted == 0 && panics_escaped == 0 { Err(format!("verify: all {tried} mutated presentations rejected, no panic")) } else { Ok(()) }));
        atk!("PARSE", "parser", "truncated presentation", Ok(match Presentation::from_bytes(&bytes[..bytes.len() - 7]) { Ok(_) => Ok(()), Err(e) => Err(format!("verify: parse error {e}")) }));
        let mut ext = bytes.clone(); ext.extend_from_slice(&[0, 1, 2]);
        atk!("PARSE", "parser", "presentation with trailing bytes", Ok(match Presentation::from_bytes(&ext) { Ok(_) => Ok(()), Err(e) => Err(format!("verify: parse error {e}")) }));
        let i2 = inv(t1n, 1, 10, 30, 1_000_000, &nonce());
        let q = sys.present(r, &root, &i2, 3, true).unwrap();
        let mut mix = q.clone(); mix.nym = p.nym;
        atk!("PARSE", "pseudonym statement", "pseudonym taken from another valid presentation", Ok(sys.verify(r, &mut Tool::new(t1n, true), &i2, &mix)));
        atk!("PARSE", "Fiat–Shamir (escrow statements)", "escrow ciphertexts taken from another valid presentation", { let mut m2 = q.clone(); m2.esc = p.esc; Ok(sys.verify(r, &mut Tool::new(t1n, true), &i2, &m2)) }); }

    // REV — revocation authorization at the log (v2.2): a separate system and RNG, so that the outcomes above are unchanged.
    {   let rr = &mut rng(seed + 7);
        let mut sr = System::setup(&mut rng(seed + 6), 100);
        for l in [50, 51] { sr.register(rr, l); }
        let rt = sr.issue_root(rr, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[0, 1]), lo: 0, budget: 500, k: 64, exp: 2_000_000, uid: 50 }).unwrap();
        let (c1, _, _) = sr.delegate(rr, &rt, &Attrs::child_of(&rt.a, scope(&[1]), 300, 32, 1_500_000), 3, 0).unwrap();
        let (c2, _, _) = sr.delegate(rr, &rt, &Attrs::child_range(&rt.a, scope(&[1]), 300, 8, 16, 1_500_000), 3, 1).unwrap();
        let (g1, _, _) = sr.delegate(rr, &c1, &Attrs::child_of(&c1.a, scope(&[1]), 100, 8, 1_400_000), 3, 0).unwrap();
        let (g2, _, _) = sr.delegate(rr, &c1, &Attrs::child_range(&c1.a, scope(&[1]), 100, c1.a.lo, c1.a.lo + 4, 1_400_000), 3, 1).unwrap();
        let un = sr.issue_root(rr, &Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope(&[1]), lo: 0, budget: 100, k: 8, exp: 2_000_000, uid: 51 }).unwrap();
        let (h1, _, _) = sr.delegate(rr, &c2, &Attrs::child_of(&c2.a, scope(&[1]), 100, 4, 1_400_000), 3, 0).unwrap();
        let mut live: Vec<Mandate> = vec![rt, c1, c2, g1, g2, un, h1];
        // indices into `live`: 0 root, 1 child c1, 2 child c2, 3 grandchild g1 (under c1), 4 grandchild g2 (under c1), 5 unrelated root,
        // 6 grandchild h1 (under c2)
        let refresh = |live: &mut Vec<Mandate>, ad: &[Fr], om: &vb_accumulator::prelude::Omega<G1Affine>| { for m in live.iter_mut() { let _ = m.refresh_partial(ad, om); } };
        let accepted = |sr: &mut System, rr: &mut rand::rngs::StdRng, live: &mut Vec<Mandate>, x: u64, a: Result<RevocationAuth, String>, n: Vec<u8>| -> bool {
            match a.and_then(|a| sr.revoke_authorized(rr, &[x], &a, &n)) {
                Ok((om, ad, chk)) => { let ok = sr.p.check_update(&ad, &om, &chk) && sr.revoked.contains(&fr(x)); refresh(live, &ad, &om); ok }
                Err(e) => { eprintln!("REV check failed: {e}"); false } } };
        // attacks on a live target (c2), before any revocation
        let x = live[2].a.id;
        let n = sr.log_nonce(rr);
        atk_cause!("REV", "log: authorization required", "revocation without authorization (empty committee authorization)",
            sr.revoke_authorized(rr, &[x], &RevocationAuth::Committee { x, sigs: vec![] }, &n).map(|_| Ok(())), "two distinct committee members");
        let n = sr.log_nonce(rr);
        { let fake: Vec<(usize, (Fr, Fr))> = (0..2).map(|i| { let k = Fr::rand(rr); (i, schnorr_sign(rr, &sr.p.g, k, &revoke_committee_msg(x, &n))) }).collect();
          atk_cause!("REV", "log: committee signatures (Schnorr under X_i)", "committee authorization forged with non-member keys",
            sr.revoke_authorized(rr, &[x], &RevocationAuth::Committee { x, sigs: fake }, &n).map(|_| Ok(())), "invalid committee signature"); }
        let n = sr.log_nonce(rr);
        { let s0 = sr.committee_sign(rr, 0, x, &n);
          atk_cause!("REV", "log: two distinct committee members", "committee authorization with one signature",
            sr.revoke_authorized(rr, &[x], &RevocationAuth::Committee { x, sigs: vec![s0] }, &n).map(|_| Ok(())), "two distinct committee members"); }
        let n = sr.log_nonce(rr);
        { let (s0, s0b) = (sr.committee_sign(rr, 0, x, &n), sr.committee_sign(rr, 0, x, &n));
          atk_cause!("REV", "log: two distinct committee members", "committee authorization with two signatures of the same member",
            sr.revoke_authorized(rr, &[x], &RevocationAuth::Committee { x, sigs: vec![s0, s0b] }, &n).map(|_| Ok(())), "two distinct committee members"); }
        let n = sr.log_nonce(rr);
        atk_cause!("REV", "log: anonymous proof (BBS+ revealed id or ancestor)", "anonymous revocation proof made with an unrelated mandate (X not its id nor an ancestor)",
            sr.p.revocation_request_at(rr, &live[5], x, 0, &n).map(|a| sr.revoke_authorized(rr, &[x], &a, &n).map(|_| ())), "revocation proof");
        let n = sr.log_nonce(rr);
        atk_cause!("REV", "log: anonymous proof (BBS+ revealed id or ancestor)", "anonymous revocation proof by a sibling claiming X at its ancestor position",
            sr.p.revocation_request_at(rr, &live[1], x, 1, &n).map(|a| sr.revoke_authorized(rr, &[x], &a, &n).map(|_| ())), "must reveal the mandate's own identifier");
        let n = sr.log_nonce(rr);
        { let s = [sr.committee_sign(rr, 0, 0, &n), sr.committee_sign(rr, 2, 0, &n)];
          atk_cause!("REV", "log rule: identifier 0 never revocable", "revocation of identifier 0 (padding of missing ancestors) with two committee signatures",
            sr.revoke_authorized(rr, &[0], &RevocationAuth::Committee { x: 0, sigs: s.to_vec() }, &n).map(|_| Ok(())), "identifier 0"); }
        { let n1 = sr.log_nonce(rr); let n2 = sr.log_nonce(rr);
          atk_cause!("REV", "log: Fiat–Shamir context (log nonce)", "valid anonymous authorization replayed under another log nonce",
            sr.p.revocation_request(rr, &live[2], x, &n1).map(|a| sr.revoke_authorized(rr, &[x], &a, &n2).map(|_| ())), "revocation proof");
          sr.log_nonces.remove(&n1); }
        { let n = sr.log_nonce(rr); let y = live[1].a.id;
          atk_cause!("REV", "log: authorization bound to X", "authorization for X used to revoke another identifier",
            sr.p.revocation_request(rr, &live[2], x, &n).map(|a| sr.revoke_authorized(rr, &[y], &a, &n).map(|_| ())), "covers another identifier"); }
        { let n = sr.log_nonce(rr);
          atk_cause!("REV", "log: single-use nonce", "authorization under a log nonce that was already used (or never issued)",
            { let n0 = b"never-issued".to_vec(); let s = vec![sr.committee_sign(rr, 0, x, &n0), sr.committee_sign(rr, 1, x, &n0)];
              sr.revoke_authorized(rr, &[x], &RevocationAuth::Committee { x, sigs: s }, &n0).map(|_| Ok(())) }, "unknown or already used log nonce");
          sr.log_nonces.remove(&n); }
        // stale accumulator value: a proof made before a revocation is submitted after it
        let n_stale = sr.log_nonce(rr);
        let stale = sr.p.revocation_request(rr, &live[2], x, &n_stale);
        // checks: the holder revokes itself (g2), a parent revokes its child (c1 holds the credential of g1, obtained when
        // it delegated), two committee members; a descendant revealing an ancestor position is an attack (log: pos 0 only)
        { let n = sr.log_nonce(rr); let x = live[4].a.id; let a = sr.p.revocation_request(rr, &live[4], x, &n);
          let ok = accepted(&mut sr, rr, &mut live, x, a, n);
          checks.push(json!({"check": "log accepts a revocation authorized anonymously by the holder itself (X = own id)", "ok": ok})); }
        atk_cause!("REV", "log: current accumulator value", "anonymous revocation proof made against a previous accumulator value",
            stale.map(|a| sr.revoke_authorized(rr, &[x], &a, &n_stale).map(|_| ())), "current accumulator value");
        { let n = sr.log_nonce(rr); let x = live[3].a.id; let a = sr.p.revocation_request(rr, &live[3], x, &n);
          let ok = accepted(&mut sr, rr, &mut live, x, a, n);
          checks.push(json!({"check": "log accepts a parent revoking its child anonymously (proof with the child credential the parent obtained when delegating)", "ok": ok})); }
        { let un = live[5].clone();
          let (c3, _, _) = sr.delegate(rr, &un, &Attrs::child_of(&un.a, scope(&[1]), 50, 4, 1_000_000), 4, 0).unwrap();
          let n = sr.log_nonce(rr);
          atk_cause!("REV", "log: anonymous revocation reveals pos 0 only", "descendant revokes its parent (and the parent's other children) with a proof at the ancestor position",
            sr.p.revocation_request_at(rr, &c3, un.a.id, 1, &n).map(|a| sr.revoke_authorized(rr, &[un.a.id], &a, &n).map(|_| ())), "must reveal the mandate's own identifier");
          let n = sr.log_nonce(rr);
          atk_cause!("REV", "wallet: revocation request for own identifier only", "honest requester asked to revoke an ancestor",
            sr.p.revocation_request(rr, &c3, un.a.id, &n).map(|a| sr.revoke_authorized(rr, &[un.a.id], &a, &n).map(|_| ())), "not the mandate's own identifier"); }
        { let n = sr.log_nonce(rr); let x = live[2].a.id;
          let s = vec![sr.committee_sign(rr, 1, x, &n), sr.committee_sign(rr, 2, x, &n)];
          let ok = accepted(&mut sr, rr, &mut live, x, Ok(RevocationAuth::Committee { x, sigs: s }), n);
          checks.push(json!({"check": "log accepts a revocation signed by two distinct committee members", "ok": ok})); }
        { let n = sr.log_nonce(rr); let y = live[6].a.id;
          atk_cause!("REV", "log: non-membership (ancestors)", "anonymous self-revocation by a mandate whose parent is revoked (credential of a revoked subtree)",
            sr.p.revocation_request(rr, &live[6], y, &n).map(|a| sr.revoke_authorized(rr, &[y], &a, &n).map(|_| ())), "VBAccumProofContributionFailed("); }
        { let mut t = Tool::new("https://rev.example|search", false); let i = inv(&t.name.clone(), 1, 10, 3, 1_000_000, "rev-n1");
          let ok = sr.present(rr, &live[0], &i, 0, false).and_then(|p| sr.verify(rr, &mut t, &i, &p)).is_ok();
          checks.push(json!({"check": "after authorized revocations, a live mandate still presents (root, refreshed witnesses)", "ok": ok})); }
    }

    let n_att = attacks.len();
    let n_rej = attacks.iter().filter(|a| a["rejected"] == true).count();
    let n_chk = checks.len();
    let n_ok = checks.iter().filter(|c| c["ok"] == true).count();
    let out = json!({"version": 2, "seed": seed, "attacks": attacks, "checks": checks, "n_attacks": n_att, "n_rejected": n_rej, "n_checks": n_chk, "n_checks_ok": n_ok});
    std::fs::create_dir_all("results").unwrap();
    std::fs::write("results/attacks.json", serde_json::to_string_pretty(&out).unwrap()).unwrap();
    println!("attacks rejected {}/{} ; checks ok {}/{}", n_rej, n_att, n_ok, n_chk);
    for a in out["attacks"].as_array().unwrap() { if a["rejected"] == false { println!("NOT REJECTED: {} -> {}", a["attack"], a["detail"]); } }
    for c in out["checks"].as_array().unwrap() { if c["ok"] == false { println!("CHECK FAILED: {}", c["check"]); } }
}
