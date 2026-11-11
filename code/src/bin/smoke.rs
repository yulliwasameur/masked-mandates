use mmcore::*;
use std::time::Instant;
fn main() {
    let mut r = rng(20261109);
    let t = Instant::now();
    let mut sys = System::setup(&mut r, 1000);
    println!("setup {:?}", t.elapsed());
    let mut scope = [false; NCLS]; scope[0] = true; scope[1] = true; scope[2] = true;
    let root_a = Attrs { id: 101, anc: [0;4], depth: 0, scope: scope.to_vec(), budget: 800, k: 10, exp: 2_000_000, uid: 42 };
    let root = sys.issue_root(&mut r, &root_a).unwrap();
    let inv = Invocation { tool: "hotel".into(), call: "{\"name\":\"search\"}".into(), class: 1, amt: 300, epoch: 7, t: 1_000_000, nonce: "n1".into() };
    let mut tool = Tool::new("hotel", true);
    let t = Instant::now(); let p = sys.present(&mut r, &root, &inv, 0, true).unwrap(); println!("present {:?} size {}", t.elapsed(), p.size());
    let t = Instant::now(); sys.verify(&mut r, &mut tool, &inv, &p).unwrap(); println!("verify {:?}", t.elapsed());
    println!("replay rejected: {}", sys.verify(&mut r, &mut tool, &inv, &p).is_err());
    let mut cs = [false; NCLS]; cs[1] = true;
    let child_a = Attrs { id: 0, anc: [101,0,0,0], depth: 1, scope: cs.to_vec(), budget: 300, k: 5, exp: 1_500_000, uid: 42 };
    let (child, pm, im) = sys.delegate(&mut r, &root, &child_a, 7, 0).unwrap();
    println!("delegate parent {:.0} ms issuer {:.0} ms", pm, im);
    let inv2 = Invocation { nonce: "n2".into(), ..inv.clone() };
    let p2 = sys.present(&mut r, &child, &inv2, 0, true).unwrap();
    sys.verify(&mut r, &mut tool, &inv2, &p2).unwrap(); println!("child ok");
    // escrow open
    let (c1, c2) = p2.esc.unwrap();
    let (d0, pf0) = sys.share(&mut r, 0, &c1); let (d2, pf2) = sys.share(&mut r, 2, &c1);
    assert!(sys.judge_share(0, &c1, &d0, &pf0) && sys.judge_share(2, &c1, &d2, &pf2));
    println!("open ok: {}", sys.open(&c2, [(0, d0), (2, d2)]) == sys.g_uid(42));
    // revoke root -> child must fail (after refreshing witnesses it can't: the ancestor is a member)
    let (_om, _add) = sys.revoke(&[101]).unwrap();
    let inv3 = Invocation { nonce: "n3".into(), ..inv.clone() };
    let p3 = sys.present(&mut r, &child, &inv3, 1, true);
    println!("after revoke: prove ok? {} verify rejected? {}", p3.is_ok(), p3.map(|p| sys.verify(&mut r, &mut tool, &inv3, &p).is_err()).unwrap_or(true));
}
