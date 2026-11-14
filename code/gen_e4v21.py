# E4 v2.1 part of gen_tex_v21.py (exec'd there): LLM agents over MCP, from results/e4v21/.
# Statistics reuse the functions of e4v21/e4v21.py (paired cluster bootstrap, exact McNemar, Holm, slowdown ratios),
# with the same bootstrap seeds as `e4v21.py analyse`, so the numbers match results/e4v21_summary.md.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("e4v21", os.path.join(os.path.dirname(os.path.abspath(R)) if os.path.isabs(R) else ".", "e4v21", "e4v21.py"))
E4 = _ilu.module_from_spec(_spec); _spec.loader.exec_module(E4)
R4 = os.path.join(R, "e4v21")
NAMES4 = [("qwen2.5-7b-instruct", "Qwen2.5-7B"), ("hermes-3-llama-3.1-8b", "Hermes-3-8B"), ("granite-3.3-8b-instruct", "Granite-3.3-8B"),
          ("gpt-oss-20b", "gpt-oss-20b"), ("qwen2.5-72b-instruct-awq", "Qwen2.5-72B")]
D4 = {m: json.load(open(os.path.join(R4, f"e4v21_{m}.json"))) for m, _ in NAMES4}
ALLCFG = ["t0", "t0_rep", "t0_nolat"] + E4.GROUPS["t07"]; LATCFG = ["t0", "t0_rep"] + E4.GROUPS["t07"]
for d in D4.values():
    assert d["experiment"] == "E4 v2.1" and not any(r["error"] for r in d["rows"])
    d["summary"] = E4.summarise(d["rows"])
pc4 = lambda x: f"{x:.0f}" if abs(x) >= 9.95 or x == 0 else f"{x:.1f}"
def rate4(rows, mode, tpls, cfgs=ALLCFG):
    rs = [r for r in rows if r["mode"] == mode and r["template"] in tpls and r["cfg"] in cfgs]
    return 100 * sum(r["success"] for r in rs) / len(rs)

# ---- scale
allrows = [r for d in D4.values() for r in d["rows"]]
M("EFourModels", str(len(D4))); M("EFourTasks", str(D4[NAMES4[0][0]]["n_tasks"])); M("EFourRuns", num(len(allrows)))
M("EFourCalls", num(sum(r["n_calls"] for r in allrows))); M("EFourCfgs", str(len(E4.CFGS)))
M("EFourLatMed", f0(D4[NAMES4[0][0]]["latency_model"]["median_ms"]))
M("EFourVllm", D4[NAMES4[0][0]]["model_config"]["vllm"]); M("EFourSdk", D4[NAMES4[0][0]]["mcp_sdk"])
_cpu = [l.split(":", 1)[1].strip() for l in D4[NAMES4[0][0]]["lscpu"].splitlines() if l.startswith("Model name")][0]
M("EFourCpu", _cpu.replace("(R)", "").replace("Intel ", "Intel~"))
assert len({d["provenance"]["mmpy_so_sha256"] for d in D4.values()}) == 1

# ---- per-call costs on one core (bench outside the agent loop) and with 16 threads
b1 = json.load(open(glob.glob(os.path.join(R4, "bench-1thread-*.json"))[0])); b16 = json.load(open(glob.glob(os.path.join(R4, "bench-16threads-*.json"))[0]))
assert b1["rayon"] in (1, "1") and str(b16["rayon"]) == "16"
M("EFourPresMs", f0(b1["results"]["mm_root"]["prep_ms_median"])); M("EFourVerMs", f0(b1["results"]["mm_root"]["verify_ms_median"]))
M("EFourMtPres", f0(b16["results"]["mm_root"]["prep_ms_median"])); M("EFourMtVer", f0(b16["results"]["mm_root"]["verify_ms_median"]))
M("EFourDelegS", f2(b1["results"]["mm_delegate"]["wall_ms_median"] / 1000))

