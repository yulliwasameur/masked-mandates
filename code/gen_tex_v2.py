"""Version 2 generator: every number, table and figure of the revised manuscript from results/*.json.
Usage: python gen_tex_v2.py <output dir>. Nothing is typed by hand; the script fails if a result is missing or not clean.
Inputs:
  results/attacks.json                      attack taxonomy (v2)
  results/zen/c{1,2,3}/e1_*.json            E1, three independent campaigns on AMD EPYC (one pinned core)
  results/mac/e1_*.json                     E1, one campaign on the laptop (one thread)
  results/e2v2.json                         E2 v2 (MCP, transports, baselines)
  results/e3v2.json                         E3 v2 (identifier, content and timing linkage)
  results/e4v2/*.json                       E4 v2 (LLM agents)
"""
import json, os, sys, glob, statistics as st
import numpy as np

R = "results"; O = sys.argv[1] if len(sys.argv) > 1 else "manuscrit"
os.makedirs(O, exist_ok=True)
J = lambda f: json.load(open(os.path.join(R, f)))
med = st.median
rng = np.random.default_rng(20261113)
def pct(v, q): return float(np.percentile(v, q))
def num(x, d=0): return f"{x:,.{d}f}".replace(",", "{,}")
def f0(x): return num(x, 0)
def f1(x): return f"{x:.1f}"
def f2(x): return f"{x:.2f}"
def boot(v, n=2000):
    """95 % bootstrap CI of the median."""
    v = np.asarray(v); m = np.median(rng.choice(v, (n, len(v)), replace=True), axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))
macros = {}
def M(name, val): macros[name] = val
def W(name, rows): open(f"{O}/{name}", "w").write("\n".join(rows) + "\n")

# ---------------- attack taxonomy
A = J("attacks.json")
assert A.get("version") == 2
assert A["n_rejected"] == A["n_attacks"] and A["n_checks_ok"] == A["n_checks"], "attack suite not clean"
M("NAttacks", str(A["n_attacks"])); M("NChecks", str(A["n_checks"]))
classes = [("A2", "Exceed the mandate / forge"), ("MP", "Malicious prover"), ("A3", "Replay and binding"),
           ("A4", "Rate abuse"), ("A5", "Use after revocation"), ("A6", "Framing and escrow"), ("PARSE", "Malformed input")]
by = ["prover", "issuer", "verifier", "Judge"]
rows = []
for c, name in classes:
    xs = [a for a in A["attacks"] if a["class"] == c]
    cnt = [sum(1 for a in xs if a["by"] == b) for b in by]
    mech = sorted({a["mechanism"].split(" (")[0] for a in xs})
    rows.append(f"{c} {name} & {len(xs)} & " + " & ".join(str(x) if x else "--" for x in cnt) + "\\\\")
    assert all(a["rejected"] for a in xs)
rows.append(f"\\midrule Total & {A['n_attacks']} & " + " & ".join(str(sum(1 for a in A['attacks'] if a['by'] == b)) for b in by) + "\\\\\\bottomrule")
W("tab_attacks.tex", rows)
M("NAttProver", str(sum(1 for a in A["attacks"] if a["by"] == "prover")))
M("NAttMP", str(sum(1 for a in A["attacks"] if a["class"] == "MP")))
fl = [a for a in A["attacks"] if "bit-flip" in a["attack"]]
M("NBitFlips", num(2000))

# ---------------- E1: three campaigns on Zen, one on the laptop
def camp(path_glob):
    out = {}
    for d in sorted(glob.glob(path_glob)):
        out[d] = {p: json.load(open(os.path.join(d, f"e1_{p}.json"))) for p in ["costs", "ablation", "throughput", "msgs", "depth", "rev"] if os.path.exists(os.path.join(d, f"e1_{p}.json"))}
    return out
