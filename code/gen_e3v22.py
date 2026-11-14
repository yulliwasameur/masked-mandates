# E3 v2.2 part of gen_tex_v21.py (exec'd there; replaces gen_e3v21.py: same macro names, plus seed ranges, load sweep,
# issuer-in-the-coalition attacker and calibration source). Needs J, M, W, num, O from gen_tex_v21.py.
import shutil as _sh
X3 = J("e3v22.json"); A3 = X3["aggregate"]
def g3(N, fmt, att, metric, setting="base", group="main", k=50):
    return A3[f"{group}|{setting}|{N}|{fmt}|{k}"]["attackers"][att][metric]
def pcm(x): return f"{100*x:.0f}" if x >= 0.095 or x == 0 else f"{100*x:.1f}"
def rng3(s): return f"{pcm(s['mean'])}\\,{{\\scriptsize[{pcm(s['min'])}--{pcm(s['max'])}]}}"   # mean [min--max over seeds], in %
fl3 = [("clear", "Clear identifiers"), ("pertool", "Per-tool pseudonym"), ("pertool_day", "Per-tool, per-day pseudonym"),
       ("ptej", "Per-tool pseudonym, revealed counter"), ("mm", r"\sys{} / one-time tokens"),
       ("pertool_day_min", "Per-tool per-day, minimized"), ("mm_min", r"\sys{}, minimized")]
assert g3(1000, "mm", "d_full", "profile_recovery")["draws"] == g3(1000, "ott", "d_full", "profile_recovery")["draws"]
assert X3["calibration"]["source"][0].startswith("results/e4v21/"), "E3 v2.2 must be calibrated on E4 v2.1"
rows = []; rows_m = []
for f, n in fl3:
    d1 = g3(1000, f, "d_full", "profile_recovery"); o1 = g3(1000, f, "e_oracle", "profile_recovery"); d10 = g3(10000, f, "d_full", "profile_recovery")
    nm1 = g3(1000, f, "id_cls@natural", "calls_correct"); nm10 = g3(10000, f, "id_cls@natural", "calls_correct")
    rows.append(f"{n} & {rng3(d1)} & {rng3(o1)} & {rng3(d10)} & {rng3(nm1)} & {rng3(nm10)}\\\\")
    rows_m.append(f"{n} & {pcm(d1['mean'])} & {pcm(o1['mean'])} & {pcm(d10['mean'])} & {pcm(nm1['mean'])} & {pcm(nm10['mean'])}\\\\")
W("tab_link_ranges.tex", rows + ["\\bottomrule"]); W("tab_link.tex", rows_m + ["\\bottomrule"])
w1 = A3["main|base|1000|mm|50"]["world"]
M("LinkCalls", num(w1["calls_total"]["mean"])); M("LinkTools", "50"); M("LinkDays", "30"); M("LinkSeeds", str(len(X3["seeds"]) if isinstance(X3["seeds"], list) else X3["seeds"]))
P_ = lambda x: f"{100*x:.0f}\\,\\%" if x >= 0.095 or x == 0 else f"{100*x:.1f}\\,\\%"
dmm = g3(1000, "mm", "d_full", "profile_recovery"); M("LinkMMReid", P_(dmm["mean"])); M("LinkMMReidLo", P_(dmm["min"])); M("LinkMMReidHi", P_(dmm["max"]))
M("LinkMMMinReid", P_(g3(1000, "mm_min", "d_full", "profile_recovery")["mean"]))
M("LinkMMUpper", P_(g3(1000, "mm", "e_oracle", "profile_recovery")["mean"]))
M("LinkDayReid", P_(g3(1000, "pertool_day", "d_full", "profile_recovery")["mean"])); M("LinkPertoolReid", P_(g3(1000, "pertool", "d_full", "profile_recovery")["mean"]))
M("LinkPtejReid", P_(g3(1000, "ptej", "d_full", "profile_recovery")["mean"])); M("LinkPtejOracle", P_(g3(1000, "ptej", "e_oracle", "profile_recovery")["mean"]))
nmm = g3(1000, "mm", "id_cls@natural", "calls_correct")
M("NameMM", P_(nmm["mean"])); M("NameMMLo", P_(nmm["min"])); M("NameMMHi", P_(nmm["max"]))   # headline naming number + seed range
M("NameMMMin", P_(g3(1000, "mm_min", "id_cls@natural", "calls_correct")["mean"]))
M("NameMMEvery", P_(g3(1000, "mm", "id_cls@every", "calls_correct")["mean"]))
n10 = g3(10000, "mm", "id_cls@natural", "calls_correct"); M("NameMMTenK", P_(n10["mean"])); M("NameMMTenKLo", P_(n10["min"])); M("NameMMTenKHi", P_(n10["max"]))
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
# calibration (E4 v2.1 Masked-Mandates runs)
cal3 = X3["calibration"]; cm = cal3["mm"]; q3 = cm["quantiles_ms"]
M("GapMedS", f"{q3['p50']/1000:.2f}"); M("GapNinetyNineS", f"{q3['p99']/1000:.1f}"); M("GapNinetyS", f"{q3['p90']/1000:.1f}")
M("GapSource", "E4 v2.1 \\sys{} runs"); M("GapN", num(cm["n_gaps"])); M("GapRows", num(cm["rows_used"])); M("GapModels", str(len(cm["per_model"])))
dl3 = cm["deleg"]
M("DelegLatMedS", f"{dl3['deleg_ms_quantiles']['p50']/1000:.2f}"); M("IssLagMedS", f"{dl3['lag_ms_quantiles']['p50']/1000:.2f}")
M("IssLagNinetyNineS", f"{dl3['lag_ms_quantiles']['p99']/1000:.2f}"); M("IssPDeleg", P_(dl3["p_deleg"])); M("IssNDeleg", num(dl3["n"]))
# load / concurrency sweep (format mm, full coalition)
def lpts():
    pts = []
    for N in sorted(set([1000, 10000] + X3["params"]["load_N"] + X3["params"]["load_N_timing_only"])):
        for key in ([f"main|base|{N}|mm|50"] if N in (1000, 10000) else [f"load|base|{N}|mm|50", f"loadT|base|{N}|mm|50"]):
            if key in A3: pts.append(key)
    for v in X3["params"]["load_rate_tasks_per_day"]:
        key = f"load|tasks_per_day=({v[0]},{v[1]})|1000|mm|50"
        if key in A3: pts.append(key)
    return pts
