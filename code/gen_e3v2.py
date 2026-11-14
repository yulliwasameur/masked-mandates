# E3 v2 part of gen_tex_v2.py (exec'd there)
X = J("e3v2.json")
W3 = {w["world"]["users"]: w for w in X["main"]}
assert sorted(W3) == [100, 1000, 10000]
def pc(x): return f"{100*x:.0f}\\,\\%" if x >= 0.01 or x == 0 else f"{100*x:.1f}\\,\\%"
fl = [("clear", "Clear identifiers"), ("pertool", "Per-tool pseudonym"), ("pertool_day", "Per-tool, per-day pseudonym"),
      ("mm", r"\sys{}"), ("pertool_min", "Per-tool, minimised args"), ("pertool_day_min", "Per-tool per-day, minimised"), ("mm_min", r"\sys{}, minimised args")]
rows = []
for k, n in fl:
    a = W3[1000]["formats"][k]
    rows.append(f"{n} & {pc(a['a_id']['reid_rate'])} & {pc(a['d_full']['reid_rate'])} & {pc(a['e_auxmap']['reid_rate']) if 'e_auxmap' in a else '--'} & {pc(W3[10000]['formats'][k]['d_full']['reid_rate'])}\\\\")
W("tab_link.tex", rows + ["\\bottomrule"])
w1, w10 = W3[1000], W3[10000]
M("LinkCalls", num(w1["world"]["calls"])); M("LinkTools", "50"); M("LinkDays", "30")
M("LinkMMReid", pc(w1["formats"]["mm"]["d_full"]["reid_rate"])); M("LinkMMMinReid", pc(w1["formats"]["mm_min"]["d_full"]["reid_rate"]))
M("LinkMMUpper", pc(w1["formats"]["mm"]["e_auxmap"]["reid_rate"])); M("LinkDayReid", pc(w1["formats"]["pertool_day"]["d_full"]["reid_rate"]))
M("LinkPertoolReid", pc(w1["formats"]["pertool"]["d_full"]["reid_rate"])); M("LinkMMMinUpper", pc(w1["formats"]["mm_min"]["e_auxmap"]["reid_rate"]))
rs = X["replicates"]["summary"]["mm"]; M("LinkMMReidLo", pc(rs["reid_min"])); M("LinkMMReidHi", pc(rs["reid_max"]))
b = w1["formats"]["mm"]["b_time2"]; M("TimSessRecTwo", pc(b["session_recall"])); M("TimPrecTwo", pc(b["precision"])); M("TimFPTwo", num(b["FP"]))
b = w10["formats"]["mm"]["b_time2"]; M("TimPrecTwoTenK", pc(b["precision"])); M("TimSessRecTwoTenK", pc(b["session_recall"]))
M("GapMedS", f"{X['calibration']['quantiles_s']['p50']:.2f}")
sens = {(s["factor"], str(s["value"])): s["result"]["formats"] for s in X["sensitivity"]}
jit = [s for s in X["sensitivity"] if s["factor"] == "timing_jitter_s"]
if jit: M("LinkMMJitReid", pc(jit[-1]["result"]["formats"]["mm"]["d_full"]["reid_rate"])); M("LinkJitS", str(jit[-1]["value"]))
mx = max(s["result"]["formats"]["mm_min"]["d_full"]["reid_rate"] for s in X["sensitivity"])
M("LinkMMMinSensMax", pc(mx))
