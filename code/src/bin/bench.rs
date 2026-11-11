//! E1 micro-benchmarks. Usage: bench <part> ; parts: costs | msgs | depth | rev
//! Writes results/e1_<part>.json with raw samples (ms) and sizes (bytes).
use mmcore::*;
use serde_json::{json, Value};
use std::time::Instant;
use vb_accumulator::prelude::Accumulator;

fn ms(t: Instant) -> f64 { t.elapsed().as_secs_f64() * 1e3 }
fn sc(n: usize, cls: &[usize]) -> Vec<bool> { let mut s = vec![false; n]; for &c in cls { s[c] = true; } s }
fn inv(tool: &str, j: u64, nonce: u64) -> Invocation {
    Invocation { tool: tool.into(), call: format!("{{\"arguments\":{{\"q\":{nonce}}},\"name\":\"search\"}}"), class: 1, amt: 100, epoch: 1 + nonce, t: 1_000_000, nonce: format!("{nonce}") }
}
fn root_attrs(n: usize, id: u64) -> Attrs { Attrs { id, anc: [0; 4], depth: 0, scope: sc(n, &[0, 1, 2]), budget: 800, k: 1000, exp: 2_000_000, uid: 42 } }
fn child_attrs(n: usize, p: &Attrs, id: u64) -> Attrs {
    Attrs { id, anc: [p.id, p.anc[0], p.anc[1], p.anc[2]], depth: p.depth + 1, scope: sc(n, &[1]), budget: p.budget - 10, k: p.k - 1, exp: p.exp - 1, uid: p.uid }
}
/// present+verify `runs` times; returns (present samples, verify samples, size)
fn pv(sys: &System, r: &mut rand::rngs::StdRng, m: &Mandate, runs: usize, esc: bool, base: u64) -> (Vec<f64>, Vec<f64>, usize) {
    let mut tool = Tool::new("bench", esc);
    let (mut p, mut v, mut size) = (vec![], vec![], 0);
    for i in 0..runs {
        let iv = inv("bench", 0, base + i as u64);
        let t = Instant::now(); let pr = sys.present(r, m, &iv, 0, esc).expect("present"); p.push(ms(t));
        let t = Instant::now(); sys.verify(r, &mut tool, &iv, &pr).expect("verify"); v.push(ms(t));
        size = pr.size();
    }
    (p, v, size)
}