# ---- canonicalisation, false rejections, revocation, quota (all configurations)
S4 = {m: d["summary"]["safety"] for m, d in D4.items()}
tot = lambda key, modes: sum(S4[m][x][key] for m in S4 for x in modes)
M("EFourCanonCalls", num(tot("canon_checked", E4.MODES))); assert tot("canon_mismatch", E4.MODES) == 0
cp4 = json.load(open(glob.glob(os.path.join(R4, "canonprobe-*.json"))[0]))
assert all(v["canon_mismatch"] == 0 for v in cp4["summary"].values()); M("EFourProbeCases", str(len(cp4["rows"])))
assert tot("honest_calls_wrongly_rejected", ["jwt", "mm", "mm_esc"]) == 0
M("EFourHonestCalls", num(tot("honest_calls", ["mm", "mm_esc"])))
assert tot("revoked_calls_accepted", ["jwt", "mm", "mm_esc"]) == 0 and tot("beyond_quota_accepted", ["jwt", "mm", "mm_esc"]) == 0
assert tot("revoked_calls_accepted", ["none"]) == tot("revoked_calls_attempted", ["none"])
assert tot("beyond_quota_accepted", ["none"]) == tot("beyond_quota_attempted", ["none"])
M("EFourRevAtt", num(tot("revoked_calls_attempted", ["jwt", "mm", "mm_esc"]))); M("EFourRevNone", num(tot("revoked_calls_attempted", ["none"])))
M("EFourQuotaAtt", num(tot("beyond_quota_attempted", ["jwt", "mm", "mm_esc"]))); M("EFourQuotaNone", num(tot("beyond_quota_attempted", ["none"])))
safe = {m: rate4(D4[m]["rows"], "mm", "c") for m in D4}; quota = {m: rate4(D4[m]["rows"], "mm", "e") for m in D4}
M("EFourSafeMin", pc4(min(safe.values()))); M("EFourSafeMax", pc4(max(safe.values())))
M("EFourQuotaMin", pc4(min(quota.values()))); M("EFourQuotaMax", pc4(max(quota.values())))
M("EFourNoneSafeMax", pc4(max(rate4(D4[m]["rows"], "none", "c") for m in D4)))

# ---- replication control (t0 vs t0_rep, honest templates)
rep = [D4[m]["summary"]["replication"][f"t0_vs_t0_rep|{x}"]["abd"] for m in D4 for x in E4.MODES]
M("EFourRepMax", str(max(z["success_discordant"] for z in rep))); M("EFourRepPairs", str(rep[0]["pairs"]))
M("EFourRepDetModel", "Qwen2.5-72B"); assert all(D4["qwen2.5-72b-instruct-awq"]["summary"]["replication"][f"t0_vs_t0_rep|{x}"]["abd"]["success_discordant"] == 0 for x in E4.MODES)

# ---- honest templates: paired differences mode - none, clustered by task.
# Configurations: t07 (3 seeds) and a pool of the four distinct configurations (t0, t0_nolat, t07 x3), WITHOUT the
# identical-settings replication t0_rep. Test: two-sided sign-flip permutation test on per-task sums of paired
# differences (valid for units clustered within tasks); CIs: percentile cluster bootstrap (E4.cluster_boot).
# Holm family: the honest-template tests only (5 models x 3 modes x 2 configuration sets = 30).
import random as _rnd
POOLCFG = ["t0", "t0_nolat"] + E4.GROUPS["t07"]
def perm_p(units, B=20000, seed=7):
    d = [sum(b - a for a, b in units[t]) for t in sorted(units)]
    obs = abs(sum(d)); rng = _rnd.Random(seed); cnt = 0
    if obs == 0: return 1.0
    for _ in range(B):
        if abs(sum(x if rng.random() < .5 else -x for x in d)) >= obs: cnt += 1
    return (cnt + 1) / (B + 1)
tests4 = []
for m, _ in NAMES4:
    d = D4[m]
    for cfgname, cfgs in [("t07", E4.GROUPS["t07"]), ("pool", POOLCFG)]:
        for mode in ["jwt", "mm", "mm_esc"]:
            u = E4.paired_units(d["rows"], "none", mode, cfgs, E4.HONEST)
            st_ = E4.cluster_boot(u, B=10000, seed=E4.iseed(d["model"], "honest", cfgname, mode) % (1 << 31))
            st_["p"] = perm_p(u, seed=E4.iseed(d["model"], cfgname, mode) % (1 << 31))
            tests4.append((m, cfgname, mode, st_))
