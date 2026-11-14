# E2 v2.1 part of gen_tex_v21.py (exec'd there)
E2 = J("e2v21.json")
assert str(E2["rayon_num_threads"]) == "1" and len(E2["seeds"]) == 3
res = {(r["mode"], r["transport"]): r for r in E2["results"]}
ctl = {(c["mode"], c["transport"]): c["outcome"] for c in E2["controls"]}
dli = {x["mode"]: x for x in E2["delegation_issuance"]}
modes = ["none", "jwt_chain", "biscuit", "macaroon", "batch_tokens", "blind_tokens", "mm", "mm_esc"]
lab = {"none": "None", "jwt_chain": "JWT chain + PoP", "biscuit": "Biscuit", "macaroon": "Macaroon", "batch_tokens": "Batch one-time tokens",
       "blind_tokens": "Blind RSA tokens + PoP", "mm": r"\sys{}", "mm_esc": r"\sys{} + escrow"}
issuer_learns = {"none": "--", "jwt_chain": "root; tools see chain", "biscuit": "root; tools see chain", "macaroon": "root; tools hold key",
                 "batch_tokens": "chain, token ids", "blind_tokens": "chain, token count", "mm": "delegation times", "mm_esc": "delegation times"}
linkT = {"none": "--", "jwt_chain": "yes", "biscuit": "yes", "macaroon": "yes", "batch_tokens": "no", "blind_tokens": "no", "mm": "no", "mm_esc": "no$^\\dagger$"}
def mv(m, t, k): return res[(m, t)][k]["median"]["median"]
def rng_(m, t, k): x = res[(m, t)][k]["median"]; return x["min"], x["max"]
# every mode except none rejects replays, in every transport
for (m, t), o in ctl.items():
    if m != "none": assert o["replay_same_tool"] == "rejected" and o["replay_other_tool"] == "rejected", (m, t)
    if m.startswith("mm"): assert all(v == "rejected" for v in o.values()), (m, t, o)
def bind(m):
    o = ctl[(m, "http")]; return "no" if o.get("tampered_call_fresh_auth") == "ACCEPTED" else "yes"
def revk(m):
    o = ctl[(m, "http")]; return "--" if m == "none" else ("no" if o.get("after_revocation_of_agent1") == "ACCEPTED" else "yes")
rows = []
for m in modes:
    if m in ("batch_tokens", "blind_tokens"): dl = f"{dli[m]['per_token_issuance_ms']['median'] if isinstance(dli[m]['per_token_issuance_ms'], dict) else dli[m]['per_token_issuance_ms']:.2f}/tok"
    elif m == "none": dl = "--"
    else:
        v = dli[m]["two_hop_ms_all_chains"]["median"]; dl = f"{v/1000:.2f} s" if v >= 1000 else f"{v:.2f}"
    st = f"{mv(m, 'http_stateless', 'total_ms'):.1f}" if (m, "http_stateless") in res else "--"
    lo, hi = rng_(m, "http", "total_ms")
    rows.append(f"{lab[m]} & {mv(m,'http','prep_ms'):.1f} & {mv(m,'http','verify_ms'):.1f} & {mv(m,'http','total_ms'):.1f} & {mv(m,'http_delay10','total_ms'):.1f} & {st} & {num(mv(m,'http','auth_bytes'))} & {dl} & {bind(m)} & {revk(m)} & {linkT[m]} & {issuer_learns[m]}\\\\")
W("tab_e2e.tex", rows + ["\\bottomrule"])
M("ECalls", str(E2["n_calls"])); M("EWarm", str(E2["warmup"])); M("EMcpSdk", E2["mcp_sdk"]); M("EPy", E2["python"]); M("ERuns", "3")
M("EtoeNoneHttp", f1(mv("none", "http", "total_ms"))); M("EChalHttp", f1(mv("mm", "http", "challenge_rtt_ms")))
M("EBaseMaxHttp", f1(max(mv(m, "http", "total_ms") for m in modes[1:6])))
M("EMMPrep", f0(mv("mm", "http", "prep_ms"))); M("EMMVer", f0(mv("mm", "http", "verify_ms"))); M("EMMTotalHttp", f0(mv("mm", "http", "total_ms")))
lo, hi = rng_("mm", "http", "total_ms"); M("EMMTotalLo", f0(lo)); M("EMMTotalHi", f0(hi))
M("EMMTotalDelay", f0(mv("mm", "http_delay10", "total_ms"))); M("EMMBytes", num(mv("mm", "http", "auth_bytes")))
M("EMMDelegS", f2(dli["mm"]["two_hop_ms_all_chains"]["median"] / 1000))
so = {x["mode"]: x for x in E2["stateless_overhead"]}; M("EStatelessAdd", f0(so["mm"]["added_total_ms"]["median"])); M("EStatelessAddJwt", f0(so["jwt_chain"]["added_total_ms"]["median"]))
