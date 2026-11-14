//! E1 micro-benchmarks, version 2.2 (n_msgs = L = 13 + n, the BBS+ message count of the layout). Usage: bench <part> ; parts: costs | msgs | depth | rev | ablation | throughput
//! Writes results/e1_<part>.json with raw samples (ms) and sizes (bytes). Every timed loop starts with
//! WARMUP discarded runs; every reported point has at least 30 samples. Verification is reported both on the
//! in-memory presentation and from bytes (deserialization included), with a verifier holding public data only.
use mmcore::*;
use serde_json::{json, Value};
use std::time::Instant;
use ark_std::rand::RngCore;

const WARMUP: usize = 5;
fn ms(t: Instant) -> f64 { t.elapsed().as_secs_f64() * 1e3 }
fn sc(n: usize, cls: &[usize]) -> Vec<bool> { let mut s = vec![false; n]; for &c in cls { s[c] = true; } s }
fn inv(tool: &str, nonce: u64) -> Invocation {
    Invocation { tool: tool.into(), call: format!("{{\"arguments\":{{\"q\":{nonce}}},\"name\":\"search\"}}"), class: 1, amt: 100, cur: "EUR".into(), epoch: 1 + nonce, t: 1_000_000, nonce: format!("{nonce}") }
}
fn root_attrs(n: usize, uid: u64) -> Attrs { Attrs { id: 0, anc: [0; 4], depth: 0, scope: sc(n, &[0, 1, 2]), lo: 0, budget: 800, k: 1000, exp: 2_000_000, uid } }
fn child_attrs(n: usize, p: &Attrs) -> Attrs { Attrs::child_of(p, sc(n, &[1]), p.budget - 10, p.k - 1, p.exp - 1) }
/// present + verify (in memory) + verify from bytes with a public-only verifier; returns samples and size.
fn pv(sys: &System, pubv: &Pub, r: &mut rand::rngs::StdRng, m: &Mandate, runs: usize, esc: bool, base: u64) -> Value {
    let tool_name = "https://bench.example|search";
    let mut tool = Tool::new(tool_name, esc);
    let mut tool2 = Tool::new(tool_name, esc);
    let (mut p, mut v, mut vb, mut size) = (vec![], vec![], vec![], 0);
    for i in 0..(runs + WARMUP) {
        let iv = inv(tool_name, base + i as u64);
        let t = Instant::now(); let pr = sys.present(r, m, &iv, 0, esc).expect("present"); let tp = ms(t);
        let bytes = pr.to_bytes();
        let t = Instant::now(); sys.verify(r, &mut tool, &iv, &pr).expect("verify"); let tv = ms(t);
        let t = Instant::now(); let q = Presentation::from_bytes(&bytes).expect("parse"); pubv.verify(r, &mut tool2, &iv, &q).expect("verify bytes"); let tvb = ms(t);
        if i >= WARMUP { p.push(tp); v.push(tv); vb.push(tvb); }
        size = bytes.len();
    }
    json!({"present": p, "verify": v, "verify_bytes": vb, "bytes": size})
}

