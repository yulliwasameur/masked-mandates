# E4 v2 part of gen_tex_v2.py (exec'd there)
E4 = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(R, "e4v2", "e4v2_*.json")))]
assert len(E4) == 5, len(E4)
nice = {"qwen2.5-7b-instruct": "Qwen2.5-7B", "qwen2.5-72b-instruct-awq": "Qwen2.5-72B", "gpt-oss-20b": "gpt-oss-20b",
        "hermes-3-llama-3.1-8b": "Hermes-3", "granite-3.3-8b-instruct": "Granite-3.3"}
order = ["qwen2.5-7b-instruct", "qwen2.5-72b-instruct-awq", "gpt-oss-20b", "hermes-3-llama-3.1-8b", "granite-3.3-8b-instruct"]
E4.sort(key=lambda d: order.index(d["model"]))
def rate(d, cfg, mode, tpls):
    bt = d["summary"]["by_template"]; k = sum(bt[f"{cfg}|{mode}|{t}"]["k"] for t in tpls); n = sum(bt[f"{cfg}|{mode}|{t}"]["n"] for t in tpls); return k, n
def pc0(k, n): return f"{100*k/n:.0f}"
rows = []; shares = []; jshares = []; honest = {m: 0 for m in ["jwt", "mm", "mm_esc"]}; wrong = 0; rev = [0, 0]; minp = 1.0
for d in E4:
    s = d["summary"]
    assert str(d["threads"]["RAYON_NUM_THREADS"]) == "1"
    for m in ["jwt", "mm", "mm_esc"]:
        sf = s["safety"][m]; honest[m] += sf["honest_calls"]; wrong += sf["honest_calls_wrongly_rejected"]
        rev[0] += sf["revoked_calls_rejected"]; rev[1] += sf["revoked_calls_attempted"]
    for k, v in s["paired"].items():
        if k.startswith("t07|honest_abd"): minp = min(minp, v["p_exact_mcnemar"])
    hn, hm = rate(d, "t07", "none", "abd"), rate(d, "t07", "mm", "abd"); hj = rate(d, "t07", "jwt", "abd")
    cn, cm = rate(d, "t07", "none", "c"), rate(d, "t07", "mm", "c")
    sh = s["timing"]["t0|mm"]["auth_share"]["ratio_of_sums"]; js = s["timing"]["t0|jwt"]["auth_share"]["ratio_of_sums"]
    pcs = s["timing"]["t0|mm"]["per_call_auth_share"]["ratio_of_sums"]
    shares.append(sh); jshares.append(js)
    llm = s["timing"]["t0|none"]["llm_ms"]["median"] / 1000
    rows.append(f"{nice[d['model']]} & {pc0(*hn)} / {pc0(*hj)} / {pc0(*hm)} & {pc0(*cn)} / {pc0(*cm)} & {f1(llm)} & {100*pcs:.0f} & {100*sh:.0f} & {100*js:.1f}\\\\")
W("tab_e4.tex", rows + ["\\bottomrule"])
assert wrong == 0
M("EFourModels", str(len(E4))); M("EFourTasks", str(E4[0]["n_tasks"])); M("EFourRuns", num(sum(len(d["rows"]) for d in E4)))
M("EFourShareMin", f"{100*min(shares):.0f}\\,\\%"); M("EFourShareMax", f"{100*max(shares):.0f}\\,\\%")
M("EFourShareMed", f"{100*med(shares):.0f}\\,\\%")
M("EFourJwtShareMax", f"{100*max(jshares):.1f}\\,\\%")
M("EFourHonestCalls", num(honest["mm"])); M("EFourRevRej", num(rev[0])); M("EFourRevAtt", num(rev[1]))
M("EFourMinP", f"{minp:.2f}")
pc_ = [c for d in E4 for r in d["rows"] if r["mode"] == "mm" for c in r["calls"] if c.get("prep_ms", 0) > 1]
M("EFourPresMs", f0(med([c["prep_ms"] for c in pc_]))); M("EFourVerMs", f0(med([c["verify_ms"] for c in pc_ if c.get("verify_ms")])))
lat = E4[0]["latency_model"]; M("EFourLatMed", f0(lat["median_ms"]))
M("EFourCpu", [l.split(":", 1)[1].strip() for l in E4[0]["lscpu"].splitlines() if l.startswith("Model name")][0].replace("(R)", ""))
b16 = [json.load(open(p)) for p in glob.glob(os.path.join(R, "e4v2", "bench", "bench-16threads-*.json"))]
M("EFourMtPres", f0(med([b["results"]["mm_root"]["prep_ms_median"] for b in b16]))); M("EFourMtVer", f0(med([b["results"]["mm_root"]["verify_ms_median"] for b in b16])))
sf = [100 * rate(d, "t07", "mm", "c")[0] / rate(d, "t07", "mm", "c")[1] for d in E4]
M("EFourSafeMin", f"{min(sf):.0f}"); M("EFourSafeMax", f"{max(sf):.0f}")