LP = lpts()
rate = lambda k: A3[k]["world"]["arrival_rate_tasks_per_min"]["mean"]
att3 = lambda k, a, m: A3[k]["attackers"].get(a, {}).get(m)
full = [k for k in LP if att3(k, "id_cls@natural", "calls_correct")]
lo_k, hi_k = min(full, key=rate), max(full, key=rate)
def fr(x): return f"{x:.2f}" if x < 1 else (f"{x:.1f}" if x < 10 else num(x))
M("LoadRateMin", fr(min(rate(k) for k in LP))); M("LoadRateMax", fr(max(rate(k) for k in LP)))
M("LoadUsersMax", num(max(A3[k]["world"]["users"]["mean"] for k in LP)))
M("NameLoadLo", P_(att3(lo_k, "id_cls@natural", "calls_correct")["mean"])); M("NameLoadLoRate", fr(rate(lo_k)))
M("NameLoadHi", P_(att3(hi_k, "id_cls@natural", "calls_correct")["mean"])); M("NameLoadHiRate", fr(rate(hi_k)))
M("NameLoadHiUsers", num(A3[hi_k]["world"]["users"]["mean"]))
dk = [k for k in LP if att3(k, "d_full", "profile_recovery")]
dlo, dhi = min(dk, key=rate), max(dk, key=rate)
M("ProfLoadLo", P_(att3(dlo, "d_full", "profile_recovery")["mean"])); M("ProfLoadLoRate", fr(rate(dlo)))
M("ProfLoadHi", P_(att3(dhi, "d_full", "profile_recovery")["mean"])); M("ProfLoadHiRate", fr(rate(dhi)))
M("ProfLoadMax", P_(max(att3(k, "d_full", "profile_recovery")["max"] for k in dk)))
sk = max(LP, key=rate)   # highest arrival rate overall: timing / naming attacker (session propagation)
M("NameSessLoadHi", P_(att3(sk, "id_sess@natural", "calls_correct")["mean"])); M("NameSessLoadHiRate", fr(rate(sk)))
M("NameSessLoadHiUsers", num(A3[sk]["world"]["users"]["mean"]))
M("NameSessLoadLo", P_(att3(min(LP, key=rate), "id_sess@natural", "calls_correct")["mean"]))
# issuer in the coalition: paired per-seed increment (issuer + tools) - (tools only), in percentage points
def inc(key, a):
    x, y = A3[key]["attackers"][a]["calls_correct"]["draws"], A3[key]["attackers"]["I:" + a]["calls_correct"]["draws"]
    d = [v - u for u, v in zip(x, y)]
    return sum(d) / len(d), min(d), max(d)