fn main() {
    let part = std::env::args().nth(1).unwrap_or("costs".into());
    let seed = 20261109u64;
    let mut r = rng(seed);
    let out: Value = match part.as_str() {
        "costs" => {
            let n_runs: usize = std::env::var("BENCH_N").ok().and_then(|x| x.parse().ok()).unwrap_or(100);
            let mut sys = System::setup(&mut r, 1000);
            let mut issue = vec![];
            let mut roots = vec![];
            for i in 0..30 { let t = Instant::now(); roots.push(sys.issue_root(&mut r, &root_attrs(NCLS, 100 + i)).unwrap()); issue.push(ms(t)); }
            let root = &roots[0];
            let (p0, v0, s0) = pv(&sys, &mut r, root, n_runs, false, 10_000);
            let (p1, v1, s1) = pv(&sys, &mut r, root, n_runs, true, 20_000);
            let (mut dp, mut di) = (vec![], vec![]);
            for i in 0..20 { let (_, a, b) = sys.delegate(&mut r, root, &child_attrs(NCLS, &root.a, 500 + i), 1000 + i, 0).unwrap(); dp.push(a); di.push(b); }
            // escrow opening: two shares with proofs + judge + open
            let iv = inv("bench", 0, 99_999);
            let pr = sys.present(&mut r, root, &iv, 0, true).unwrap();
            let (c1, c2) = pr.esc.unwrap();
            let mut op = vec![];
            for _ in 0..50 {
                let t = Instant::now();
                let (d0, f0) = sys.share(&mut r, 0, &c1); let (d1, f1) = sys.share(&mut r, 1, &c1);
                assert!(sys.judge(&c1, &c2, [(0, d0, f0), (1, d1, f1)], &[7, 9, 42, 43]) == Ok(42));
                op.push(ms(t));
            }
            json!({"n_msgs": NCLS + 12, "bench_n": n_runs, "issue_root": issue, "present": p0, "verify": v0, "present_esc": p1, "verify_esc": v1,
                   "bytes": s0, "bytes_esc": s1, "deleg_parent": dp, "deleg_issuer": di, "open": op})
        }
        "msgs" => {
            let mut pts = vec![];
            for n in [4usize, 8, 12, 16, 20, 28, 36, 44, 52] {
                let mut sys = System::setup_n(&mut r, 100, n);
                let root = sys.issue_root(&mut r, &root_attrs(n, 7)).unwrap();
                let (p, v, s) = pv(&sys, &mut r, &root, 30, false, 0);
                let (mut dp, mut di) = (vec![], vec![]);
                for i in 0..8 { let (_, a, b) = sys.delegate(&mut r, &root, &child_attrs(n, &root.a, 50 + i), 10 + i, 0).unwrap(); dp.push(a); di.push(b); }
                eprintln!("msgs {} done", n + 12);
                pts.push(json!({"n_msgs": n + 12, "present": p, "verify": v, "bytes": s, "deleg_parent": dp, "deleg_issuer": di}));
            }
            json!({"points": pts})
        }
        "depth" => {
            let mut sys = System::setup(&mut r, 100);
            let mut cur = sys.issue_root(&mut r, &root_attrs(NCLS, 1)).unwrap();
            let mut pts = vec![];
            for d in 0..=4u64 {
                let (p, v, s) = pv(&sys, &mut r, &cur, 30, false, 1000 * (d + 1));
                pts.push(json!({"depth": d, "present": p, "verify": v, "bytes": s}));
                if d < 4 { let a = child_attrs(NCLS, &cur.a, 10 + d); cur = sys.delegate(&mut r, &cur, &a, 500 + d, 0).unwrap().0; }
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
            let mut next_id = 1_000_000_000u64;
            let mut pts = vec![];
            for &target in &sizes {
                // grow the revoked set to `target` (ids never issued)
                while (sys.revoked.len() as u64) < target {
                    let step = (target - sys.revoked.len() as u64).min(50_000);
                    let ids: Vec<u64> = (0..step).map(|i| next_id + i).collect(); next_id += step;
                    // growth phase: issuer adds without publishing Omega; the holder then fetches fresh witnesses
                    let add: Vec<ark_bls12_381::Fr> = ids.iter().map(|i| fr(*i)).collect();
                    sys.acc = sys.acc.add_batch(add.clone(), &sys.akp.secret_key, &sys.init, &mut sys.state).unwrap();
                    sys.revoked.extend(add);
                }
                root.nm = root.ids().iter().map(|id| sys.nm_witness(*id).unwrap()).collect();
                // present/verify at exactly `target` revoked ids (before the batch-update phase below)
                let (p, v, _) = pv(&sys, &mut r, &root, 10, false, target);
                let mut wit = vec![];
                for i in 0..10 { let t = Instant::now(); let _ = sys.nm_witness(5_000_000 + i).unwrap(); wit.push(ms(t)); }
                let (mut batch, mut refresh, mut omega_b) = (vec![], vec![], 0usize);
                for _ in 0..10 {
                    let ids: Vec<u64> = (0..100).map(|i| next_id + i).collect(); next_id += 100;
                    let t = Instant::now(); let (om, ad) = sys.revoke(&ids).unwrap(); batch.push(ms(t));
                    omega_b = ser_len(&om);
                    let t = Instant::now(); root.refresh(&ad, &om).unwrap(); refresh.push(ms(t));
                }
                eprintln!("rev {} done", target);
                pts.push(json!({"size": target, "size_after_batches": sys.revoked.len(), "witness": wit, "batch100": batch, "refresh": refresh, "omega_bytes": omega_b, "present": p, "verify": v}));
            }
            let _ = sys.acc.value();
            json!({"points": pts})
        }
        _ => panic!("unknown part"),
    };
    std::fs::create_dir_all("results").unwrap();
    let mut o = out;
    o["seed"] = json!(seed);
    o["threads"] = json!(std::env::var("RAYON_NUM_THREADS").unwrap_or("default".into()));
    std::fs::write(format!("results/e1_{}.json", part), serde_json::to_string(&o).unwrap()).unwrap();
    eprintln!("{} written", part);
}
