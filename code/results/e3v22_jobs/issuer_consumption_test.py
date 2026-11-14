import sys, os, json, time, importlib.util
import numpy as np
N, r, var = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
os.environ["E3_ISS_CONSUME"] = var
spec = importlib.util.spec_from_file_location("e3", os.path.expanduser("~/mm95-e3v22/sim/e3v22.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cal = json.load(open(os.path.expanduser("~/mm95-e3v22/cal.json")))
P = dict(m.BASE); seed = m.SEEDS[r]
U, C, pri, lat = m.make_world(N, P, seed, cal)
gm = m.gap_model(C, None)
sA, _, _ = m.track(C, gm, True, None)
im = m.issuer_model(C, gm)
t = time.time(); sI, _, stI = m.track(C, gm, True, None, iss=im); dt = time.time() - t
qa, qi = m.session_quality(sA, C), m.session_quality(sI, C)
out = []
for s in (sA, sI):
    at, _ = m.stage1_atoms(C, "mm", s, seed)
    out.append(m.id_metrics(np.full(len(at), -1), C, C["idnat"]) if False else None)
    import scipy.sparse as sp
    r_ = m.identified_attack(C, at, None, None, C["idnat"], m.visible_fields("mm"), seed, light=True)
    out[-1] = r_["id_sess"]["calls_correct"]
print(f"N={N} r={r} var={var} A exact {qa['tasks_exact']:.3f} P {qa['pair_precision']:.3f} R {qa['pair_recall']:.3f} | I exact {qi['tasks_exact']:.3f} P {qi['pair_precision']:.3f} R {qi['pair_recall']:.3f} cons {stI['delegations_consumed']}/{stI['delegations']} | id_sess A {out[0]:.4f} I {out[1]:.4f}  ({dt:.0f}s)", flush=True)
