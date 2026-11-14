use mmcore::*;
use std::time::Instant;
fn main() {
    let mut r = rng(20261109);
    let t = Instant::now();
    let mut sys = System::setup(&mut r, 1000);
    println!("setup {:?}", t.elapsed());
    let mut scope = [false; NCLS]; scope[0] = true; scope[1] = true; scope[2] = true;
    let root_a = Attrs { id: 0, anc: [0; 4], depth: 0, scope: scope.to_vec(), lo: 0, budget: 800, k: 10, exp: 2_000_000, uid: 42 };
    let root = sys.issue_root(&mut r, &root_a).unwrap();
    println!("root id {}", root.a.id);
    let inv = Invocation { tool: "https://hotel.example|search".into(), call: "{\"name\":\"search\"}".into(), class: 1, amt: 300, cur: "EUR".into(), epoch: 7, t: 1_000_000, nonce: "n1".into() };
    let mut tool = Tool::new(&inv.tool, true);
    let t = Instant::now(); let p = sys.present(&mut r, &root, &inv, 0, true).unwrap(); println!("present {:?} size {}", t.elapsed(), p.size());
    let t = Instant::now(); sys.verify(&mut r, &mut tool, &inv, &p).unwrap(); println!("verify {:?}", t.elapsed());
    println!("replay rejected: {}", sys.verify(&mut r, &mut tool, &inv, &p).is_err());
    // public-only verifier
    let pubv = Pub::from_bytes(&sys.p.to_bytes()).unwrap();
    let mut tool2 = Tool::new(&inv.tool, true);
    let inv_b = Invocation { nonce: "n1b".into(), ..inv.clone() };
    let pb = sys.present(&mut r, &root, &inv_b, 1, true).unwrap();
    println!("public-only verifier ok: {}", pubv.verify(&mut r, &mut tool2, &inv_b, &Presentation::from_bytes(&pb.to_bytes()).unwrap()).is_ok());
    // counter beyond quota cannot be proved
    println!("j = k refused: {}", sys.present(&mut r, &root, &Invocation { nonce: "nk".into(), ..inv.clone() }, 10, true).is_err());
    let mut cs = [false; NCLS]; cs[1] = true;
    let child_a = Attrs::child_of(&root.a, cs.to_vec(), 300, 5, 1_500_000);
    let (child, pm, im) = sys.delegate(&mut r, &root, &child_a, 7, 0).unwrap();
    println!("delegate parent {:.0} ms issuer {:.0} ms, child id {}", pm, im, child.a.id);
    let inv2 = Invocation { nonce: "n2".into(), ..inv.clone() };
    println!("child interval [{}, {})", child.a.lo, child.a.k);
    let p2 = sys.present(&mut r, &child, &inv2, 0, true).unwrap(); // offsets are relative to the interval
    sys.verify(&mut r, &mut tool, &inv2, &p2).unwrap(); println!("child ok");
    // the child cannot use a counter below its interval (reserved for the parent)
    println!("child counter beyond its interval refused: {}", sys.present(&mut r, &child, &Invocation { nonce: "n2c".into(), ..inv.clone() }, child.a.k - child.a.lo, true).is_err());
    // one pseudonym space per tree: a counter already used in the tree is rejected
    let inv2b = Invocation { nonce: "n2b".into(), ..inv.clone() };
    let p2b = sys.present(&mut r, &root, &inv2b, child.a.lo - root.a.lo, true).unwrap();
    println!("same counter used twice in the tree rejected: {}", sys.verify(&mut r, &mut tool, &inv2b, &p2b).is_err());
    // escrow opens to (principal, mandate)
    let c = p2.esc.unwrap();
    let sh = |r: &mut _, i, x: &G1| { let (d, pf) = sys.share(r, i, x); (i, d, pf) };
    let s1 = [sh(&mut r, 0, &c[0]), sh(&mut r, 2, &c[0])];
    let s2 = [sh(&mut r, 0, &c[2]), sh(&mut r, 2, &c[2])];
    println!("judge: {:?} (expected (42, {}))", sys.judge(&c, s1, s2), child.a.id);
    // revoke the root: the child can no longer present
    let (_om, _add) = sys.revoke(&[root.a.id]).unwrap();
    let inv3 = Invocation { nonce: "n3".into(), ..inv.clone() };
    let p3 = sys.present(&mut r, &child, &inv3, 1, true);
    println!("after revoke: prove ok? {} verify rejected? {}", p3.is_ok(), p3.map(|p| sys.verify(&mut r, &mut tool, &inv3, &p).is_err()).unwrap_or(true));
}