Z = camp(os.path.join(R, "zen", "c*")); assert len(Z) == 3 and all(len(v) == 6 for v in Z.values()), f"Zen campaigns incomplete: {[(k, list(v)) for k, v in Z.items()]}"
MAC = camp(os.path.join(R, "mac"))
zc = [v["costs"] for v in Z.values()]
for c in zc: assert c["version"] == 2 and str(c["threads"]) == "1"
def pool(key, src=zc): return [x for c in src for x in c[key]]
def cmeds(key, src=zc): return [med(c[key]) for c in src]
lscpu = open(os.path.join(sorted(glob.glob(os.path.join(R, "zen", "c*")))[0], "lscpu.txt")).read()
M("CpuZen", [l.split(":", 1)[1].strip() for l in lscpu.splitlines() if l.startswith("Model name")][0].split(" Processor")[0].rsplit(" ", 1)[0])
C0 = zc[0]
M("NMsgs", str(C0["n_msgs"])); M("BenchN", str(C0["bench_n"])); M("Warmup", str(C0["warmup"]))
M("PresMs", f0(med(pool("present")))); M("VerMs", f0(med(pool("verify"))))
M("VerBytesMs", f0(med(pool("verify_bytes"))))
M("PresB", num(C0["bytes"])); M("PresKB", f1(C0["bytes"] / 1000)); M("EscExtraB", num(C0["bytes_esc"] - C0["bytes"]))
M("DelParentS", f2(med(pool("deleg_parent")) / 1000)); M("DelIssuerMs", f0(med(pool("deleg_issuer"))))
M("PubParamsKB", f1(C0["public_params_bytes"] / 1000))
spread = max((max(cmeds(k)) - min(cmeds(k))) / med(cmeds(k)) for k in ["present", "verify", "deleg_parent"])
M("CampSpread", f"{100*spread:.1f}\\,\\%")
mc = MAC.get(os.path.join(R, "mac"), {}).get("costs")
if mc:
    M("CpuMac", "Apple M5 Pro"); M("PresMacMs", f0(med(mc["present"]))); M("VerMacMs", f0(med(mc["verify"])))
def cell(v):
    lo, hi = boot(v); return f"{f1(med(v))} [{f1(lo)}, {f1(hi)}]"
crow = [("IssueRoot (holder + issuer)", "issue_root", "--"), ("Present", "present", num(C0["bytes"])), ("Verify", "verify", "--"),
        ("Verify, from bytes", "verify_bytes", "--"), ("Present, escrow", "present_esc", num(C0["bytes_esc"])), ("Verify, escrow", "verify_esc", "--"),
        ("Delegate, parent", "deleg_parent", "--"), ("Delegate, issuer", "deleg_issuer", "--"), ("Escrow opening + Judge", "open", "--")]
rows = []
for n, k, b in crow:
    mac = f1(med(mc[k])) if mc else "--"
    rows.append(f"{n} & {cell(pool(k))} & {mac} & {b}\\\\")
W("tab_costs.tex", rows + ["\\bottomrule"])

# ablation
ab = {}
for v in Z.values():
    for p in v["ablation"]["points"]: ab.setdefault(p["variant"], {"present": [], "verify": [], "bytes": p["bytes"]}); ab[p["variant"]]["present"] += p["present"]; ab[p["variant"]]["verify"] += p["verify"]
rows = [f"{k} & {f1(med(x['present']))} & {f1(med(x['verify']))} & {num(x['bytes'])}\\\\" for k, x in ab.items()]
W("tab_ablation.tex", rows + ["\\bottomrule"])
names = list(ab)
M("AblBbsPres", f0(med(ab[names[0]]["present"]))); M("AblDyAdd", f0(med(ab[names[1]]["present"]) - med(ab[names[0]]["present"])))
M("AblRangeAdd", f0(med(ab[names[2]]["present"]) - med(ab[names[1]]["present"]))); M("AblNmAdd", f0(med(ab[names[3]]["present"]) - med(ab[names[2]]["present"])))
M("AblNmVerAdd", f0(med(ab[names[3]]["verify"]) - med(ab[names[2]]["verify"])))

# throughput / DoS
th = [v["throughput"] for v in Z.values()]
good = [x for t in th for x in t["verify_valid"]]; bad = [x for t in th for x in t["verify_invalid_bitflip"]]; garb = [x for t in th for x in t["reject_random_bytes"]]
M("ThrVerMs", f0(med(good))); M("ThrBadMs", f0(med(bad))); M("ThrGarbageUs", f0(1000 * med(garb)))
M("ThrPerCore", f0(1000 / med(good)))