for t, p in zip(tests4, E4.holm([t[3]["p"] for t in tests4])): t[3]["p_holm"] = p
eqv = lambda s: -5 <= s["ci90"][0] and s["ci90"][1] <= 5
M("EFourNTests", str(len(tests4))); M("EFourMinP", f"{min(t[3]['p'] for t in tests4):.2f}")
M("EFourMinHolm", f"{min(t[3]['p_holm'] for t in tests4):.2f}")
M("EFourEqTsev", str(sum(eqv(t[3]) for t in tests4 if t[1] == "t07"))); M("EFourEqAll", str(sum(eqv(t[3]) for t in tests4 if t[1] == "pool")))
M("EFourEqPairs", str(sum(1 for t in tests4 if t[1] == "pool")))
mm_t07 = [t[3] for t in tests4 if t[1] == "t07" and t[2] == "mm"]; mm_pool = [t[3] for t in tests4 if t[1] == "pool" and t[2] == "mm"]
M("EFourMMEqTsev", str(sum(eqv(s) for s in mm_t07))); M("EFourMMEq", str(sum(eqv(s) for s in mm_pool)))
M("EFourMMMaxDiff", f"{max(abs(s['diff_pp']) for s in mm_pool):.1f}"); M("EFourMMMaxDiffTsev", f"{max(abs(s['diff_pp']) for s in mm_t07):.1f}")
M("EFourUnitsAll", str(mm_pool[0]["units"])); M("EFourUnitsTsev", str(mm_t07[0]["units"]))
M("EFourMarginPP", "5"); M("EFourRepPP", f"{100 * int(macros['EFourRepMax']) / int(macros['EFourRepPairs']):.0f}")
neq = [f"{dict(NAMES4)[t[0]]} {t[2].replace('mm_esc', 'MM+escrow').replace('mm', 'MM').replace('jwt', 'JWT')}" for t in tests4 if t[1] == "t07" and not eqv(t[3])]
M("EFourNotEqTsev", ", ".join(neq) if neq else "none")
# ---- slowdown and authorisation share
slow = {m: {x: E4.ratio_stats(D4[m]["rows"], x, LATCFG, E4.HONEST) for x in ["jwt", "mm", "mm_esc"]} for m in D4}
M("EFourSlowMin", f2(min(slow[m]["mm"]["median"] for m in D4))); M("EFourSlowMax", f2(max(slow[m]["mm"]["median"] for m in D4)))
M("EFourJwtSlowMax", f2(max(slow[m]["jwt"]["median"] for m in D4)))
slow0 = {m: E4.ratio_stats(D4[m]["rows"], "mm", ["t0_nolat"], E4.HONEST) for m in D4}
M("EFourSlowNoLatMax", f2(max(slow0[m]["median"] for m in D4)))
nud = {m: 100 * sum(1 for r in D4[m]["rows"] if r["nudges"] > 0) / len(D4[m]["rows"]) for m in D4}
M("EFourNudgeMin", f"{min(nud.values()):.0f}"); M("EFourNudgeMax", f"{max(nud.values()):.0f}")
T4 = {m: D4[m]["summary"]["timing"] for m in D4}
sh = {m: 100 * T4[m]["t0|mm"]["auth_share"]["ratio_of_sums"] for m in D4}
M("EFourShareMin", f"{min(sh.values()):.0f}\\,\\%"); M("EFourShareMax", f"{max(sh.values()):.0f}\\,\\%")
M("EFourJwtShareMax", f"{max(100 * T4[m]['t0|jwt']['auth_share']['ratio_of_sums'] for m in D4):.1f}\\,\\%")
M("EFourDelegShareMax", f"{max(100 * T4[m]['t0|mm']['deleg_share']['ratio_of_sums'] for m in D4):.0f}\\,\\%")

rows4 = []
for m, n in NAMES4:
    d = D4[m]["rows"]
    rows4.append(f"{n} & {pc4(rate4(d, 'none', E4.HONEST))} & {pc4(rate4(d, 'jwt', E4.HONEST))} & {pc4(rate4(d, 'mm', E4.HONEST))} & "
                 f"{pc4(rate4(d, 'jwt', 'c'))} & {pc4(safe[m])} & {pc4(rate4(d, 'jwt', 'e'))} & {pc4(quota[m])} & "
                 f"{slow[m]['mm']['median']:.2f} & {sh[m]:.0f}\\\\")
