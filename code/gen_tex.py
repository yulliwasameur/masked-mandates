"""Generates every number, table and figure of the manuscript from results/*.json.
Outputs (in manuscrit/): numbers.tex, tab_attacks.tex, tab_costs.tex, tab_rev.tex, tab_e2e.tex, tab_link.tex,
tab_timing.tex, fig_costs.pdf, fig_timing.pdf. Nothing is typed by hand.
"""
import json, os, statistics as st, sys
import numpy as np

R = "results"; O = sys.argv[1] if len(sys.argv) > 1 else "manuscrit"
os.makedirs(O, exist_ok=True)
J = lambda f: json.load(open(os.path.join(R, f)))
med = st.median
def pct(v, q): return float(np.percentile(v, q))
def f0(x): return f"{x:,.0f}".replace(",", "{,}")
def f1(x): return f"{x:.1f}"
def f2(x): return f"{x:.2f}"
def num(x, d=0):
    s = f"{x:,.{d}f}"; return s.replace(",", "{,}")

macros = {}
def M(name, val): macros[name] = val

# ---------------- attacks
A = J("attacks.json")
M("NAttacks", str(A["n_attacks"])); M("NChecks", str(A["n_checks"]))
assert A["n_rejected"] == A["n_attacks"] and A["n_checks_ok"] == A["n_checks"], "attack suite not clean"
assert all(a["by"] in ("prover", "issuer", "verifier") for a in A["attacks"]), "attack rejected for an unexpected cause"
lab = {"A2": "A2", "A3": "A3", "A4": "A4", "A5": "A5", "A6": "A6"}
rows = []
for a in A["attacks"]:
    by = "P" if a["by"] == "prover" else "V"
    rows.append(f"\\parbox[t]{{0.8\\columnwidth}}{{\\raggedright {lab[a['class']]}: {a['attack']}}} & rejected ({by})\\\\")
rows.append(f"\\midrule {A['n_checks']} correctness checks & all pass\\\\ \\bottomrule")
rows.append(r"\multicolumn{2}{@{}l}{\scriptsize P: the cheating prover cannot build the proof; V: rejected by the tool, the issuer or the Judge.}\\")
open(f"{O}/tab_attacks.tex", "w").write("\n".join(rows) + "\n")

# ---------------- costs
C = J("e1_costs.json")
def cell(v): return f"{f1(med(v))} [{f1(pct(v,5))}, {f1(pct(v,95))}]"
M("NMsgs", str(C["n_msgs"])); M("BenchN", str(C["bench_n"]))
M("PresMs", f0(med(C["present"]))); M("VerMs", f0(med(C["verify"])))
M("PresB", num(C["bytes"])); M("PresKB", f1(C["bytes"] / 1000)); M("EscExtraB", num(C["bytes_esc"] - C["bytes"]))
M("DelParentS", f2(med(C["deleg_parent"]) / 1000)); M("DelIssuerMs", f0(med(C["deleg_issuer"])))
M("Threads", str(C.get("threads", "1")))
crow = [("IssueRoot (holder + issuer)", C["issue_root"], "--"),
        ("Present", C["present"], num(C["bytes"])), ("Verify", C["verify"], "--"),
        ("Present, with escrow", C["present_esc"], num(C["bytes_esc"])), ("Verify, with escrow", C["verify_esc"], "--"),
        ("Delegate, parent + child", C["deleg_parent"], "--"), ("Delegate, issuer", C["deleg_issuer"], "--"),
        ("Escrow opening (2 shares, Judge)", C["open"], "--")]
open(f"{O}/tab_costs.tex", "w").write("\n".join(f"{n} & {cell(v)} & {b}\\\\" for n, v, b in crow) + "\n\\bottomrule\n")

