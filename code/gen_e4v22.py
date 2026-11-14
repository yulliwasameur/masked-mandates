# E4 v2.2 additions (exec'd by gen_tex_v21.py after gen_e4v21): dishonest wallet and grace/retry rules, from
# results/e4v22_key.json (written by the e4v22 harness; scripted policy, i.e. no LLM, unless an LLM key is present).
K4 = J("e4v22_key.json")
def k4(key): return K4[key]
dw = [m for m in ("mm_dw", "mm_dw_cv")]
sent = sum(k4(f"dw.total.{m}.{t}.sent") for m in dw for t in "ce")
acc = sum(k4(f"dw.total.{m}.{t}.accepted") for m in dw for t in "ce")
rej_uni = sum(k4(f"dw.total.{m}.{t}.tool_rejected_uniform") for m in dw for t in "ce")
assert acc == 0 and rej_uni == sent
M("EFourDwSent", str(sent)); M("EFourDwRevSent", str(sum(k4(f"dw.total.{m}.c.sent") for m in dw))); M("EFourDwQuotaSent", str(sum(k4(f"dw.total.{m}.e.sent") for m in dw)))
G = "grace.oracle."
assert all(k4(G + c + ".revoked_or_beyond_quota_accepted") == 0 for c in ("v22_W0_every2s", "v22_W0_retry_every2s", "v22_W0_D1000_every2s", "v22_W2_every2s", "v22_W2_every60s", "v22_W0_D1000_every60s"))
M("EFourOrWzeroRej", f"{100 * k4(G + 'v22_W0_every2s.honest_rejected') / k4(G + 'v22_W0_every2s.honest_calls'):.0f}\\,\\%")
M("EFourRetryRej", str(k4(G + "v22_W0_retry_every2s.honest_rejected"))); M("EFourRetryN", str(k4(G + "v22_W0_retry_every2s.retries")))
M("EFourRetryOk", str(k4(G + "v22_W0_retry_every2s.retries_ok"))); M("EFourRetryCalls", str(k4(G + "v22_W0_retry_every2s.honest_calls")))
M("EFourRetryDelayMs", f0(1000 * k4(G + "v22_W0_retry_every2s.delay_s_median")))
M("EFourDeltaRej", str(k4(G + "v22_W0_D1000_every2s.honest_rejected")))
M("EFourDeltaDelayS", f"{k4(G + 'v22_W0_D1000_every2s.delay_s_median'):.1f}"); M("EFourDeltaDelaySparseS", f"{k4(G + 'v22_W0_D1000_every60s.delay_s_median'):.1f}")
M("EFourWtwoDelayS", f"{k4(G + 'v22_W2_every2s.delay_s_median'):.1f}"); M("EFourWtwoDelaySparseS", f0(k4(G + "v22_W2_every60s.delay_s_median")))
# LLM confirmation (five models for the dishonest wallet; Qwen2.5-72B and gpt-oss-20b for retry / time window)
dsent = sum(k4(f"dw.llm.total.{m}.{t}.sent") for m in dw for t in "ce")
assert sum(k4(f"dw.llm.total.{m}.{t}.accepted") for m in dw for t in "ce") == 0
assert sum(k4(f"dw.llm.total.{m}.{t}.tool_rejected_uniform") for m in dw for t in "ce") == dsent
M("EFourDwLlmSent", str(dsent)); M("EFourDwLlmHonest", num(sum(k4(f"dw.llm.total.{m}.{t}.honest_calls") for m in dw for t in "ce")))
assert sum(k4(f"dw.llm.total.{m}.{t}.honest_rejected") for m in dw for t in "ce") == 0
GL = [k for k in K4 if k.startswith("grace.llm.") and k.endswith(".honest_rejected") and ("retry_every2s" in k or "D1000" in k)]
assert all(K4[k] == 0 for k in GL) and len(GL) >= 4
sr = [100 * K4[k.replace(".honest_rejected", ".success")] / 120 for k in GL if "every2s" in k]
M("EFourLlmFixSuccMin", f"{min(sr):.0f}"); M("EFourLlmFixSuccMax", f"{max(sr):.0f}")