W("tab_e4.tex", rows4 + ["\\bottomrule"])

# ---- shared issuer with background revocations (mode mm, t0)
def shared4(m, G):
    d = json.load(open(os.path.join(R4, f"e4v21_shared_{m}_W{G}.json"))); assert d["shared_issuer"]["grace"] == G
    rs = d["rows"]; hon_ = sum(r["honest_calls"] for r in rs); rej = sum(r["honest_rejected"] for r in rs)
    assert rej == sum(r["honest_rejected_churn"] for r in rs)
    assert sum(r["revoked_accepted"] for r in rs) == 0 and sum(r["beyond_quota_accepted"] for r in rs) == 0
    delays = []
    for lg in d["revlogs"]:
        es = [e for e in lg["events"] if e["kind"] in ("dummy", "task")]; byv = {e["ver"]: e for e in es}
        for e in es:
            nx = byv.get(e["ver"] + G)
            if nx and nx.get("t_installed"): delays.append((nx["t_installed"] - e["t_request"]) * 1e3)
    ids = {r["task"] for r in rs}
    base = [r for r in D4[m]["rows"] if r["task"] in ids and r["cfg"] == "t0" and r["mode"] == "mm"]
    return {"rej": 100 * rej / hon_, "succ": 100 * sum(r["success"] for r in rs) / len(rs), "base": 100 * sum(r["success"] for r in base) / len(base),
            "delay": med(delays), "every": d["shared_issuer"]["revoke_every_s"], "n": len(rs)}
SH4 = {(m, G): shared4(m, G) for m in ["qwen2.5-72b-instruct-awq", "gpt-oss-20b"] for G in (0, 2)}
z0 = [SH4[(m, 0)] for m in ["qwen2.5-72b-instruct-awq", "gpt-oss-20b"]]; z2 = [SH4[(m, 2)] for m in ["qwen2.5-72b-instruct-awq", "gpt-oss-20b"]]
M("EFourShEvery", f"{z0[0]['every']:g}"); M("EFourShTasks", str(z0[0]["n"]))
M("EFourShRejMin", f"{min(x['rej'] for x in z0):.0f}\\,\\%"); M("EFourShRejMax", f"{max(x['rej'] for x in z0):.0f}\\,\\%")
assert all(x["rej"] == 0 for x in z2)
M("EFourShSuccZeroMin", f"{min(x['succ'] for x in z0):.0f}"); M("EFourShSuccZeroMax", f"{max(x['succ'] for x in z0):.0f}")
M("EFourShSuccTwoMin", f"{min(x['succ'] for x in z2):.0f}"); M("EFourShSuccTwoMax", f"{max(x['succ'] for x in z2):.0f}")
M("EFourShBaseMin", f"{min(x['base'] for x in z2):.0f}"); M("EFourShBaseMax", f"{max(x['base'] for x in z2):.0f}")
M("EFourShDelayZeroMs", f0(max(x["delay"] for x in z0))); M("EFourShDelayTwoS", f"{max(x['delay'] for x in z2) / 1000:.1f}")

# ---- wallet in a separate process
ipc = json.load(open(os.path.join(R4, "e4v21_ipc_qwen2.5-7b-instruct.json")))
ov = [c["prep_ms"] - c["prep_inner_ms"] for r in ipc["rows"] for c in r["calls"] if c.get("valid") and "prep_inner_ms" in c and not c.get("refused")]
M("EFourIpcMs", f2(med(ov)))
# per-configuration honest-template success (none / MM), for the supplement (equivalence pools these)
cfg_rows = []
for m, n in NAMES4:
    d = D4[m]["rows"]; cells = []
    for cf in (["t0"], ["t0_rep"], ["t0_nolat"], E4.GROUPS["t07"]):
        cells += [pc4(rate4(d, "none", E4.HONEST, cf)), pc4(rate4(d, "mm", E4.HONEST, cf))]
    cfg_rows.append(f"{n} & " + " & ".join(cells) + "\\\\")
W("tab_e4_cfg.tex", cfg_rows + ["\\bottomrule"])
