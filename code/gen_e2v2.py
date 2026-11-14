# E2 v2 part of gen_tex_v2.py (exec'd there; uses J, M, W, num, f0, f1, f2, med)
E2 = J("e2v2.json")
assert str(E2["rayon_num_threads"]) == "1"
runs = {(r["mode"], r["transport"]): r for r in E2["runs"]}
modes = ["none", "jwt_chain", "biscuit", "macaroon", "batch_tokens", "blind_tokens", "mm", "mm_esc"]
lab = {"none": "None", "jwt_chain": "JWT chain + PoP", "biscuit": "Biscuit", "macaroon": "Macaroon", "batch_tokens": "Batch one-time tokens",
       "blind_tokens": "Blind RSA tokens", "mm": r"\sys{}", "mm_esc": r"\sys{} + escrow"}
# who can link calls: tools / issuer
link = {"none": "--", "jwt_chain": "T, I", "biscuit": "T, I", "macaroon": "T, I", "batch_tokens": "I", "blind_tokens": "none", "mm": "none", "mm_esc": "none$^\\dagger$"}
for m in modes:
    for t in E2["transports"]:
        r = runs[(m, t)]
        if m != "none":
            c = r["controls"]
            assert not c["replay_same_tool"]["accepted"] and not c["replay_other_tool"]["accepted"], (m, t)
        if m.startswith("mm"):
            assert all(not v["accepted"] for v in r["controls"].values()), (m, t, r["controls"])
def s(m, t, k): return runs[(m, t)]["summary"][k]["median"]
def deleg(m):
    d = runs[(m, "http")]["delegation_issuance"]; return d.get("two_hop_total_ms", 0.0)
def rev_ok(m):
    c = runs[(m, "http")]["controls"].get("after_revocation_of_agent1")
    if m == "none": return "--"
    return "--" if c is None else ("no" if c["accepted"] else "yes")
rows = []
for m in modes:
    dl = deleg(m)
    dls = "--" if m == "none" else (f"{dl/1000:.2f} s" if dl >= 1000 else f"{dl:.2f}")
    if m == "batch_tokens": dls = f"{runs[(m,'http')]['delegation_issuance'].get('per_token_issuance_ms', 0):.2f}/tok"
    if m == "blind_tokens": dls = f"{runs[(m,'http')]['delegation_issuance'].get('per_token_issuance_ms', 0):.1f}/tok"
    rows.append(f"{lab[m]} & {f1(s(m,'http','prep_ms'))} & {f1(s(m,'http','verify_ms'))} & {f1(s(m,'http','total_ms'))} & {f1(s(m,'http_delay10','total_ms'))} & {num(s(m,'http','auth_bytes'))} & {dls} & {rev_ok(m)} & {link[m]}\\\\")
W("tab_e2e.tex", rows + ["\\bottomrule"])
M("ECalls", str(E2["n_calls"])); M("EWarm", str(E2["warmup"])); M("EMcpSdk", E2["mcp_sdk"]); M("EPy", E2["python"])
M("EtoeNoneHttp", f1(s("none", "http", "total_ms"))); M("EtoeNoneDelay", f1(s("none", "http_delay10", "total_ms")))
M("EChalHttp", f1(s("mm", "http", "challenge_rtt_ms")))
M("EBaseMaxHttp", f1(max(s(m, "http", "total_ms") for m in modes[1:6])))
M("EMMPrep", f0(s("mm", "http", "prep_ms"))); M("EMMVer", f0(s("mm", "http", "verify_ms"))); M("EMMTotalHttp", f0(s("mm", "http", "total_ms")))
M("EMMTotalDelay", f0(s("mm", "http_delay10", "total_ms"))); M("EMMBytes", num(s("mm", "http", "auth_bytes")))
M("EMMDelegS", f2(deleg("mm") / 1000))
M("ELoadStart", E2["uptime_start"].split("averages:")[1].split()[0])
M("EBatchTokMs", f2(runs[("batch_tokens", "http")]["delegation_issuance"]["per_token_issuance_ms"]))
M("EBlindTokMs", f1(runs[("blind_tokens", "http")]["delegation_issuance"]["per_token_issuance_ms"]))