pp = lambda x: f"{100*x:.1f}"
for key, nm in [("main|base|1000|mm|50", ""), ("main|base|10000|mm|50", "TenK"), ("sens|p_deleg=1.0|1000|mm|50", "PdOne"),
                ("load|p_deleg=1.0|10000|mm|50", "PdOneTenK")]:
    if key not in A3: continue
    m_, lo_, hi_ = inc(key, "id_cls@natural"); M(f"IssNameInc{nm}", pp(m_)); M(f"IssNameIncLo{nm}", pp(lo_)); M(f"IssNameIncHi{nm}", pp(hi_))
    m_, lo_, hi_ = inc(key, "id_sess@natural"); M(f"IssSessInc{nm}", pp(m_))
    tr = A3[key]["tracker"]
    M(f"IssExactA{nm}", P_(tr["A"]["tasks_exact"]["mean"])); M(f"IssExactI{nm}", P_(tr["I"]["tasks_exact"]["mean"]))
    M(f"IssNameWith{nm}", P_(A3[key]["attackers"]["I:id_cls@natural"]["calls_correct"]["mean"]))
mxk = max((k for k in LP if "I:id_sess@natural" in A3[k]["attackers"]), key=rate)
m_, lo_, hi_ = inc(mxk, "id_sess@natural"); M("IssSessIncLoadHi", pp(m_)); M("IssSessIncLoadHiRate", fr(rate(mxk)))
_sh.copy(os.path.join(R, "fig_e3_load.pdf"), os.path.join(O, "fig_e3_load.pdf"))
# mitigation: decoupled identity call (sim/e3v22.py docstring item E; aggregate keys dec|decouple=...)
def dg(v, N, att, met, fmt="mm"): return A3[f"dec|decouple={v}|{N}|{fmt}|50"]["attackers"][att][met]
for v, nm in [("hour", "Hour"), ("day", "Day")]:
    s_ = dg(v, 1000, "id_cls@natural", "calls_correct")
    M(f"NameDec{nm}", P_(s_["mean"])); M(f"NameDec{nm}Lo", P_(s_["min"])); M(f"NameDec{nm}Hi", P_(s_["max"]))
    s_ = dg(v, 10000, "id_cls@natural", "calls_correct"); M(f"NameDec{nm}TenK", P_(s_["mean"]))
    M(f"NameDec{nm}TenKLo", P_(s_["min"])); M(f"NameDec{nm}TenKHi", P_(s_["max"]))
    s_ = dg(f"{v}_every", 1000, "id_cls@every", "calls_correct"); M(f"NameDec{nm}Every", P_(s_["mean"]))
    M(f"NameDec{nm}EveryLo", P_(s_["min"])); M(f"NameDec{nm}EveryHi", P_(s_["max"]))
    M(f"NameDec{nm}Sess", P_(dg(v, 1000, "id_sess@natural", "calls_correct")["mean"]))
    M(f"NameDec{nm}Min", P_(dg(v, 1000, "id_cls@natural", "calls_correct", "mm_min")["mean"]))
    s_ = dg(v, 1000, "d_full", "profile_recovery"); M(f"ProfDec{nm}", P_(s_["mean"]))
    M(f"ProfDec{nm}Lo", P_(s_["min"])); M(f"ProfDec{nm}Hi", P_(s_["max"]))
# decoupling, reviewer follow-up (docstring item F; keys decA|decouple=...): adapted attacker X and value-free variant
def da(v, N, att): return A3[f"decA|decouple={v}|{N}|mm|50"]["attackers"][att]["calls_correct"]
for N, sfx in [(1000, ""), (10000, "TenK")]:
    for v, nm in [("hour", "Hour"), ("day", "Day")]:
        for tag, setting, att in [("Adapt", v, "X:id_cls@natural"), ("Free", f"{v}_free", "X:id_cls@natural"),   # Free: adapted attacker
                                  ("FreeTools", f"{v}_free", "id_cls@natural")]:
            s_ = da(setting, N, att)
            M(f"NameDec{nm}{tag}{sfx}", P_(s_["mean"])); M(f"NameDec{nm}{tag}{sfx}Lo", P_(s_["min"])); M(f"NameDec{nm}{tag}{sfx}Hi", P_(s_["max"]))
        M(f"NameDec{nm}AdaptSess{sfx}", P_(da(v, N, "X:id_sess@natural")["mean"]))
        M(f"NameDec{nm}FreeSess{sfx}", P_(da(f"{v}_free", N, "X:id_sess@natural")["mean"]))
        tx = A3[f"decA|decouple={v}|{N}|mm|50"]["tracker"]["X"]
        M(f"DecJoinPrec{nm}{sfx}", P_(tx["decoupled_join_precision_most_recent"]["mean"]))
        M(f"DecJoinCand{nm}{sfx}", f"{tx['decoupled_candidates_mean']['mean']:.1f}")