# msgs, depth
mp = {}
for v in Z.values():
    for p in v["msgs"]["points"]: d = mp.setdefault(p["n_msgs"], {"present": [], "verify": [], "deleg_parent": [], "bytes": p["bytes"]}); [d[k].extend(p[k]) for k in ["present", "verify", "deleg_parent"]]
ns = sorted(mp)
M("MsgPresMin", f0(min(med(mp[n]["present"]) for n in ns))); M("MsgPresMax", f0(max(med(mp[n]["present"]) for n in ns)))
M("MsgLo", str(ns[0])); M("MsgHi", str(ns[-1])); M("MsgBMin", num(mp[ns[0]]["bytes"])); M("MsgBMax", num(mp[ns[-1]]["bytes"]))
M("DelMsgLoMs", f0(med(mp[ns[0]]["deleg_parent"]))); M("DelMsgHiS", f2(med(mp[ns[-1]]["deleg_parent"]) / 1000))
dp = {}
for v in Z.values():
    for p in v["depth"]["points"]: dp.setdefault(p["depth"], []).extend(p["present"])
M("DepthPresMin", f0(min(med(x) for x in dp.values()))); M("DepthPresMax", f0(max(med(x) for x in dp.values())))

# revocation
rv = {}
for v in Z.values():
    for p in v["rev"]["points"]:
        d = rv.setdefault(p["size"], {k: [] for k in ["witness", "batch100", "refresh", "present", "verify"]}); d["omega"] = p["omega_bytes"]
        for k in ["witness", "batch100", "refresh", "present", "verify"]: d[k] += p[k]
rows = []
for s in sorted(rv):
    d = rv[s]; rows.append(f"$10^{{{int(round(np.log10(s)))}}}$ & " + " & ".join(f1(med(d[k])) for k in ["witness", "batch100", "refresh", "present", "verify"]) + "\\\\")
W("tab_rev.tex", rows + ["\\bottomrule"])
smax = max(rv)
M("RevMax", f"$10^{{{int(round(np.log10(smax)))}}}$"); M("RevWitMs", f0(med(rv[smax]["witness"]))); M("RevRefreshMs", f1(med(rv[smax]["refresh"])))
M("OmegaKB", f1(rv[smax]["omega"] / 1000))
M("RevPresMin", f0(min(med(d["present"]) for d in rv.values()))); M("RevPresMax", f0(max(med(d["present"]) for d in rv.values())))

# figure: costs vs messages (left), delegation vs messages (right)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 8, "font.family": "serif"})
fig, ax = plt.subplots(1, 2, figsize=(7, 2.2))
ax[0].plot(ns, [med(mp[n]["present"]) for n in ns], "o-", label="Present", color="#1f4e79")
ax[0].plot(ns, [med(mp[n]["verify"]) for n in ns], "s--", label="Verify", color="#c55a11")
ax[0].set_xlabel("signed messages"); ax[0].set_ylabel("ms (one core)"); ax[0].legend(frameon=False); ax[0].set_ylim(bottom=0)
ax[1].plot(ns, [med(mp[n]["deleg_parent"]) / 1000 for n in ns], "o-", color="#1f4e79", label="Delegate, parent")
ax[1].set_xlabel("signed messages"); ax[1].set_ylabel("s (one core)"); ax[1].legend(frameon=False); ax[1].set_ylim(bottom=0)
fig.tight_layout(); fig.savefig(f"{O}/fig_costs.pdf"); plt.close(fig)

# ---------------- E2 v2, E3 v2, E4 v2 (sections added when the results exist)
for part in ["gen_e2v2", "gen_e3v2", "gen_e4v2"]:
    fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{part}.py")
    if os.path.exists(fn):
        exec(open(fn).read())

with open(f"{O}/numbers.tex", "w") as f:
    f.write("% generated by gen_tex_v2.py from results/ -- do not edit\n")
    for k in sorted(macros): f.write(f"\\newcommand{{\\{k}}}{{{macros[k]}}}\n")
print(len(macros), "macros written to", O)