fn main() {
    let part = std::env::args().nth(1).unwrap_or("costs".into());
    let seed: u64 = std::env::var("BENCH_SEED").ok().and_then(|x| x.parse().ok()).unwrap_or(20261109);
    let mut r = rng(seed);
    let out: Value = match part.as_str() {
        "costs" => {
            let n_runs: usize = std::env::var("BENCH_N").ok().and_then(|x| x.parse().ok()).unwrap_or(100);
            let mut sys = System::setup(&mut r, 1000);
            let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
            let mut issue = vec![];
            let mut roots = vec![];
            for i in 0..(30 + WARMUP) { let t = Instant::now(); let m = sys.issue_root(&mut r, &root_attrs(NCLS, 100 + i as u64)).unwrap(); if i >= WARMUP { issue.push(ms(t)); } roots.push(m); }
            let root = roots[0].clone();
            let plain = pv(&sys, &pubv, &mut r, &root, n_runs, false, 10_000);
            let escr = pv(&sys, &pubv, &mut r, &root, n_runs, true, 20_000);
            let (mut dp, mut di) = (vec![], vec![]);
            for i in 0..(30 + WARMUP) { let (_, a, b) = sys.delegate(&mut r, &root, &child_attrs(NCLS, &root.a), 1000 + i as u64, 0).unwrap(); if i >= WARMUP { dp.push(a); di.push(b); } }
            // escrow opening: four shares with Chaum–Pedersen proofs + Judge (principal and mandate)
            let iv = inv("https://bench.example|pay", 99_999);
            let pr = sys.present(&mut r, &root, &iv, 0, true).unwrap();
            let c = pr.esc.unwrap();
            let mut op = vec![];
            for i in 0..(50 + WARMUP) {
                let t = Instant::now();
                let sh = |r: &mut _, k: usize, x: &G1| { let (d, pf) = sys.share(r, k, x); (k, d, pf) };
                let s1 = [sh(&mut r, 0, &c[0]), sh(&mut r, 1, &c[0])]; let s2 = [sh(&mut r, 0, &c[2]), sh(&mut r, 1, &c[2])];
                assert!(sys.judge(&c, s1, s2) == Ok((100, root.a.id)));
                if i >= WARMUP { op.push(ms(t)); }
            }
            let pk_bytes = sys.p.to_bytes().len();
            json!({"n_msgs": Lay { n: NCLS }.l(), "bench_n": n_runs, "warmup": WARMUP, "issue_root": issue, "present": plain["present"], "verify": plain["verify"], "verify_bytes": plain["verify_bytes"],
                   "present_esc": escr["present"], "verify_esc": escr["verify"], "verify_bytes_esc": escr["verify_bytes"],
                   "bytes": plain["bytes"], "bytes_esc": escr["bytes"], "deleg_parent": dp, "deleg_issuer": di, "open": op, "public_params_bytes": pk_bytes})
        }
        "ablation" => {
            let mut sys = System::setup(&mut r, 1000);
            let root = sys.issue_root(&mut r, &root_attrs(NCLS, 42)).unwrap();
            let mut pts = vec![];
            for (name, parts, esc) in [("BBS+ only", Parts { dy: false, ranges: false, nm: false, revealed: false }, false),
                                       ("+ pseudonym, revealed counter (k-TAA style)", Parts { dy: false, ranges: false, nm: false, revealed: true }, false),
                                       ("+ pseudonym (hidden counter)", Parts { dy: true, ranges: false, nm: false, revealed: false }, false),
                                       ("+ amount and expiry ranges", Parts { dy: true, ranges: true, nm: false, revealed: false }, false),
                                       ("+ 5 non-membership (full)", Parts::ALL, false),
                                       ("full + escrow", Parts::ALL, true)] {
                let (mut p, mut v, mut b) = (vec![], vec![], 0);
                for i in 0..(30 + WARMUP) {
                    let iv = inv("https://bench.example|search", 50_000 + i as u64);
                    let (tp, tv, bytes) = sys.p.ablation(&mut r, &root, &iv, (i % 900) as u64, parts, esc).unwrap();
                    if i >= WARMUP { p.push(tp); v.push(tv); b = bytes; }
                }
                eprintln!("ablation {name} done");
                pts.push(json!({"variant": name, "present": p, "verify": v, "bytes": b}));
            }
            json!({"points": pts})
        }
        "throughput" => {
            // single-core verification throughput, and the cost of rejecting invalid presentations
            let mut sys = System::setup(&mut r, 1000);
            let root = sys.issue_root(&mut r, &root_attrs(NCLS, 42)).unwrap();
            let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
            let tool_name = "https://bench.example|search";
            let mut good = vec![]; let mut bad = vec![]; let mut garbage = vec![];
            let n = 60;
            let pres: Vec<(Invocation, Vec<u8>)> = (0..n + WARMUP).map(|i| { let iv = inv(tool_name, 70_000 + i as u64); let b = sys.present(&mut r, &root, &iv, (i % 900) as u64, false).unwrap().to_bytes(); (iv, b) }).collect();
            let mut tool = Tool::new(tool_name, false);
            let t_all = Instant::now();
            for (i, (iv, b)) in pres.iter().enumerate() {
                let t = Instant::now(); let q = Presentation::from_bytes(b).unwrap(); pubv.verify(&mut r, &mut tool, iv, &q).unwrap(); if i >= WARMUP { good.push(ms(t)); }
            }
            let wall_good = ms(t_all);
            for (i, (iv, b)) in pres.iter().enumerate() {
                // invalid: one flipped bit in the proof body (parses, fails verification)
                let mut bb = b.clone(); let pos = r.next_u64() as usize % bb.len(); bb[pos] ^= 1 << (r.next_u64() % 8);
                let t = Instant::now(); let ok = Presentation::from_bytes(&bb).ok().map(|q| pubv.verify(&mut r, &mut Tool::new(tool_name, false), iv, &q).is_ok()).unwrap_or(false); if i >= WARMUP { bad.push(ms(t)); }
                assert!(!ok);
                // garbage of the right length: rejected at parsing
                let mut gb = vec![0u8; b.len()]; r.fill_bytes(&mut gb);
                let t = Instant::now(); let _ = Presentation::from_bytes(&gb).ok().map(|q| pubv.verify(&mut r, &mut Tool::new(tool_name, false), iv, &q).is_ok()); if i >= WARMUP { garbage.push(ms(t)); }
            }
            json!({"verify_valid": good, "verify_invalid_bitflip": bad, "reject_random_bytes": garbage, "wall_ms_valid": wall_good, "n": n})
        }
        "msgs" => {
            let mut pts = vec![];
            for n in [4usize, 8, 12, 16, 20, 28, 36, 44, 52] {
                let mut sys = System::setup_n(&mut r, 100, n);
                let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
                let root = sys.issue_root(&mut r, &root_attrs(n, 7)).unwrap();
                let res = pv(&sys, &pubv, &mut r, &root, 30, false, 0);
                let (mut dp, mut di) = (vec![], vec![]);
                for i in 0..(30 + WARMUP) { let (_, a, b) = sys.delegate(&mut r, &root, &child_attrs(n, &root.a), 10 + i as u64, 0).unwrap(); if i >= WARMUP { dp.push(a); di.push(b); } }
                eprintln!("msgs {} done", Lay { n }.l());
                pts.push(json!({"n_msgs": Lay { n }.l(), "present": res["present"], "verify": res["verify"], "verify_bytes": res["verify_bytes"], "bytes": res["bytes"], "deleg_parent": dp, "deleg_issuer": di}));
            }
            json!({"points": pts})
        }
        "depth" => {
            let mut sys = System::setup(&mut r, 100);
            let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
            let mut cur = sys.issue_root(&mut r, &root_attrs(NCLS, 1)).unwrap();
            let mut pts = vec![];
            for d in 0..=4u64 {
                let res = pv(&sys, &pubv, &mut r, &cur, 30, false, 1000 * (d + 1));
                pts.push(json!({"depth": d, "present": res["present"], "verify": res["verify"], "verify_bytes": res["verify_bytes"], "bytes": res["bytes"]}));
                if d < 4 { let a = child_attrs(NCLS, &cur.a); cur = sys.delegate(&mut r, &cur, &a, 500 + d, 0).unwrap().0; }
            }
            json!({"points": pts})
        }
        "rev" => {
            let sizes: Vec<u64> = std::env::var("REV_SIZES").ok().map(|x| x.split(',').map(|y| y.parse().unwrap()).collect()).unwrap_or(vec![1_000, 10_000, 100_000, 1_000_000]);
            let maxs = *sizes.iter().max().unwrap();
            let t = Instant::now();
            let mut sys = System::setup(&mut r, maxs + 10_000);
            eprintln!("setup for {} in {:.0} ms", maxs, ms(t));
            let mut root = sys.issue_root(&mut r, &root_attrs(NCLS, 1)).unwrap();
            let mut next_id = 1u64 << 62;
            let mut pts = vec![];
            for &target in &sizes {
                while (sys.revoked.len() as u64) < target {
                    let step = (target - sys.revoked.len() as u64).min(50_000);
                    let ids: Vec<u64> = (0..step).map(|i| next_id + i).collect(); next_id += step;
                    let add: Vec<ark_bls12_381::Fr> = ids.iter().map(|i| fr(*i)).collect();
                    sys.acc = sys.acc.add_batch(add.clone(), &sys.akp.secret_key, &sys.init, &mut sys.state).unwrap();
                    sys.revoked.extend(add);
                }
                sys.p.accv = *vb_accumulator::prelude::Accumulator::value(&sys.acc);
                root.nm = root.ids().iter().map(|id| sys.nm_witness(*id).unwrap()).collect();
                let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
                let res = pv(&sys, &pubv, &mut r, &root, 30, false, target);
                let mut wit = vec![];
                for i in 0..(30 + WARMUP) { let t = Instant::now(); let _ = sys.nm_witness(5_000_000 + i as u64).unwrap(); if i >= WARMUP { wit.push(ms(t)); } }
                let (mut batch, mut refresh, mut omega_b) = (vec![], vec![], 0usize);
                for i in 0..(30 + WARMUP) {
                    let ids: Vec<u64> = (0..100).map(|k| next_id + k).collect(); next_id += 100;
                    let t = Instant::now(); let (om, ad) = sys.revoke(&ids).unwrap(); let tb = ms(t);
                    omega_b = ser_len(&om);
                    let t = Instant::now(); root.refresh(&ad, &om).unwrap(); let tr = ms(t);
                    if i >= WARMUP { batch.push(tb); refresh.push(tr); }
                }
                eprintln!("rev {} done", target);
                pts.push(json!({"size": target, "size_after_batches": sys.revoked.len(), "witness": wit, "batch100": batch, "refresh": refresh, "omega_bytes": omega_b,
                                "present": res["present"], "verify": res["verify"], "verify_bytes": res["verify_bytes"]}));
            }
            json!({"points": pts})
        }
        _ => panic!("unknown part"),
    };
    std::fs::create_dir_all("results").unwrap();
    let mut o = out;
    o["seed"] = json!(seed);
    o["version"] = json!("2.2");
    for k in ["GIT_COMMIT", "BIN_SHA256", "PIN", "HOSTNAME", "SLURM_JOB_ID"] { o[k.to_lowercase()] = json!(std::env::var(k).unwrap_or_default()); }
    o["threads"] = json!(std::env::var("RAYON_NUM_THREADS").unwrap_or("default".into()));
    let dir = std::env::var("RESULTS_DIR").unwrap_or("results".into());
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(format!("{dir}/e1_{}.json", part), serde_json::to_string(&o).unwrap()).unwrap();
    eprintln!("{} written", part);
}
