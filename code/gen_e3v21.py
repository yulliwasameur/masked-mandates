# E3 v2.1 part of gen_tex_v21.py (exec'd there)
X3 = J("e3v21.json"); A3 = X3["aggregate"]
def g3(N, fmt, att, metric, setting="base", group="main", k=50):
    return A3[f"{group}|{setting}|{N}|{fmt}|{k}"]["attackers"][att][metric]
def pcm(x): return f"{100*x:.0f}" if x >= 0.095 or x == 0 else f"{100*x:.1f}"
fl3 = [("clear", "Clear identifiers"), ("pertool", "Per-tool pseudonym"), ("pertool_day", "Per-tool, per-day pseudonym"),
       ("ptej", "Per-tool pseudonym, revealed counter"), ("mm", r"\sys{} / one-time tokens"),
       ("pertool_day_min", "Per-tool per-day, minimized"), ("mm_min", r"\sys{}, minimized")]
assert g3(1000, "mm", "d_full", "profile_recovery")["draws"] == g3(1000, "ott", "d_full", "profile_recovery")["draws"]
rows = []
for f, n in fl3:
    d1 = g3(1000, f, "d_full", "profile_recovery"); o1 = g3(1000, f, "e_oracle", "profile_recovery"); d10 = g3(10000, f, "d_full", "profile_recovery")
    nm1 = g3(1000, f, "id_cls@natural", "calls_correct"); nm10 = g3(10000, f, "id_cls@natural", "calls_correct")
    rows.append(f"{n} & {pcm(d1['mean'])} & {pcm(o1['mean'])} & {pcm(d10['mean'])} & {pcm(nm1['mean'])} & {pcm(nm10['mean'])}\\\\")
W("tab_link.tex", rows + ["\\bottomrule"])
w1 = A3["main|base|1000|mm|50"]["world"]
M("LinkCalls", num(w1["calls_total"]["mean"])); M("LinkTools", "50"); M("LinkDays", "30"); M("LinkSeeds", str(len(X3["seeds"]) if isinstance(X3["seeds"], list) else X3["seeds"]))
P_ = lambda x: f"{100*x:.0f}\\,\\%" if x >= 0.095 or x == 0 else f"{100*x:.1f}\\,\\%"
dmm = g3(1000, "mm", "d_full", "profile_recovery"); M("LinkMMReid", P_(dmm["mean"])); M("LinkMMReidLo", P_(dmm["min"])); M("LinkMMReidHi", P_(dmm["max"]))
M("LinkMMMinReid", P_(g3(1000, "mm_min", "d_full", "profile_recovery")["mean"]))
M("LinkMMUpper", P_(g3(1000, "mm", "e_oracle", "profile_recovery")["mean"]))
M("LinkDayReid", P_(g3(1000, "pertool_day", "d_full", "profile_recovery")["mean"])); M("LinkPertoolReid", P_(g3(1000, "pertool", "d_full", "profile_recovery")["mean"]))
M("LinkPtejReid", P_(g3(1000, "ptej", "d_full", "profile_recovery")["mean"])); M("LinkPtejOracle", P_(g3(1000, "ptej", "e_oracle", "profile_recovery")["mean"]))
M("NameMM", P_(g3(1000, "mm", "id_cls@natural", "calls_correct")["mean"])); M("NameMMMin", P_(g3(1000, "mm_min", "id_cls@natural", "calls_correct")["mean"]))
M("NameMMEvery", P_(g3(1000, "mm", "id_cls@every", "calls_correct")["mean"])); M("NameMMTenK", P_(g3(10000, "mm", "id_cls@natural", "calls_correct")["mean"]))
M("NameMMSess", P_(g3(1000, "mm", "id_sess@natural", "calls_correct")["mean"])); M("NameMMSessPrec", P_(g3(1000, "mm", "id_sess@natural", "precision")["mean"]))
M("NameDay", P_(g3(1000, "pertool_day", "id_cls@natural", "calls_correct")["mean"]))
# coalitions
M("CoalFiveName", P_(A3["coal|base|1000|mm|5"]["attackers"]["id_cls@natural"]["calls_correct"]["mean"]))
# jitter
for J_, nm in [(10000, "Ten"), (60000, "Sixty"), (600000, "SixHundred")]:
    M(f"JitD{nm}", P_(g3(1000, "mm", "d_full", "profile_recovery", setting=f"jitter_ms={J_}", group="sens")["mean"]))
    M(f"JitName{nm}", P_(g3(1000, "mm", "id_cls@natural", "calls_correct", setting=f"jitter_ms={J_}", group="sens")["mean"]))
mx = max(g3(1000, "mm_min", "d_full", "profile_recovery", setting=s.split("|")[1], group="sens")["max"] for s in A3 if s.startswith("sens|") and s.endswith("|mm_min|50"))
M("LinkMMMinSensMax", P_(mx))
M("GapMedS", f"{X3['calibration']['mm']['quantiles_ms']['p50']/1000:.2f}"); M("GapNinetyNineS", f"{X3['calibration']['mm']['quantiles_ms']['p99']/1000:.1f}")