# ---------------- msgs / depth
Mm = J("e1_msgs.json")["points"]
pm = [med(p["present"]) for p in Mm]
M("MsgPresMin", f0(min(pm))); M("MsgPresMax", f0(max(pm)))
lo = [p for p in Mm if p["n_msgs"] == 16][0]; hi = [p for p in Mm if p["n_msgs"] == 64][0]
M("MsgBMin", num(lo["bytes"])); M("MsgBMax", num(hi["bytes"]))
M("DelMsgLo", str(lo["n_msgs"])); M("DelMsgLoMs", f0(med(lo["deleg_parent"])))
M("DelMsgHi", str(hi["n_msgs"])); M("DelMsgHiS", f2(med(hi["deleg_parent"]) / 1000))
D = J("e1_depth.json")["points"]
dp = [med(p["present"]) for p in D]
M("DepthPresMin", f0(min(dp))); M("DepthPresMax", f0(max(dp)))

# ---------------- revocation
RV = J("e1_rev.json")["points"]
rr = []
for p in RV:
    e = int(round(np.log10(p["size"])))
    rr.append(f"$10^{e}$ & {f1(med(p['witness']))} & {f1(med(p['batch100']))} & {f1(med(p['refresh']))} & {f0(med(p['present']))} & {f0(med(p['verify']))}\\\\")
open(f"{O}/tab_rev.tex", "w").write("\n".join(rr) + "\n\\bottomrule\n")
big = RV[-1]
M("RevMax", f"$10^{int(round(np.log10(big['size'])))}$")
rp = [med(p["present"]) for p in RV]
M("RevPresMin", f0(min(rp))); M("RevPresMax", f0(max(rp)))
M("RevWitMs", f0(med(big["witness"]))); M("OmegaKB", f1(big["omega_bytes"] / 1000)); M("RevRefreshMs", f1(med(big["refresh"])))

# ---------------- E2
E = J("e2.json")
M("EMcpSdk", E["mcp_sdk"]); M("EPy", E["python"]); M("ECalls", str(E["n_calls"]))
name = {"none": "No authorisation", "jwt": "Mandate JWT + PoP JWT", "biscuit": "Biscuit (2 attenuations)", "macaroon": "Macaroon (2 caveats)",
        "mm": r"\sys{}", "mm_esc": r"\sys{}, escrow"}
link = {"none": "--", "jwt": "yes", "biscuit": "yes", "macaroon": "yes", "mm": "no", "mm_esc": r"no$^\dagger$"}
er = []; stats = {}
for m in E["modes"]:
    c = m["calls"]; tot = [x["total_ms"] for x in c]
    s = {"prep": med([x["prep_ms"] for x in c]), "ver": med([x["verify_ms"] for x in c]), "tot": med(tot), "p95": pct(tot, 95),
         "bytes": med([x["meta_bytes"] for x in c])}
    stats[m["mode"]] = s
    er.append(f"{name[m['mode']]} & {f2(s['prep'])} & {f2(s['ver'])} & {f2(s['tot'])} & {f2(s['p95'])} & {num(s['bytes'])} & {link[m['mode']]}\\\\")
    if m["mode"] != "none":
        assert not m["replay_same_accepted"] and not m["replay_other_accepted"], f"replay accepted in {m['mode']}"
open(f"{O}/tab_e2e.tex", "w").write("\n".join(er) + "\n\\bottomrule\n")
M("EtoeNone", f1(stats["none"]["tot"]))
M("EBaseMaxAdd", f1(max(stats[k]["tot"] - stats["none"]["tot"] for k in ("jwt", "biscuit", "macaroon"))))
M("EPrepMMr", f0(stats["mm"]["prep"])); M("EVerMMr", f0(stats["mm"]["ver"])); M("EtoeMMr", f0(stats["mm"]["tot"]))

# ---------------- E3
X = J("e3.json")
idf = X["identifier"]
M("LinkUsers", num(idf["users"])); M("LinkRecords", num(idf["calls"]))
fm = idf["formats"]
def p100(x): return f"{100*x:.1f}\\,\\%"
M("LinkRecPertool", p100(fm["pertool"]["recall"])); M("LinkRecEpoch", p100(fm["epoch"]["recall"]))
lr = [("Clear token (principal, chain)", fm["clear"]), ("Stable per-tool pseudonym", fm["pertool"]), ("Per-tool, per-day pseudonym", fm["epoch"]),
      (r"\sys{} (per-call pseudonym)", fm["mm"])]
open(f"{O}/tab_link.tex", "w").write("\n".join(f"{n} & {v['recall']:.3f} & {v['session_recall']:.3f}\\\\" for n, v in lr) + "\n\\bottomrule\n")
T = X["timing"]
def tget(u, j, d): return [t for t in T if t["users"] == u and t["jitter_s"] == j and t["delta_s"] == d][0]
tr = []
for u in (100, 1000, 10000):
    for j in (0, 600):
        cells = []
        for d in (10, 60, 600):
            t = tget(u, j, d); cells.append(f"{t['session_recall']:.2f} / {t['precision']:.2f}")
        tr.append(f"{num(u)} & {j} & " + " & ".join(cells) + "\\\\")
open(f"{O}/tab_timing.tex", "w").write("\n".join(tr) + "\n\\bottomrule\n")
M("TimSessRec", f"{tget(1000,0,600)['session_recall']:.2f}")
M("TimPrecHSixty", f"{tget(100,0,60)['precision']:.2f}"); M("TimPrecKSixty", f"{tget(1000,0,60)['precision']:.2f}"); M("TimPrecTTSixty", f"{tget(10000,0,60)['precision']:.3f}")
M("TimSessRecSixty", f"{tget(1000,0,60)['session_recall']:.2f}"); M("TimSessRecJit", f"{tget(1000,600,60)['session_recall']:.2f}")

# ---------------- environment
env = J("env.json")
M("Cpu", env["cpu"]); M("Rustc", env["rustc"])

with open(f"{O}/numbers.tex", "w") as f:
    f.write("% generated by gen_tex.py from results/*.json -- do not edit\n")
    for k in sorted(macros):
        f.write(f"\\newcommand{{\\{k}}}{{{macros[k]}}}\n")

# ---------------- figures
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family": "serif", "font.size": 8})
fig, ax = plt.subplots(1, 2, figsize=(7.16, 2.2))
x = [p["n_msgs"] for p in Mm]
for key, lbl, mk in (("present", "Present", "o"), ("verify", "Verify", "s")):
    y = [med(p[key]) for p in Mm]; lo_ = [med(p[key]) - pct(p[key], 5) for p in Mm]; hi_ = [pct(p[key], 95) - med(p[key]) for p in Mm]
    ax[0].errorbar(x, y, yerr=[lo_, hi_], marker=mk, ms=3, capsize=2, lw=1, label=lbl)
ax[0].set_xlabel("signed messages"); ax[0].set_ylabel("ms"); ax[0].set_ylim(bottom=0); ax[0].legend(frameon=False); ax[0].grid(alpha=.3)
for key, lbl, mk in (("deleg_parent", "Parent + child", "o"), ("deleg_issuer", "Issuer", "s")):
    ax[1].plot(x, [med(p[key]) / 1000 for p in Mm], marker=mk, ms=3, lw=1, label=lbl)
ax[1].set_xlabel("signed messages"); ax[1].set_ylabel("s"); ax[1].set_ylim(bottom=0); ax[1].legend(frameon=False); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(f"{O}/fig_costs.pdf")
fig, a = plt.subplots(figsize=(3.4, 2.2))
for u, mk in ((100, "o"), (1000, "s"), (10000, "^")):
    ds = (10, 60, 600); a.plot(ds, [tget(u, 0, d)["precision"] for d in ds], marker=mk, ms=3, lw=1, label=f"{u:,} users")
a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel(r"window $\delta$ (s)"); a.set_ylabel("precision"); a.legend(frameon=False); a.grid(alpha=.3, which="both")
fig.tight_layout(); fig.savefig(f"{O}/fig_timing.pdf")
print("generated", len(macros), "macros")
