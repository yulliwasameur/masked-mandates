# E4 v2.1 -- real LLM agents, MCP tools, authorisation modes (summary)

Generated 2026-11-13 16:27 by `e4v21.py analyse` from 5 campaign files and 4 shared-issuer files. Success rates in % with Wilson 95% CI. Configurations: t0 = temperature 0 with tool latency, t0_rep = identical replication of t0, t0_nolat = temperature 0 without tool latency, t07 = temperature 0.7, 3 seeds pooled. Templates: a = flight+hotel, b = delegated hotel booking, c = revocation (success = safe failure), d = search-heavy (11 calls), e = binding quota (success = flight paid, no call beyond the sub-agent's quota accepted, partial failure reported).

## Key results

* **Scale.** 5 models x 120 tasks (templates a-e, 24 each) x 4 modes x 6 configurations = 14,400 campaign runs (2,880 per model, every unit completed at the first attempt: 0 harness errors, 0 re-runs), 83,764 MCP tool calls, 8,179 sub-agent delegations, 2,523 revocations; plus the shared-issuer configuration (2 models x W in {0, 2} x 120 tasks = 480 runs, 2,186 dummy and 71 task revocations) and the IPC-wallet run (120 runs). 7.1 GPU-hours on Hedy (13 jobs, including 2 cancelled and 1 failed at start-up).
* **Canonicalisation from the raw arguments: 0 mismatches.** The tool canonicalised the raw JSON-RPC `params.arguments` and compared it with the client's canonical string on 83,764 calls (21,247 none, 20,901 jwt, 20,818 mm, 20,798 mm_esc): 0 mismatches; the adversarial probe (21 argument objects x 3 modes: null values, extra/nested keys, int vs float, `1e2`, `0.1+0.2`, `-0.0`, 2^53+1, 1e21, numeric strings, non-ASCII, control characters, UTF-16 key order) also gave 0 mismatches (the MCP SDK does not drop null values inside `arguments`).
* **Honest calls wrongly rejected: 0** in every mode with one issuer per task run (jwt 19,000, mm 18,903, mm_esc 18,892 honest calls).
* **Revocation (template c).** Calls by a revoked sub-agent: jwt 656/656 rejected, mm 650/650, mm_esc 648/648; none 926/926 accepted. Safe-failure rate (all 6 configurations, 144 runs per cell), none vs jwt / mm / mm_esc: Qwen-7B 0.7 vs 52.1 / 52.8 / 52.8 %; Qwen-72B 0.0 vs 99.3 / 99.3 / 99.3 %; gpt-oss 0.0 vs 100 / 100 / 100 %; Hermes-3 0.0 vs 42.4 / 45.1 / 45.1 %; Granite 0.0 vs 17.4 / 16.7 / 16.7 % (JWT column = the JWT baseline's safe-failure rate). Remaining failures are model behaviour (claims of DONE after the rejection: Granite 83-89 of 144 runs per authorised mode, Hermes 18-26, others 0-4).
* **Binding quota (template e, new).** Calls beyond the sub-agent's quota of 3 hotel searches: none 1,454/1,454 accepted; jwt 0/1,235 accepted (rejected by the per-tree counters at the tool); mm 0/1,251 and mm_esc 0/1,249 accepted (all refused by the honest wallet: no presentation can be built beyond the carved interval, so the call goes out unauthorised and is rejected). Success (flight paid, nothing beyond quota accepted, partial failure reported), none vs jwt / mm / mm_esc, all configurations: Qwen-7B 0.7 vs 75.0 / 75.0 / 75.0 %; Qwen-72B 0.0 vs 75.7 / 74.3 / 75.7 %; gpt-oss 0.7 vs 100 / 99.3 / 100 %; Hermes-3 0.0 vs 2.1 / 2.1 / 1.4 %; Granite 0.0 vs 14.6 / 16.7 / 15.3 %. Hermes-3 sub-agents mostly report the three cities they could search as DONE and the main agent claims DONE (134 of 144 runs per authorised mode): enforcement holds, honest reporting of partial failure depends on the model.
* **Replication control (t0 vs t0_rep, identical settings).** Success discordance on the honest templates a, b, d (72 pairs per model and mode): Qwen-72B 0 in every mode (72/72 identical transcripts); Qwen-7B 1-2, gpt-oss 1-7, Hermes-3 1-2, Granite 2-3 per mode (identical transcripts 25-62 of 72). Over all 120 tasks: 0-7 discordant units per model and mode. Mode-vs-none discordances on the honest templates are of the same size (tables below).
* **Equivalence on the honest templates (a, b, d), +-5 pp margin.** Paired differences mode - none, cluster bootstrap over the 72 tasks (10,000 resamples), Holm over all 60 McNemar tests: no honest-template test significant after correction (every Holm-adjusted p = 1; smallest raw p = 0.041, gpt-oss jwt - none over 6 configurations, +3.0 pp, 95% CI [+0.2, +6.0]; the c and e tests remain significant except Granite e jwt - none, Holm p = 0.066). With the 3 temperature-0.7 seeds (216 units per model), the 90% CI lies inside +-5 pp (equivalence at alpha = 0.05) for 12 of 15 (model, mode) pairs; not shown equivalent: gpt-oss mm - none (-0.9 pp, 90% CI [-5.1, +2.8]), gpt-oss mm_esc - none (-1.4, [-5.6, +2.8]), Granite mm_esc - none (+1.9, [-2.3, +6.0]). Pooling the 6 configurations (432 units), 14 of 15 pairs are equivalent; the exception is gpt-oss jwt - none (+3.0, 90% CI [+0.7, +5.6]). For mm - none specifically: equivalent for all 5 models when pooling the 6 configurations (largest |diff| 0.9 pp), and for 4 of 5 with t07 alone.
* **Slowdown (task wall time, honest templates, paired units with tool latency; median / ratio of sums / p95 of the per-unit ratio).** mm / none: Qwen-7B 2.32 / 2.06 / 3.78; Qwen-72B 1.49 / 1.56 / 1.91; gpt-oss 1.71 / 1.71 / 2.46; Hermes-3 2.29 / 2.32 / 3.08; Granite 1.81 / 1.80 / 2.81 (mm_esc within 0.05 of mm). jwt / none: 1.00 median for every model (ratio of sums 0.98-1.02, p95 1.03-1.36). Without tool latency, mm / none medians 1.55-3.14.
* **Authorisation share of task wall time** (t0, ratio of sums): mm 34.7 % (Qwen-72B) to 58.6 % (Hermes-3), of which per-call proofs 21-37 points and delegation 13-22 points; jwt 0.2-0.5 %. Per call (single core): MM prove 352.5 ms, verify 94.8 ms (mm_esc 354.6 / 97.3 ms), `_meta` 18.1 kB (18.8 kB with escrow), challenge round trip 1.6-2.3 ms; delegation 2.46 s (parent 2.07 s + issuer 0.39 s); JWT 0.11 + 0.36 ms, 0.84 kB.
* **Shared issuer with concurrent revocations (new).** One Authority per worker, one dummy revocation every 2 s (0.51-0.52 revocations/s per worker achieved, 349-713 per run). W = 0: 94 of 556 honest calls (16.9 %, Qwen-72B) and 81 of 420 (19.3 %, gpt-oss) rejected, every one attributable to accumulator churn (presentation built against version v, verified after the tool installed v+1); task success falls from 87.5 % (per-task issuer, same tasks, t0 mm) to 65.0 % (Qwen-72B) and from 94.2 % to 52.5 % (gpt-oss). W = 2: 0 of 629 and 0 of 624 honest calls rejected, success 88.3 % and 95.8 % (same as with a per-task issuer). Revocation delay (request to the moment no tool accepts a pre-revocation accumulator): W = 0 median 239 / 228 ms (p95 261 / 265 ms); W = 2 median 4.22 s (p95 5.5-5.9 s), i.e. about W x the inter-revocation interval. No revoked or beyond-quota call accepted in any shared run. `Authority.revoke` with ~220 live mandates per worker (200 dummies + the tasks' sub-agents): 100-115 ms median (it refreshes every mandate's witness), on the agent's core, vs 2.5 ms with a per-task issuer.
* **Wallet in a separate process (IPC, Qwen-7B, mode mm, t0, 120 tasks):** added latency 0.14 ms per presentation (median; p95 0.16 ms) on top of 352.5 ms of proving; median task wall 6,469 ms vs 6,482 ms in-process.
* **Models.** The five models of v2: Qwen2.5-7B-Instruct, Qwen2.5-72B-Instruct-AWQ, gpt-oss-20b, Hermes-3-Llama-3.1-8B, Granite-3.3-8B-Instruct (same vLLM 0.33.0 serving, parsers and chat templates). Mistral-Small-3.2 is absent: its weights were removed from Hedy after v1 and re-downloading ~48 GB would push the home directory beyond its quota (409 GB used of 450 GB soft; the brief caps usage at 440 GB).


## Provenance

| file | git commit (local tree copied to Hedy) | mmpy .so sha256 | e4v21.py sha256 | rows |
|---|---|---|---|---|
| e4v21_qwen2.5-7b-instruct.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 2880 |
| e4v21_qwen2.5-72b-instruct-awq.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 2880 |
| e4v21_gpt-oss-20b.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 2880 |
| e4v21_hermes-3-llama-3.1-8b.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 2880 |
| e4v21_granite-3.3-8b-instruct.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 2880 |
| e4v21_shared_gpt-oss-20b_W0.json | 060ced918f45 | 1ace11bfcc7238df... | 3ce67f88fdf3 | 120 |
| e4v21_shared_gpt-oss-20b_W2.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 120 |
| e4v21_shared_qwen2.5-72b-instruct-awq_W0.json | 060ced918f45 | 1ace11bfcc7238df... | 487f16a4a5fa | 120 |
| e4v21_shared_qwen2.5-72b-instruct-awq_W2.json | 060ced918f45 | 1ace11bfcc7238df... | 3ce67f88fdf3 | 120 |

## Models and serving configuration

| model | weights | vLLM tool parser | chat template | workers | runs | errors left | re-run units | nudged runs | nudges |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | Qwen2.5-7B-Instruct | hermes | model default (tokenizer_config.json) | 5 | 2880 | 0 | 0 | 120 | 160 |
| qwen2.5-72b-instruct-awq | Qwen2.5-72B-Instruct-AWQ | hermes | model default (tokenizer_config.json) | 5 | 2880 | 0 | 0 | 0 | 0 |
| gpt-oss-20b | gpt-oss-20b | openai | model default (tokenizer_config.json) | 5 | 2880 | 0 | 0 | 428 | 468 |
| hermes-3-llama-3.1-8b | Hermes-3-Llama-3.1-8B | hermes | hermes3_tool_use.jinja | 5 | 2880 | 0 | 0 | 1068 | 1695 |
| granite-3.3-8b-instruct | granite-3.3-8b-instruct | granite | granite33_tools.jinja | 5 | 2880 | 0 | 0 | 813 | 1401 |

## Task success (temperature 0, tool latency on)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 45.8 [27.9, 64.9] (n=24) | 45.8 [27.9, 64.9] (n=24) | 50.0 [31.4, 68.6] (n=24) | 45.8 [27.9, 64.9] (n=24) |
| qwen2.5-7b-instruct | b | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | c | 4.2 [0.7, 20.2] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | d | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 25.0 [12.0, 44.9] (n=24) | 16.7 [6.7, 35.9] (n=24) |
| qwen2.5-7b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-7b-instruct | all | 24.2 [17.4, 32.6] (n=120) | 48.3 [39.6, 57.2] (n=120) | 50.0 [41.2, 58.8] (n=120) | 47.5 [38.8, 56.4] (n=120) |
| qwen2.5-72b-instruct-awq | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| qwen2.5-72b-instruct-awq | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | d | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | e | 0.0 [0.0, 13.8] (n=24) | 75.0 [55.1, 88.0] (n=24) | 70.8 [50.8, 85.1] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | all | 53.3 [44.4, 62.0] (n=120) | 88.3 [81.4, 92.9] (n=120) | 87.5 [80.4, 92.3] (n=120) | 88.3 [81.4, 92.9] (n=120) |
| gpt-oss-20b | a | 79.2 [59.5, 90.8] (n=24) | 95.8 [79.8, 99.3] (n=24) | 87.5 [69.0, 95.7] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | d | 87.5 [69.0, 95.7] (n=24) | 83.3 [64.1, 93.3] (n=24) | 83.3 [64.1, 93.3] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| gpt-oss-20b | e | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | all | 53.3 [44.4, 62.0] (n=120) | 95.8 [90.6, 98.2] (n=120) | 94.2 [88.4, 97.1] (n=120) | 95.8 [90.6, 98.2] (n=120) |
| hermes-3-llama-3.1-8b | a | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | b | 25.0 [12.0, 44.9] (n=24) | 29.2 [14.9, 49.2] (n=24) | 25.0 [12.0, 44.9] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 13.8] (n=24) | 37.5 [21.2, 57.3] (n=24) | 37.5 [21.2, 57.3] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| hermes-3-llama-3.1-8b | d | 20.8 [9.2, 40.5] (n=24) | 16.7 [6.7, 35.9] (n=24) | 16.7 [6.7, 35.9] (n=24) | 25.0 [12.0, 44.9] (n=24) |
| hermes-3-llama-3.1-8b | e | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) |
| hermes-3-llama-3.1-8b | all | 13.3 [8.4, 20.6] (n=120) | 20.8 [14.5, 28.9] (n=120) | 20.0 [13.8, 28.0] (n=120) | 25.0 [18.1, 33.4] (n=120) |
| granite-3.3-8b-instruct | a | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 33.3 [18.0, 53.3] (n=24) |
| granite-3.3-8b-instruct | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 8.3 [2.3, 25.8] (n=24) |
| granite-3.3-8b-instruct | d | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 16.7 [6.7, 35.9] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| granite-3.3-8b-instruct | all | 16.7 [11.1, 24.3] (n=120) | 21.7 [15.2, 29.9] (n=120) | 22.5 [15.9, 30.8] (n=120) | 21.7 [15.2, 29.9] (n=120) |

## Task success (replication of t0, identical settings)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | b | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | d | 20.8 [9.2, 40.5] (n=24) | 16.7 [6.7, 35.9] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| qwen2.5-7b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-7b-instruct | all | 24.2 [17.4, 32.6] (n=120) | 48.3 [39.6, 57.2] (n=120) | 49.2 [40.4, 58.0] (n=120) | 49.2 [40.4, 58.0] (n=120) |
| qwen2.5-72b-instruct-awq | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| qwen2.5-72b-instruct-awq | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | d | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | e | 0.0 [0.0, 13.8] (n=24) | 70.8 [50.8, 85.1] (n=24) | 70.8 [50.8, 85.1] (n=24) | 70.8 [50.8, 85.1] (n=24) |
| qwen2.5-72b-instruct-awq | all | 53.3 [44.4, 62.0] (n=120) | 87.5 [80.4, 92.3] (n=120) | 87.5 [80.4, 92.3] (n=120) | 87.5 [80.4, 92.3] (n=120) |
| gpt-oss-20b | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | d | 79.2 [59.5, 90.8] (n=24) | 87.5 [69.0, 95.7] (n=24) | 83.3 [64.1, 93.3] (n=24) | 79.2 [59.5, 90.8] (n=24) |
| gpt-oss-20b | e | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | all | 54.2 [45.3, 62.8] (n=120) | 95.8 [90.6, 98.2] (n=120) | 95.0 [89.5, 97.7] (n=120) | 93.3 [87.4, 96.6] (n=120) |
| hermes-3-llama-3.1-8b | a | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 20.8 [9.2, 40.5] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 13.8] (n=24) | 45.8 [27.9, 64.9] (n=24) | 45.8 [27.9, 64.9] (n=24) | 41.7 [24.5, 61.2] (n=24) |
| hermes-3-llama-3.1-8b | d | 16.7 [6.7, 35.9] (n=24) | 16.7 [6.7, 35.9] (n=24) | 16.7 [6.7, 35.9] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | e | 0.0 [0.0, 13.8] (n=24) | 4.2 [0.7, 20.2] (n=24) | 4.2 [0.7, 20.2] (n=24) | 0.0 [0.0, 13.8] (n=24) |
| hermes-3-llama-3.1-8b | all | 13.3 [8.4, 20.6] (n=120) | 23.3 [16.7, 31.7] (n=120) | 21.7 [15.2, 29.9] (n=120) | 22.5 [15.9, 30.8] (n=120) |
| granite-3.3-8b-instruct | a | 37.5 [21.2, 57.3] (n=24) | 37.5 [21.2, 57.3] (n=24) | 37.5 [21.2, 57.3] (n=24) | 37.5 [21.2, 57.3] (n=24) |
| granite-3.3-8b-instruct | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | d | 8.3 [2.3, 25.8] (n=24) | 8.3 [2.3, 25.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 8.3 [2.3, 25.8] (n=24) |
| granite-3.3-8b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | all | 15.0 [9.7, 22.5] (n=120) | 21.7 [15.2, 29.9] (n=120) | 23.3 [16.7, 31.7] (n=120) | 20.0 [13.8, 28.0] (n=120) |

## Task success (temperature 0.7, 3 seeds)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 47.2 [36.1, 58.6] (n=72) | 47.2 [36.1, 58.6] (n=72) | 47.2 [36.1, 58.6] (n=72) | 45.8 [34.8, 57.3] (n=72) |
| qwen2.5-7b-instruct | b | 48.6 [37.4, 59.9] (n=72) | 48.6 [37.4, 59.9] (n=72) | 48.6 [37.4, 59.9] (n=72) | 48.6 [37.4, 59.9] (n=72) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 5.1] (n=72) | 54.2 [42.7, 65.2] (n=72) | 55.6 [44.1, 66.5] (n=72) | 55.6 [44.1, 66.5] (n=72) |
| qwen2.5-7b-instruct | d | 16.7 [9.8, 26.9] (n=72) | 16.7 [9.8, 26.9] (n=72) | 15.3 [8.8, 25.3] (n=72) | 18.1 [10.9, 28.5] (n=72) |
| qwen2.5-7b-instruct | e | 1.4 [0.2, 7.5] (n=72) | 75.0 [63.9, 83.6] (n=72) | 75.0 [63.9, 83.6] (n=72) | 75.0 [63.9, 83.6] (n=72) |
| qwen2.5-7b-instruct | all | 22.8 [18.7, 27.4] (n=360) | 48.3 [43.2, 53.5] (n=360) | 48.3 [43.2, 53.5] (n=360) | 48.6 [43.5, 53.8] (n=360) |
| qwen2.5-72b-instruct-awq | a | 70.8 [59.5, 80.1] (n=72) | 69.4 [58.0, 78.9] (n=72) | 70.8 [59.5, 80.1] (n=72) | 70.8 [59.5, 80.1] (n=72) |
| qwen2.5-72b-instruct-awq | b | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 5.1] (n=72) | 98.6 [92.5, 99.8] (n=72) | 98.6 [92.5, 99.8] (n=72) | 98.6 [92.5, 99.8] (n=72) |
| qwen2.5-72b-instruct-awq | d | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) |
| qwen2.5-72b-instruct-awq | e | 0.0 [0.0, 5.1] (n=72) | 77.8 [66.9, 85.8] (n=72) | 77.8 [66.9, 85.8] (n=72) | 77.8 [66.9, 85.8] (n=72) |
| qwen2.5-72b-instruct-awq | all | 47.8 [42.7, 52.9] (n=360) | 82.8 [78.5, 86.3] (n=360) | 83.1 [78.8, 86.6] (n=360) | 83.1 [78.8, 86.6] (n=360) |
| gpt-oss-20b | a | 93.1 [84.8, 97.0] (n=72) | 94.4 [86.6, 97.8] (n=72) | 94.4 [86.6, 97.8] (n=72) | 93.1 [84.8, 97.0] (n=72) |
| gpt-oss-20b | b | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| gpt-oss-20b | c | 0.0 [0.0, 5.1] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| gpt-oss-20b | d | 79.2 [68.4, 86.9] (n=72) | 81.9 [71.5, 89.1] (n=72) | 75.0 [63.9, 83.6] (n=72) | 75.0 [63.9, 83.6] (n=72) |
| gpt-oss-20b | e | 1.4 [0.2, 7.5] (n=72) | 100.0 [94.9, 100.0] (n=72) | 98.6 [92.5, 99.8] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| gpt-oss-20b | all | 54.7 [49.6, 59.8] (n=360) | 95.3 [92.6, 97.0] (n=360) | 93.6 [90.6, 95.7] (n=360) | 93.6 [90.6, 95.7] (n=360) |
| hermes-3-llama-3.1-8b | a | 26.4 [17.6, 37.6] (n=72) | 26.4 [17.6, 37.6] (n=72) | 26.4 [17.6, 37.6] (n=72) | 26.4 [17.6, 37.6] (n=72) |
| hermes-3-llama-3.1-8b | b | 18.1 [10.9, 28.5] (n=72) | 18.1 [10.9, 28.5] (n=72) | 18.1 [10.9, 28.5] (n=72) | 19.4 [12.0, 30.0] (n=72) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 5.1] (n=72) | 41.7 [31.0, 53.2] (n=72) | 48.6 [37.4, 59.9] (n=72) | 44.4 [33.5, 55.9] (n=72) |
| hermes-3-llama-3.1-8b | d | 19.4 [12.0, 30.0] (n=72) | 18.1 [10.9, 28.5] (n=72) | 16.7 [9.8, 26.9] (n=72) | 18.1 [10.9, 28.5] (n=72) |
| hermes-3-llama-3.1-8b | e | 0.0 [0.0, 5.1] (n=72) | 2.8 [0.8, 9.6] (n=72) | 2.8 [0.8, 9.6] (n=72) | 2.8 [0.8, 9.6] (n=72) |
| hermes-3-llama-3.1-8b | all | 12.8 [9.7, 16.6] (n=360) | 21.4 [17.5, 25.9] (n=360) | 22.5 [18.5, 27.1] (n=360) | 22.2 [18.2, 26.8] (n=360) |
| granite-3.3-8b-instruct | a | 27.8 [18.8, 39.0] (n=72) | 27.8 [18.8, 39.0] (n=72) | 27.8 [18.8, 39.0] (n=72) | 31.9 [22.3, 43.4] (n=72) |
| granite-3.3-8b-instruct | b | 26.4 [17.6, 37.6] (n=72) | 27.8 [18.8, 39.0] (n=72) | 26.4 [17.6, 37.6] (n=72) | 25.0 [16.4, 36.1] (n=72) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 5.1] (n=72) | 22.2 [14.2, 33.1] (n=72) | 20.8 [13.1, 31.6] (n=72) | 22.2 [14.2, 33.1] (n=72) |
| granite-3.3-8b-instruct | d | 12.5 [6.7, 22.1] (n=72) | 5.6 [2.2, 13.4] (n=72) | 9.7 [4.8, 18.7] (n=72) | 15.3 [8.8, 25.3] (n=72) |
| granite-3.3-8b-instruct | e | 0.0 [0.0, 5.1] (n=72) | 13.9 [7.7, 23.7] (n=72) | 16.7 [9.8, 26.9] (n=72) | 15.3 [8.8, 25.3] (n=72) |
| granite-3.3-8b-instruct | all | 13.3 [10.2, 17.2] (n=360) | 19.4 [15.7, 23.8] (n=360) | 20.3 [16.4, 24.7] (n=360) | 21.9 [18.0, 26.5] (n=360) |

## Task success (temperature 0, zero tool latency)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 50.0 [31.4, 68.6] (n=24) | 45.8 [27.9, 64.9] (n=24) | 45.8 [27.9, 64.9] (n=24) | 45.8 [27.9, 64.9] (n=24) |
| qwen2.5-7b-instruct | b | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | d | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 16.7 [6.7, 35.9] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| qwen2.5-7b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-7b-instruct | all | 24.2 [17.4, 32.6] (n=120) | 48.3 [39.6, 57.2] (n=120) | 47.5 [38.8, 56.4] (n=120) | 48.3 [39.6, 57.2] (n=120) |
| qwen2.5-72b-instruct-awq | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| qwen2.5-72b-instruct-awq | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | d | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | e | 0.0 [0.0, 13.8] (n=24) | 75.0 [55.1, 88.0] (n=24) | 70.8 [50.8, 85.1] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | all | 53.3 [44.4, 62.0] (n=120) | 88.3 [81.4, 92.9] (n=120) | 87.5 [80.4, 92.3] (n=120) | 88.3 [81.4, 92.9] (n=120) |
| gpt-oss-20b | a | 87.5 [69.0, 95.7] (n=24) | 95.8 [79.8, 99.3] (n=24) | 87.5 [69.0, 95.7] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | d | 75.0 [55.1, 88.0] (n=24) | 87.5 [69.0, 95.7] (n=24) | 83.3 [64.1, 93.3] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | e | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | all | 52.5 [43.6, 61.2] (n=120) | 96.7 [91.7, 98.7] (n=120) | 94.2 [88.4, 97.1] (n=120) | 95.0 [89.5, 97.7] (n=120) |
| hermes-3-llama-3.1-8b | a | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 13.8] (n=24) | 45.8 [27.9, 64.9] (n=24) | 41.7 [24.5, 61.2] (n=24) | 45.8 [27.9, 64.9] (n=24) |
| hermes-3-llama-3.1-8b | d | 16.7 [6.7, 35.9] (n=24) | 16.7 [6.7, 35.9] (n=24) | 20.8 [9.2, 40.5] (n=24) | 25.0 [12.0, 44.9] (n=24) |
| hermes-3-llama-3.1-8b | e | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) | 0.0 [0.0, 13.8] (n=24) |
| hermes-3-llama-3.1-8b | all | 13.3 [8.4, 20.6] (n=120) | 22.5 [15.9, 30.8] (n=120) | 22.5 [15.9, 30.8] (n=120) | 24.2 [17.4, 32.6] (n=120) |
| granite-3.3-8b-instruct | a | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) | 37.5 [21.2, 57.3] (n=24) |
| granite-3.3-8b-instruct | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | d | 8.3 [2.3, 25.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 8.3 [2.3, 25.8] (n=24) | 8.3 [2.3, 25.8] (n=24) |
| granite-3.3-8b-instruct | e | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | all | 14.2 [9.0, 21.5] (n=120) | 19.2 [13.1, 27.1] (n=120) | 20.0 [13.8, 28.0] (n=120) | 20.0 [13.8, 28.0] (n=120) |

## Replication control: t0 run twice with identical settings (t0 vs t0_rep)

Success discordance = units whose success differs between the two identical runs (same model, same mode). Transcript identity = identical LLM-visible transcripts (templates a, b, d).

| model | mode | a,b,d: discordant / pairs | c | e | all | identical transcripts (a,b,d) | t0 vs t0_nolat: discordant (all) |
|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 1 / 72 | 1 / 24 | 0 / 24 | 2 / 120 | 62/72 | 2 / 120 |
| qwen2.5-7b-instruct | jwt | 2 / 72 | 0 / 24 | 0 / 24 | 2 / 120 | 59/72 | 0 / 120 |
| qwen2.5-7b-instruct | mm | 1 / 72 | 0 / 24 | 0 / 24 | 1 / 120 | 62/72 | 3 / 120 |
| qwen2.5-7b-instruct | mm_esc | 2 / 72 | 0 / 24 | 0 / 24 | 2 / 120 | 60/72 | 1 / 120 |
| qwen2.5-72b-instruct-awq | none | 0 / 72 | 0 / 24 | 0 / 24 | 0 / 120 | 72/72 | 0 / 120 |
| qwen2.5-72b-instruct-awq | jwt | 0 / 72 | 0 / 24 | 1 / 24 | 1 / 120 | 72/72 | 0 / 120 |
| qwen2.5-72b-instruct-awq | mm | 0 / 72 | 0 / 24 | 0 / 24 | 0 / 120 | 72/72 | 0 / 120 |
| qwen2.5-72b-instruct-awq | mm_esc | 0 / 72 | 0 / 24 | 1 / 24 | 1 / 120 | 72/72 | 0 / 120 |
| gpt-oss-20b | none | 7 / 72 | 0 / 24 | 0 / 24 | 7 / 120 | 55/72 | 5 / 120 |
| gpt-oss-20b | jwt | 4 / 72 | 0 / 24 | 0 / 24 | 4 / 120 | 58/72 | 1 / 120 |
| gpt-oss-20b | mm | 1 / 72 | 0 / 24 | 0 / 24 | 1 / 120 | 58/72 | 2 / 120 |
| gpt-oss-20b | mm_esc | 7 / 72 | 0 / 24 | 0 / 24 | 7 / 120 | 54/72 | 5 / 120 |
| hermes-3-llama-3.1-8b | none | 2 / 72 | 0 / 24 | 0 / 24 | 2 / 120 | 53/72 | 2 / 120 |
| hermes-3-llama-3.1-8b | jwt | 2 / 72 | 4 / 24 | 1 / 24 | 7 / 120 | 52/72 | 4 / 120 |
| hermes-3-llama-3.1-8b | mm | 1 / 72 | 2 / 24 | 1 / 24 | 4 / 120 | 49/72 | 5 / 120 |
| hermes-3-llama-3.1-8b | mm_esc | 1 / 72 | 4 / 24 | 0 / 24 | 5 / 120 | 48/72 | 1 / 120 |
| granite-3.3-8b-instruct | none | 2 / 72 | 0 / 24 | 0 / 24 | 2 / 120 | 31/72 | 5 / 120 |
| granite-3.3-8b-instruct | jwt | 2 / 72 | 0 / 24 | 2 / 24 | 4 / 120 | 37/72 | 5 / 120 |
| granite-3.3-8b-instruct | mm | 2 / 72 | 0 / 24 | 5 / 24 | 7 / 120 | 37/72 | 7 / 120 |
| granite-3.3-8b-instruct | mm_esc | 3 / 72 | 1 / 24 | 2 / 24 | 6 / 120 | 25/72 | 8 / 120 |

## Paired differences with respect to `none` (cluster bootstrap over tasks, exact McNemar, Holm)

Difference = success rate of the mode minus success rate of `none` on the same (task, configuration) units, in percentage points. CIs: percentile cluster bootstrap (10000 resamples; clusters = tasks, units = seeds/configurations within a task). p: exact McNemar on the discordant units; p_Holm: Holm correction over all 60 McNemar tests of this table. Equivalence (margin +-5 pp): TOST at alpha = 0.05, i.e. the 90% CI lies inside [-5, +5]; the stricter column requires the 95% CI inside the margin. For templates c and e the difference is the expected effect of authorisation (no equivalence claimed).

| model | scope | configurations | pair | units (tasks) | rate none | rate mode | diff pp | 95% CI | 90% CI | discordant none-only / mode-only | p McNemar | p Holm | equivalent (90% CI in +-5) | 95% CI in +-5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | honest a,b,d | t07 (3 seeds) | jwt-none | 216 (72) | 37.5 | 37.5 | +0.0 | [-1.9, +1.9] | [-1.4, +1.4] | 2 / 2 | 1 | 1 | yes | yes |
| qwen2.5-7b-instruct | honest a,b,d | t07 (3 seeds) | mm-none | 216 (72) | 37.5 | 37.0 | -0.5 | [-2.3, +0.9] | [-1.9, +0.9] | 2 / 1 | 1 | 1 | yes | yes |
| qwen2.5-7b-instruct | honest a,b,d | t07 (3 seeds) | mm_esc-none | 216 (72) | 37.5 | 37.5 | +0.0 | [-1.9, +1.9] | [-1.4, +1.4] | 2 / 2 | 1 | 1 | yes | yes |
| qwen2.5-7b-instruct | honest a,b,d | all 6 configurations | jwt-none | 432 (72) | 38.7 | 38.2 | -0.5 | [-1.6, +0.7] | [-1.4, +0.5] | 4 / 2 | 0.688 | 1 | yes | yes |
| qwen2.5-7b-instruct | honest a,b,d | all 6 configurations | mm-none | 432 (72) | 38.7 | 38.4 | -0.2 | [-1.2, +0.7] | [-1.2, +0.7] | 4 / 3 | 1 | 1 | yes | yes |
| qwen2.5-7b-instruct | honest a,b,d | all 6 configurations | mm_esc-none | 432 (72) | 38.7 | 38.2 | -0.5 | [-1.4, +0.5] | [-1.2, +0.2] | 4 / 2 | 0.688 | 1 | yes | yes |
| qwen2.5-7b-instruct | revocation c | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 54.2 | +54.2 | [+36.1, +72.2] | [+38.9, +69.4] | 0 / 39 | 3.64e-12 | 1.56e-10 | n/a | n/a |
| qwen2.5-7b-instruct | revocation c | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 55.6 | +55.6 | [+36.1, +73.6] | [+40.3, +70.8] | 0 / 40 | 1.82e-12 | 8.19e-11 | n/a | n/a |
| qwen2.5-7b-instruct | revocation c | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 55.6 | +55.6 | [+36.1, +73.6] | [+40.3, +70.8] | 0 / 40 | 1.82e-12 | 8.19e-11 | n/a | n/a |
| qwen2.5-7b-instruct | quota e | t07 (3 seeds) | jwt-none | 72 (24) | 1.4 | 75.0 | +73.6 | [+55.6, +90.3] | [+58.3, +87.5] | 0 / 53 | 2.22e-16 | 1.07e-14 | n/a | n/a |
| qwen2.5-7b-instruct | quota e | t07 (3 seeds) | mm-none | 72 (24) | 1.4 | 75.0 | +73.6 | [+56.9, +90.3] | [+58.3, +87.5] | 0 / 53 | 2.22e-16 | 1.07e-14 | n/a | n/a |
| qwen2.5-7b-instruct | quota e | t07 (3 seeds) | mm_esc-none | 72 (24) | 1.4 | 75.0 | +73.6 | [+56.9, +90.3] | [+58.3, +87.5] | 0 / 53 | 2.22e-16 | 1.07e-14 | n/a | n/a |
| qwen2.5-72b-instruct-awq | honest a,b,d | t07 (3 seeds) | jwt-none | 216 (72) | 79.6 | 79.2 | -0.5 | [-1.4, +0.0] | [-1.4, +0.0] | 1 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | honest a,b,d | t07 (3 seeds) | mm-none | 216 (72) | 79.6 | 79.6 | +0.0 | [+0.0, +0.0] | [+0.0, +0.0] | 0 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | honest a,b,d | t07 (3 seeds) | mm_esc-none | 216 (72) | 79.6 | 79.6 | +0.0 | [+0.0, +0.0] | [+0.0, +0.0] | 0 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | honest a,b,d | all 6 configurations | jwt-none | 432 (72) | 84.3 | 84.0 | -0.2 | [-0.7, +0.0] | [-0.7, +0.0] | 1 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | honest a,b,d | all 6 configurations | mm-none | 432 (72) | 84.3 | 84.3 | +0.0 | [+0.0, +0.0] | [+0.0, +0.0] | 0 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | honest a,b,d | all 6 configurations | mm_esc-none | 432 (72) | 84.3 | 84.3 | +0.0 | [+0.0, +0.0] | [+0.0, +0.0] | 0 / 0 | 1 | 1 | yes | yes |
| qwen2.5-72b-instruct-awq | revocation c | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 98.6 | +98.6 | [+95.8, +100.0] | [+95.8, +100.0] | 0 / 71 | 8.47e-22 | 4.83e-20 | n/a | n/a |
| qwen2.5-72b-instruct-awq | revocation c | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 98.6 | +98.6 | [+95.8, +100.0] | [+95.8, +100.0] | 0 / 71 | 8.47e-22 | 4.83e-20 | n/a | n/a |
| qwen2.5-72b-instruct-awq | revocation c | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 98.6 | +98.6 | [+95.8, +100.0] | [+95.8, +100.0] | 0 / 71 | 8.47e-22 | 4.83e-20 | n/a | n/a |
| qwen2.5-72b-instruct-awq | quota e | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 77.8 | +77.8 | [+66.7, +87.5] | [+68.1, +86.1] | 0 / 56 | 2.78e-17 | 1.42e-15 | n/a | n/a |
| qwen2.5-72b-instruct-awq | quota e | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 77.8 | +77.8 | [+66.7, +87.5] | [+68.1, +86.1] | 0 / 56 | 2.78e-17 | 1.42e-15 | n/a | n/a |
| qwen2.5-72b-instruct-awq | quota e | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 77.8 | +77.8 | [+66.7, +87.5] | [+69.4, +86.1] | 0 / 56 | 2.78e-17 | 1.42e-15 | n/a | n/a |
| gpt-oss-20b | honest a,b,d | t07 (3 seeds) | jwt-none | 216 (72) | 90.7 | 92.1 | +1.4 | [-2.8, +5.6] | [-1.9, +4.6] | 8 / 11 | 0.648 | 1 | yes | no |
| gpt-oss-20b | honest a,b,d | t07 (3 seeds) | mm-none | 216 (72) | 90.7 | 89.8 | -0.9 | [-6.0, +3.7] | [-5.1, +3.2] | 14 / 12 | 0.845 | 1 | no | no |
| gpt-oss-20b | honest a,b,d | t07 (3 seeds) | mm_esc-none | 216 (72) | 90.7 | 89.4 | -1.4 | [-6.0, +3.2] | [-5.1, +2.8] | 12 / 9 | 0.664 | 1 | no | no |
| gpt-oss-20b | honest a,b,d | all 6 configurations | jwt-none | 432 (72) | 89.8 | 92.8 | +3.0 | [+0.2, +6.0] | [+0.5, +5.6] | 11 / 24 | 0.041 | 1 | no | no |
| gpt-oss-20b | honest a,b,d | all 6 configurations | mm-none | 432 (72) | 89.8 | 90.3 | +0.5 | [-2.5, +3.2] | [-1.9, +2.8] | 17 / 19 | 0.868 | 1 | yes | yes |
| gpt-oss-20b | honest a,b,d | all 6 configurations | mm_esc-none | 432 (72) | 89.8 | 90.3 | +0.5 | [-2.5, +3.7] | [-2.1, +3.2] | 17 / 19 | 0.868 | 1 | yes | yes |
| gpt-oss-20b | revocation c | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 100.0 | +100.0 | [+100.0, +100.0] | [+100.0, +100.0] | 0 / 72 | 4.24e-22 | 2.54e-20 | n/a | n/a |
| gpt-oss-20b | revocation c | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 100.0 | +100.0 | [+100.0, +100.0] | [+100.0, +100.0] | 0 / 72 | 4.24e-22 | 2.54e-20 | n/a | n/a |
| gpt-oss-20b | revocation c | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 100.0 | +100.0 | [+100.0, +100.0] | [+100.0, +100.0] | 0 / 72 | 4.24e-22 | 2.54e-20 | n/a | n/a |
| gpt-oss-20b | quota e | t07 (3 seeds) | jwt-none | 72 (24) | 1.4 | 100.0 | +98.6 | [+95.8, +100.0] | [+95.8, +100.0] | 0 / 71 | 8.47e-22 | 4.83e-20 | n/a | n/a |
| gpt-oss-20b | quota e | t07 (3 seeds) | mm-none | 72 (24) | 1.4 | 98.6 | +97.2 | [+93.1, +100.0] | [+94.4, +100.0] | 0 / 70 | 1.69e-21 | 8.81e-20 | n/a | n/a |
| gpt-oss-20b | quota e | t07 (3 seeds) | mm_esc-none | 72 (24) | 1.4 | 100.0 | +98.6 | [+95.8, +100.0] | [+95.8, +100.0] | 0 / 71 | 8.47e-22 | 4.83e-20 | n/a | n/a |
| hermes-3-llama-3.1-8b | honest a,b,d | t07 (3 seeds) | jwt-none | 216 (72) | 21.3 | 20.8 | -0.5 | [-2.3, +1.4] | [-2.3, +1.4] | 3 / 2 | 1 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | honest a,b,d | t07 (3 seeds) | mm-none | 216 (72) | 21.3 | 20.4 | -0.9 | [-3.2, +1.4] | [-2.8, +0.9] | 4 / 2 | 0.688 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | honest a,b,d | t07 (3 seeds) | mm_esc-none | 216 (72) | 21.3 | 21.3 | +0.0 | [-1.9, +1.9] | [-1.4, +1.4] | 2 / 2 | 1 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | honest a,b,d | all 6 configurations | jwt-none | 432 (72) | 21.8 | 21.5 | -0.2 | [-1.9, +1.2] | [-1.6, +0.9] | 6 / 5 | 1 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | honest a,b,d | all 6 configurations | mm-none | 432 (72) | 21.8 | 20.8 | -0.9 | [-2.3, +0.2] | [-2.1, +0.0] | 8 / 4 | 0.388 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | honest a,b,d | all 6 configurations | mm_esc-none | 432 (72) | 21.8 | 22.9 | +1.2 | [-0.5, +3.0] | [-0.2, +2.8] | 2 / 7 | 0.18 | 1 | yes | yes |
| hermes-3-llama-3.1-8b | revocation c | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 41.7 | +41.7 | [+26.4, +56.9] | [+29.2, +54.2] | 0 / 30 | 1.86e-09 | 7.45e-08 | n/a | n/a |
| hermes-3-llama-3.1-8b | revocation c | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 48.6 | +48.6 | [+34.7, +62.5] | [+36.1, +61.1] | 0 / 35 | 5.82e-11 | 2.44e-09 | n/a | n/a |
| hermes-3-llama-3.1-8b | revocation c | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 44.4 | +44.4 | [+30.6, +58.3] | [+33.3, +55.6] | 0 / 32 | 4.66e-10 | 1.91e-08 | n/a | n/a |
| hermes-3-llama-3.1-8b | quota e | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 2.8 | +2.8 | [+0.0, +6.9] | [+0.0, +5.6] | 0 / 2 | 0.5 | 1 | n/a | n/a |
| hermes-3-llama-3.1-8b | quota e | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 2.8 | +2.8 | [+0.0, +6.9] | [+0.0, +5.6] | 0 / 2 | 0.5 | 1 | n/a | n/a |
| hermes-3-llama-3.1-8b | quota e | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 2.8 | +2.8 | [+0.0, +6.9] | [+0.0, +5.6] | 0 / 2 | 0.5 | 1 | n/a | n/a |
| granite-3.3-8b-instruct | honest a,b,d | t07 (3 seeds) | jwt-none | 216 (72) | 22.2 | 20.4 | -1.9 | [-5.1, +1.4] | [-4.6, +0.9] | 10 / 6 | 0.454 | 1 | yes | no |
| granite-3.3-8b-instruct | honest a,b,d | t07 (3 seeds) | mm-none | 216 (72) | 22.2 | 21.3 | -0.9 | [-4.6, +2.3] | [-3.7, +1.9] | 8 / 6 | 0.791 | 1 | yes | yes |
| granite-3.3-8b-instruct | honest a,b,d | t07 (3 seeds) | mm_esc-none | 216 (72) | 22.2 | 24.1 | +1.9 | [-2.8, +6.9] | [-2.3, +6.0] | 10 / 14 | 0.541 | 1 | no | no |
| granite-3.3-8b-instruct | honest a,b,d | all 6 configurations | jwt-none | 432 (72) | 23.8 | 22.9 | -0.9 | [-2.8, +1.2] | [-2.5, +0.7] | 14 / 10 | 0.541 | 1 | yes | yes |
| granite-3.3-8b-instruct | honest a,b,d | all 6 configurations | mm-none | 432 (72) | 23.8 | 24.1 | +0.2 | [-1.6, +2.1] | [-1.4, +1.9] | 10 / 11 | 1 | 1 | yes | yes |
| granite-3.3-8b-instruct | honest a,b,d | all 6 configurations | mm_esc-none | 432 (72) | 23.8 | 24.8 | +0.9 | [-1.6, +3.5] | [-1.2, +3.0] | 13 / 17 | 0.585 | 1 | yes | yes |
| granite-3.3-8b-instruct | revocation c | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 22.2 | +22.2 | [+12.5, +31.9] | [+13.9, +30.6] | 0 / 16 | 3.05e-05 | 0.00119 | n/a | n/a |
| granite-3.3-8b-instruct | revocation c | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 20.8 | +20.8 | [+11.1, +30.6] | [+12.5, +29.2] | 0 / 15 | 6.1e-05 | 0.00226 | n/a | n/a |
| granite-3.3-8b-instruct | revocation c | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 22.2 | +22.2 | [+11.1, +33.3] | [+12.5, +31.9] | 0 / 16 | 3.05e-05 | 0.00119 | n/a | n/a |
| granite-3.3-8b-instruct | quota e | t07 (3 seeds) | jwt-none | 72 (24) | 0.0 | 13.9 | +13.9 | [+5.6, +23.6] | [+6.9, +20.8] | 0 / 10 | 0.00195 | 0.0664 | n/a | n/a |
| granite-3.3-8b-instruct | quota e | t07 (3 seeds) | mm-none | 72 (24) | 0.0 | 16.7 | +16.7 | [+9.7, +25.0] | [+9.7, +23.6] | 0 / 12 | 0.000488 | 0.0176 | n/a | n/a |
| granite-3.3-8b-instruct | quota e | t07 (3 seeds) | mm_esc-none | 72 (24) | 0.0 | 15.3 | +15.3 | [+8.3, +23.6] | [+9.7, +22.2] | 0 / 11 | 0.000977 | 0.0342 | n/a | n/a |

## Template c (revocation): safe-failure rate and revoked calls (all configurations)

| model | none | jwt | mm | mm_esc | revoked calls attempted / accepted: none | jwt | mm | mm_esc | c runs claiming DONE (jwt / mm / mm_esc) |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | 0.7 [0.1, 3.8] (n=144) | 52.1 [44.0, 60.1] (n=144) | 52.8 [44.7, 60.8] (n=144) | 52.8 [44.7, 60.8] (n=144) | 254 / 254 | 147 / 0 | 148 / 0 | 145 / 0 | 4 / 4 / 4 |
| qwen2.5-72b-instruct-awq | 0.0 [0.0, 2.6] (n=144) | 99.3 [96.2, 99.9] (n=144) | 99.3 [96.2, 99.9] (n=144) | 99.3 [96.2, 99.9] (n=144) | 165 / 165 | 144 / 0 | 144 / 0 | 144 / 0 | 0 / 0 / 0 |
| gpt-oss-20b | 0.0 [0.0, 2.6] (n=144) | 100.0 [97.4, 100.0] (n=144) | 100.0 [97.4, 100.0] (n=144) | 100.0 [97.4, 100.0] (n=144) | 174 / 174 | 148 / 0 | 147 / 0 | 149 / 0 | 0 / 0 / 0 |
| hermes-3-llama-3.1-8b | 0.0 [0.0, 2.6] (n=144) | 42.4 [34.6, 50.5] (n=144) | 45.1 [37.2, 53.3] (n=144) | 45.1 [37.2, 53.3] (n=144) | 243 / 243 | 138 / 0 | 136 / 0 | 138 / 0 | 26 / 25 / 18 |
| granite-3.3-8b-instruct | 0.0 [0.0, 2.6] (n=144) | 17.4 [12.0, 24.4] (n=144) | 16.7 [11.5, 23.6] (n=144) | 16.7 [11.5, 23.6] (n=144) | 90 / 90 | 79 / 0 | 75 / 0 | 72 / 0 | 83 / 89 / 84 |

## Template e (binding quota: k = 3 hotel searches delegated, 5 needed; all configurations)

| model | mode | runs | success | flight paid | survey delegated | sub-agent reports FAILED | main reports FAILED | main claims DONE | calls beyond quota attempted | accepted | refused by the wallet (MM) | cities surveyed (median) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 144 | 0.7 [0.1, 3.8] | 108 | 144 | 3 | 4 | 140 | 378 | 378 | 0 | 5 |
| qwen2.5-7b-instruct | jwt | 144 | 75.0 [67.3, 81.4] | 108 | 144 | 144 | 144 | 0 | 295 | 0 | 0 | 3 |
| qwen2.5-7b-instruct | mm | 144 | 75.0 [67.3, 81.4] | 108 | 144 | 144 | 144 | 0 | 296 | 0 | 296 | 3 |
| qwen2.5-7b-instruct | mm_esc | 144 | 75.0 [67.3, 81.4] | 108 | 144 | 144 | 144 | 0 | 295 | 0 | 295 | 3 |
| qwen2.5-72b-instruct-awq | none | 144 | 0.0 [0.0, 2.6] | 110 | 144 | 0 | 0 | 144 | 288 | 288 | 0 | 5 |
| qwen2.5-72b-instruct-awq | jwt | 144 | 75.7 [68.1, 82.0] | 109 | 144 | 144 | 144 | 0 | 288 | 0 | 0 | 3 |
| qwen2.5-72b-instruct-awq | mm | 144 | 74.3 [66.6, 80.7] | 107 | 144 | 144 | 144 | 0 | 288 | 0 | 288 | 3 |
| qwen2.5-72b-instruct-awq | mm_esc | 144 | 75.7 [68.1, 82.0] | 109 | 144 | 144 | 144 | 0 | 288 | 0 | 288 | 3 |
| gpt-oss-20b | none | 144 | 0.7 [0.1, 3.8] | 144 | 144 | 15 | 22 | 122 | 269 | 269 | 0 | 5 |
| gpt-oss-20b | jwt | 144 | 100.0 [97.4, 100.0] | 144 | 144 | 142 | 144 | 0 | 191 | 0 | 0 | 3 |
| gpt-oss-20b | mm | 144 | 99.3 [96.2, 99.9] | 143 | 144 | 143 | 144 | 0 | 194 | 0 | 194 | 3 |
| gpt-oss-20b | mm_esc | 144 | 100.0 [97.4, 100.0] | 144 | 144 | 142 | 144 | 0 | 194 | 0 | 194 | 3 |
| hermes-3-llama-3.1-8b | none | 144 | 0.0 [0.0, 2.6] | 32 | 144 | 3 | 13 | 129 | 315 | 315 | 0 | 5 |
| hermes-3-llama-3.1-8b | jwt | 144 | 2.1 [0.7, 5.9] | 30 | 144 | 14 | 9 | 134 | 288 | 0 | 0 | 3 |
| hermes-3-llama-3.1-8b | mm | 144 | 2.1 [0.7, 5.9] | 28 | 144 | 12 | 8 | 134 | 292 | 0 | 292 | 3 |
| hermes-3-llama-3.1-8b | mm_esc | 144 | 1.4 [0.4, 4.9] | 29 | 144 | 13 | 9 | 135 | 290 | 0 | 290 | 3 |
| granite-3.3-8b-instruct | none | 144 | 0.0 [0.0, 2.6] | 74 | 107 | 1 | 0 | 144 | 204 | 204 | 0 | 5 |
| granite-3.3-8b-instruct | jwt | 144 | 14.6 [9.7, 21.3] | 83 | 101 | 85 | 44 | 100 | 173 | 0 | 0 | 3 |
| granite-3.3-8b-instruct | mm | 144 | 16.7 [11.5, 23.6] | 81 | 104 | 89 | 47 | 97 | 181 | 0 | 181 | 3 |
| granite-3.3-8b-instruct | mm_esc | 144 | 15.3 [10.3, 22.0] | 78 | 101 | 85 | 44 | 100 | 182 | 0 | 182 | 3 |

## Slowdown factors (task wall time, mode / none, paired error-free units, templates a, b, d)

| model | mode | tool latency on (t0, t0_rep, t07): units | median | ratio of sums | p95 | zero latency (t0_nolat): units | median | ratio of sums | p95 |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | jwt | 360 | 1.00 | 1.02 | 1.11 | 72 | 1.02 | 1.11 | 1.32 |
| qwen2.5-7b-instruct | mm | 360 | 2.32 | 2.06 | 3.78 | 72 | 3.11 | 2.08 | 4.79 |
| qwen2.5-7b-instruct | mm_esc | 360 | 2.33 | 2.01 | 3.79 | 72 | 3.12 | 1.74 | 4.81 |
| qwen2.5-72b-instruct-awq | jwt | 360 | 1.00 | 1.00 | 1.03 | 72 | 1.00 | 1.00 | 1.01 |
| qwen2.5-72b-instruct-awq | mm | 360 | 1.49 | 1.56 | 1.91 | 72 | 1.55 | 1.64 | 1.99 |
| qwen2.5-72b-instruct-awq | mm_esc | 360 | 1.49 | 1.57 | 1.92 | 72 | 1.56 | 1.65 | 2.00 |
| gpt-oss-20b | jwt | 360 | 1.00 | 1.02 | 1.30 | 72 | 1.00 | 1.00 | 1.17 |
| gpt-oss-20b | mm | 360 | 1.71 | 1.71 | 2.46 | 72 | 1.92 | 2.04 | 2.88 |
| gpt-oss-20b | mm_esc | 360 | 1.71 | 1.71 | 2.49 | 72 | 1.93 | 2.01 | 2.90 |
| hermes-3-llama-3.1-8b | jwt | 360 | 1.00 | 0.98 | 1.09 | 72 | 1.01 | 1.02 | 1.09 |
| hermes-3-llama-3.1-8b | mm | 360 | 2.29 | 2.32 | 3.08 | 72 | 3.12 | 3.06 | 3.98 |
| hermes-3-llama-3.1-8b | mm_esc | 360 | 2.31 | 2.35 | 3.12 | 72 | 3.14 | 3.05 | 4.00 |
| granite-3.3-8b-instruct | jwt | 360 | 1.00 | 1.01 | 1.36 | 72 | 1.01 | 1.01 | 1.26 |
| granite-3.3-8b-instruct | mm | 360 | 1.81 | 1.80 | 2.81 | 72 | 2.12 | 2.15 | 3.51 |
| granite-3.3-8b-instruct | mm_esc | 360 | 1.84 | 1.82 | 2.84 | 72 | 2.09 | 2.09 | 3.18 |

## Authorisation share of task wall time (ratio of sums, all templates, error-free runs)

| model | mode | t0: auth share | per-call (challenge+prep+verify) | delegation | t0_nolat: auth share | t07: auth share | LLM share (t0) | tool-latency share (t0) |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 76.9% | 22.8% |
| qwen2.5-7b-instruct | jwt | 0.4% | 0.4% | 0.0% | 0.4% | 0.5% | 79.3% | 20.0% |
| qwen2.5-7b-instruct | mm | 54.7% | 35.2% | 19.4% | 56.8% | 57.3% | 34.4% | 10.5% |
| qwen2.5-7b-instruct | mm_esc | 57.4% | 37.0% | 20.3% | 64.4% | 57.7% | 31.1% | 11.0% |
| qwen2.5-72b-instruct-awq | none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 89.0% | 10.9% |
| qwen2.5-72b-instruct-awq | jwt | 0.2% | 0.2% | 0.0% | 0.2% | 0.2% | 89.8% | 9.9% |
| qwen2.5-72b-instruct-awq | mm | 34.7% | 21.4% | 13.3% | 37.2% | 34.5% | 58.5% | 6.5% |
| qwen2.5-72b-instruct-awq | mm_esc | 34.8% | 21.5% | 13.2% | 37.2% | 34.7% | 58.5% | 6.4% |
| gpt-oss-20b | none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 83.8% | 16.0% |
| gpt-oss-20b | jwt | 0.3% | 0.3% | 0.0% | 0.3% | 0.3% | 84.6% | 14.9% |
| gpt-oss-20b | mm | 44.8% | 27.6% | 17.2% | 48.6% | 41.8% | 46.5% | 8.3% |
| gpt-oss-20b | mm_esc | 44.9% | 27.8% | 17.1% | 49.4% | 41.9% | 46.5% | 8.2% |
| hermes-3-llama-3.1-8b | none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 71.1% | 28.5% |
| hermes-3-llama-3.1-8b | jwt | 0.5% | 0.5% | 0.0% | 0.6% | 0.5% | 72.0% | 27.2% |
| hermes-3-llama-3.1-8b | mm | 58.6% | 36.6% | 22.0% | 66.0% | 57.9% | 29.7% | 11.1% |
| hermes-3-llama-3.1-8b | mm_esc | 58.9% | 36.8% | 22.1% | 66.3% | 58.0% | 29.5% | 11.0% |
| granite-3.3-8b-instruct | none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 84.2% | 15.6% |
| granite-3.3-8b-instruct | jwt | 0.3% | 0.3% | 0.0% | 0.3% | 0.3% | 84.8% | 14.8% |
| granite-3.3-8b-instruct | mm | 42.5% | 28.3% | 14.3% | 46.0% | 42.4% | 48.6% | 8.6% |
| granite-3.3-8b-instruct | mm_esc | 42.8% | 28.3% | 14.5% | 46.1% | 42.7% | 48.4% | 8.5% |

## Per-call authorisation cost (single core, RAYON_NUM_THREADS=1; median [p95] ms, all configurations)

| model | mode | caller | calls | prep | verify | challenge RTT | _meta bytes |
|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | jwt | root mandate | 3298 | 0.11 [0.13] | 0.35 [0.40] | 1.56 [2.17] | 841 |
| qwen2.5-7b-instruct | jwt | child mandate | 1483 | 0.11 [0.12] | 0.35 [0.37] | 1.56 [1.96] | 853 |
| qwen2.5-7b-instruct | mm | root mandate | 3191 | 352.51 [365.35] | 94.78 [105.75] | 1.65 [2.38] | 18117 |
| qwen2.5-7b-instruct | mm | child mandate | 1041 | 352.40 [365.42] | 94.84 [105.61] | 1.78 [2.86] | 18117 |
| qwen2.5-7b-instruct | mm_esc | root mandate | 3195 | 354.62 [367.44] | 97.23 [108.28] | 1.67 [2.45] | 18785 |
| qwen2.5-7b-instruct | mm_esc | child mandate | 1041 | 354.56 [367.90] | 97.25 [108.41] | 1.91 [2.86] | 18785 |
| qwen2.5-72b-instruct-awq | jwt | root mandate | 2632 | 0.13 [0.14] | 0.37 [0.40] | 1.79 [2.47] | 838 |
| qwen2.5-72b-instruct-awq | jwt | child mandate | 1563 | 0.11 [0.14] | 0.35 [0.38] | 1.67 [2.47] | 853 |
| qwen2.5-72b-instruct-awq | mm | root mandate | 2632 | 352.25 [353.73] | 94.79 [95.01] | 1.85 [2.52] | 18117 |
| qwen2.5-72b-instruct-awq | mm | child mandate | 1131 | 352.10 [353.53] | 94.79 [95.00] | 2.35 [2.83] | 18117 |
| qwen2.5-72b-instruct-awq | mm_esc | root mandate | 2632 | 354.39 [355.85] | 97.24 [97.47] | 2.12 [2.52] | 18785 |
| qwen2.5-72b-instruct-awq | mm_esc | child mandate | 1131 | 354.22 [355.71] | 97.21 [97.42] | 2.36 [2.84] | 18785 |
| gpt-oss-20b | jwt | root mandate | 2631 | 0.12 [0.14] | 0.36 [0.40] | 1.71 [2.43] | 838 |
| gpt-oss-20b | jwt | child mandate | 1456 | 0.11 [0.13] | 0.36 [0.38] | 1.65 [2.31] | 853 |
| gpt-oss-20b | mm | root mandate | 2632 | 352.59 [365.58] | 94.80 [105.80] | 1.80 [2.55] | 18117 |
| gpt-oss-20b | mm | child mandate | 1117 | 352.46 [366.58] | 94.84 [105.85] | 2.28 [2.87] | 18117 |
| gpt-oss-20b | mm_esc | root mandate | 2630 | 354.69 [367.57] | 97.26 [108.38] | 1.86 [2.53] | 18785 |
| gpt-oss-20b | mm_esc | child mandate | 1119 | 354.55 [367.60] | 97.26 [108.64] | 2.29 [2.89] | 18785 |
| hermes-3-llama-3.1-8b | jwt | root mandate | 2768 | 0.11 [0.13] | 0.35 [0.40] | 1.59 [2.09] | 838 |
| hermes-3-llama-3.1-8b | jwt | child mandate | 1619 | 0.11 [0.12] | 0.35 [0.37] | 1.55 [1.92] | 854 |
| hermes-3-llama-3.1-8b | mm | root mandate | 2758 | 352.31 [353.83] | 94.82 [95.31] | 1.67 [2.23] | 18117 |
| hermes-3-llama-3.1-8b | mm | child mandate | 1195 | 352.23 [353.66] | 94.86 [95.34] | 1.72 [2.86] | 18117 |
| hermes-3-llama-3.1-8b | mm_esc | root mandate | 2749 | 354.42 [355.84] | 97.28 [97.77] | 1.69 [2.32] | 18785 |
| hermes-3-llama-3.1-8b | mm_esc | child mandate | 1202 | 354.37 [355.77] | 97.28 [97.77] | 1.72 [2.85] | 18785 |
| granite-3.3-8b-instruct | jwt | root mandate | 2439 | 0.11 [0.13] | 0.35 [0.40] | 1.60 [2.18] | 841 |
| granite-3.3-8b-instruct | jwt | child mandate | 1012 | 0.11 [0.12] | 0.35 [0.38] | 1.61 [2.29] | 853 |
| granite-3.3-8b-instruct | mm | root mandate | 2441 | 352.18 [353.81] | 94.80 [95.23] | 1.66 [2.24] | 18117 |
| granite-3.3-8b-instruct | mm | child mandate | 765 | 351.97 [353.45] | 94.85 [95.26] | 2.29 [2.83] | 18117 |
| granite-3.3-8b-instruct | mm_esc | root mandate | 2436 | 354.33 [355.80] | 97.26 [97.68] | 1.68 [2.28] | 18785 |
| granite-3.3-8b-instruct | mm_esc | child mandate | 757 | 354.10 [355.58] | 97.24 [97.66] | 2.30 [2.80] | 18785 |

| model | mode | delegations | delegation ms (median) | parent ms | issuer ms | revocations | revoke ms | push to 4 tools ms |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | jwt | 432 | 0.2 | 0.0 | 0.0 | 140 | 0.00 | 3.0 |
| qwen2.5-7b-instruct | mm | 432 | 2455.8 | 2065.9 | 385.3 | 140 | 2.53 | 123.5 |
| qwen2.5-7b-instruct | mm_esc | 432 | 2455.9 | 2066.7 | 385.3 | 140 | 2.73 | 123.5 |
| qwen2.5-72b-instruct-awq | jwt | 432 | 0.2 | 0.0 | 0.0 | 144 | 0.00 | 4.5 |
| qwen2.5-72b-instruct-awq | mm | 432 | 2432.9 | 2045.5 | 385.1 | 144 | 2.54 | 123.3 |
| qwen2.5-72b-instruct-awq | mm_esc | 432 | 2432.7 | 2045.3 | 385.1 | 144 | 2.73 | 123.3 |
| gpt-oss-20b | jwt | 432 | 0.2 | 0.0 | 0.0 | 144 | 0.00 | 3.0 |
| gpt-oss-20b | mm | 432 | 2456.3 | 2066.3 | 385.4 | 144 | 2.53 | 123.5 |
| gpt-oss-20b | mm_esc | 432 | 2455.8 | 2065.5 | 385.3 | 144 | 2.72 | 123.5 |
| hermes-3-llama-3.1-8b | jwt | 432 | 0.2 | 0.0 | 0.0 | 137 | 0.00 | 2.9 |
| hermes-3-llama-3.1-8b | mm | 429 | 2433.8 | 2046.4 | 385.3 | 136 | 2.53 | 123.4 |
| hermes-3-llama-3.1-8b | mm_esc | 431 | 2433.7 | 2046.2 | 385.2 | 137 | 2.73 | 123.4 |
| granite-3.3-8b-instruct | jwt | 316 | 0.2 | 0.0 | 0.0 | 69 | 0.00 | 3.1 |
| granite-3.3-8b-instruct | mm | 316 | 2432.2 | 2045.0 | 384.9 | 65 | 2.52 | 123.4 |
| granite-3.3-8b-instruct | mm_esc | 313 | 2432.0 | 2044.8 | 384.9 | 65 | 2.54 | 123.4 |

## Safety counters and canonicalisation (all configurations)

| model | mode | runs | honest calls | honest calls wrongly rejected | canonical strings compared | client/server mismatches | revoked calls attempted / accepted | beyond-quota calls attempted / accepted | out-of-mandate calls attempted / accepted | wallet refusals | errors | nudged runs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 720 | 4220 | 0 | 4857 | 0 | 254 / 254 | 378 / 378 | 5 / 5 | 0 | 0 | 37 |
| qwen2.5-7b-instruct | jwt | 720 | 4333 | 0 | 4781 | 0 | 147 / 0 | 295 / 0 | 6 / 0 | 0 | 0 | 31 |
| qwen2.5-7b-instruct | mm | 720 | 4232 | 0 | 4686 | 0 | 148 / 0 | 296 / 0 | 10 / 0 | 454 | 0 | 27 |
| qwen2.5-7b-instruct | mm_esc | 720 | 4236 | 0 | 4683 | 0 | 145 / 0 | 295 / 0 | 7 / 0 | 447 | 0 | 25 |
| qwen2.5-72b-instruct-awq | none | 720 | 3763 | 0 | 4216 | 0 | 165 / 165 | 288 / 288 | 0 / 0 | 0 | 0 | 0 |
| qwen2.5-72b-instruct-awq | jwt | 720 | 3763 | 0 | 4195 | 0 | 144 / 0 | 288 / 0 | 0 / 0 | 0 | 0 | 0 |
| qwen2.5-72b-instruct-awq | mm | 720 | 3763 | 0 | 4195 | 0 | 144 / 0 | 288 / 0 | 0 / 0 | 432 | 0 | 0 |
| qwen2.5-72b-instruct-awq | mm_esc | 720 | 3763 | 0 | 4195 | 0 | 144 / 0 | 288 / 0 | 0 / 0 | 432 | 0 | 0 |
| gpt-oss-20b | none | 720 | 3763 | 0 | 4206 | 0 | 174 / 174 | 269 / 269 | 0 / 0 | 0 | 0 | 108 |
| gpt-oss-20b | jwt | 720 | 3748 | 0 | 4087 | 0 | 148 / 0 | 191 / 0 | 0 / 0 | 0 | 0 | 108 |
| gpt-oss-20b | mm | 720 | 3749 | 0 | 4090 | 0 | 147 / 0 | 194 / 0 | 0 / 0 | 341 | 0 | 107 |
| gpt-oss-20b | mm_esc | 720 | 3749 | 0 | 4092 | 0 | 149 / 0 | 194 / 0 | 0 / 0 | 343 | 0 | 105 |
| hermes-3-llama-3.1-8b | none | 720 | 3943 | 0 | 4501 | 0 | 243 / 243 | 315 / 315 | 0 / 0 | 0 | 0 | 305 |
| hermes-3-llama-3.1-8b | jwt | 720 | 3961 | 0 | 4387 | 0 | 138 / 0 | 288 / 0 | 0 / 0 | 0 | 0 | 255 |
| hermes-3-llama-3.1-8b | mm | 720 | 3953 | 0 | 4381 | 0 | 136 / 0 | 292 / 0 | 0 / 0 | 428 | 0 | 250 |
| hermes-3-llama-3.1-8b | mm_esc | 720 | 3951 | 0 | 4379 | 0 | 138 / 0 | 290 / 0 | 0 / 0 | 428 | 0 | 258 |
| granite-3.3-8b-instruct | none | 720 | 3170 | 0 | 3467 | 0 | 90 / 90 | 204 / 204 | 3 / 3 | 0 | 0 | 201 |
| granite-3.3-8b-instruct | jwt | 720 | 3195 | 0 | 3451 | 0 | 79 / 0 | 173 / 0 | 4 / 0 | 0 | 0 | 198 |
| granite-3.3-8b-instruct | mm | 720 | 3206 | 0 | 3466 | 0 | 75 / 0 | 181 / 0 | 4 / 0 | 260 | 0 | 208 |
| granite-3.3-8b-instruct | mm_esc | 720 | 3193 | 0 | 3449 | 0 | 72 / 0 | 182 / 0 | 2 / 0 | 256 | 0 | 206 |

Canonicalisation probe `canonprobe-qwen2.5-7b-instruct-45427.json` (63 adversarial argument objects through the real MCP client and tool server): none: 0 mismatches, 0 rejections of 21; jwt: 0 mismatches, 3 rejections of 21; mm: 0 mismatches, 3 rejections of 21 (rejections = amounts above the root mandate's per-call limit of 1,000 EUR, i.e. correct policy decisions).

## Shared issuer with concurrent revocations (mode mm, temperature 0)

One Authority per worker shared by all its tasks; a background task revokes an unrelated dummy mandate every 2 s and pushes the new public parameters to the 4 tools; publish-then-refresh ordering (the wallet does not present while new parameters are being pushed). Churn rejection = honest call rejected whose presentation was built against an older accumulator version than the one the tool held at verification. Revocation delay = time from the revocation request to the moment no tool accepts presentations against a pre-revocation accumulator: W = 0, installation of the new value on the last tool; W = 2, installation of the 2nd subsequent value.

| model | W | runs | success | per-task-Authority t0 mm success (same tasks) | honest calls | rejected | of which churn | revocations (dummy + task) | achieved rate per worker /s | revoke ms median [p95] | push ms median | lock wait per call ms median [p95] | revocation delay ms median [p95] | dummy pool exhausted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-oss-20b | 0 | 120 | 52.5 [43.6, 61.2] | 94.2 [88.4, 97.1] | 420 | 81 | 81 | 349 + 12 | 0.52 | 103.7 [134.9] | 122.2 | 0.00 [0.0] | 228 [265] | 0 of 5 workers |
| gpt-oss-20b | 2 | 120 | 95.8 [90.6, 98.2] | 94.2 [88.4, 97.1] | 624 | 0 | 0 | 522 + 24 | 0.52 | 100.0 [137.2] | 123.1 | 0.00 [0.0] | 4218 [5933] | 0 of 5 workers |
| qwen2.5-72b-instruct-awq | 0 | 120 | 65.0 [56.1, 72.9] | 87.5 [80.4, 92.3] | 556 | 94 | 94 | 602 + 11 | 0.51 | 114.5 [136.2] | 122.2 | 0.00 [0.0] | 239 [261] | 0 of 5 workers |
| qwen2.5-72b-instruct-awq | 2 | 120 | 88.3 [81.4, 92.9] | 87.5 [80.4, 92.3] | 629 | 0 | 0 | 713 + 24 | 0.52 | 100.9 [138.8] | 122.7 | 0.00 [0.0] | 4221 [5537] | 0 of 5 workers |

## Wallet in a separate process (IPC over a multiprocessing pipe, same core; mode mm, temperature 0)

| model | runs | success | calls | prep ms median (IPC) | of which inside the wallet process | IPC overhead per call median [p95] ms | in-process prep median (campaign t0 mm) | task wall median IPC / in-process ms |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | 120 | 48.3 [39.6, 57.2] | 735 | 352.6 | 352.5 | 0.14 [0.16] | 352.5 | 6469 / 6482 |

## Micro-benchmark of the primitives on the compute node (median ms; `bench`, outside the agent loop)

| file | threads (RAYON_NUM_THREADS) | cores | MM prep (root) | MM verify | MM_esc prep | MM_esc verify | MM prep (child) | delegation parent+issuer | revoke (mandates) | verifier update | presentation bytes (raw; base64 in _meta) | JWT prep | JWT verify |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bench-1thread-qwen2.5-7b-instruct-45427.json | 1 | 1 | 352.7 | 94.5 | 355.0 | 97.0 | 352.6 | 2069+386 | 6.3 (10) | 23.9 | 13536 | 0.043 | 0.247 |
| bench-16threads-qwen2.5-7b-instruct-45427.json | 16 | 10 | 121.1 | 63.4 | 123.5 | 64.9 | 121.9 | 561+172 | 6.4 (7) | 5.4 | 13536 | 0.044 | 0.249 |

## Design (what changed with respect to E4 v2)

* **Code and provenance.** `code/e4v21/e4v21.py` is a copy of `code/e4v2/e4v2.py` (kept unchanged) adapted to the mmpy v2.1 API. mmpy was rebuilt on the Hedy login node (maturin 1.16, release, into `agentenv`) from `code/src`, `code/mmpy`, `Cargo.toml`, `Cargo.lock` copied from the local tree at commit `060ced918f45da9e26641d9da8870f59612dfc36` (HEAD moved to `690add5a` during the session with a paper-only commit; `git diff 060ced9 690add5 -- code` is empty). sha256 of the built shared object `mmpy.cpython-312-x86_64-linux-gnu.so`: `1ace11bfcc7238df93b96d77a7c5960d995e455bddebb1f7b0a17ed03fb34d25`. Both, plus the sha256 of `e4v21.py`, are stored under `provenance` in every result JSON (campaign, shared-issuer, bench, canonicalisation probe).
* **mmpy v2.1 / strict tools.** `Authority(seed, uid=42, budget=100000, k=100000, exp=2^39, grace=W)`; `delegate(parent, classes, budget, k, exp, epoch)` carves k counters from the parent's free interval; `present(..., cur="EUR")` raises `ValueError` when the honest wallet refuses (stale or revoked mandate, quota exhausted, amount above budget) and the call is then sent without authorisation. Each tool holds a strict `Verifier(pp, tool, require_escrow, seed, epoch=1, now=T, tol=300, debug=False)`: the hidden `challenge` MCP tool (argument: tool name) returns `v.challenge()` (single-use nonce issued by the verifier itself) and the tool's clock `t`, the client presents with the tool's `t`, the tool calls `set_clock(1, now)` before `verify`; errors are the uniform `"rejected"`. JWT: the tool's own nonce store, `iat` = the tool's `t`.
* **Canonicalisation from the raw arguments.** The client parses the model's JSON arguments and sends that object unchanged (no type conversion, amounts in EUR as written by the model); it signs RFC 8785 JCS of `{"name", "arguments", "currency": "EUR"}`. The tool server replaces FastMCP's `tools/call` handler by a low-level handler (`validate_input=False`) that receives `params.arguments` as decoded from the JSON-RPC body (no pydantic coercion, no schema validation) and canonicalises it as received; both sides derive the amount in cents with the same function from the raw value. Validity (required keys, numeric types) is checked on a coerced copy only. The client's canonical hash travels in `_meta.dbg` for diagnosis only (never used to authorise); the tool reports whether its own canonical string matches. Adversarial probe (`canonprobe`): 21 argument objects (null values, extra/nested keys, int vs float, `1e2`, `0.1+0.2`, `-0.0`, 2^53+1, 1e21, numeric strings, non-ASCII/combining/emoji/control characters, keys needing UTF-16 ordering) through the real MCP client and server in modes none/jwt/mm.
* **Replication control.** Configuration `t0_rep` = `t0` with identical settings (temperature 0, seed 0, same latency draws), run in the same job; six configurations per (task, mode): t0, t0_rep, t0_nolat, t07_s1..s3.
* **Template e (binding quota), 24 tasks.** The main agent pays the cheapest flight, then must call `delegate_hotel_survey` for five cities; the sub-agent's child mandate has classes {search}, budget 0 and quota k = 3 (MM: 3 counters carved from the root's interval, per tool and epoch; JWT: `k` in the signed child mandate and its ancestors' k in `anc_k`, counted per tree by each tool). The quota is not mentioned to the model. Success = flight paid exactly, no other payment, no call beyond the quota accepted, and the main agent's final answer reports FAILED (partial failure). Under `none` the survey completes, so the correct outcome is impossible by construction.
* **Shared issuer with concurrent revocations** (Qwen2.5-72B-AWQ and gpt-oss-20b, mode mm, temperature 0, planned 12 tasks per template; all 120 tasks were run, see below): one `Authority` per worker shared by every task of the worker (each task uses the root mandate and delegates its sub-agents from it), 200 unrelated dummy mandates per worker delegated before the tasks (k = 1, classes {search}), and an asyncio task that revokes one dummy every 2 s on a fixed schedule and pushes the new public parameters (with the grace window) to the 4 tools. Ordering = publish-then-refresh: a publication lock is held from `revoke` to the last tool's installation and the wallet takes it before presenting, so a presentation is never built against parameters that tools do not have yet; the remaining race is a presentation built against version v and verified after the tool installed v+1, which W = 0 rejects and W = 2 accepts. Two runs per model: W = 0 and W = 2. No retry on rejection (the agent sees the same uniform rejection as any refusal).
* Unchanged from v2: tasks a-d, prompts, nudge rule (at most 2), tool latency model (lognormal, median 120 ms, sigma 0.5), W = 5 workers with one agent core and one tool-server core each, RAYON_NUM_THREADS = 1, vLLM 0.33.0 with the same parsers and chat templates, `--rerun-errors` for units that end with a harness error.
## Jobs and compute (MesoNET Hedy, account m26297, partition gpu, 1 H100 80GB + 16 cores per job)

| job | purpose | elapsed |
|---|---|---|
| 45425, 45426 | first submission (Qwen-7B, Qwen-72B), cancelled after 4 min: NFS quota pre-allocation (see problems) | 4:20 each |
| 45427 | Qwen2.5-7B campaign (2,880 runs) + single-core and 16-thread bench + canonicalisation probe | 59:32 |
| 45428 | Qwen2.5-72B-AWQ campaign | 1:30:51 |
| 45429 | gpt-oss-20b campaign | 1:11:33 |
| 45430 | Hermes-3-Llama-3.1-8B campaign | 48:47 |
| 45431 | Granite-3.3-8B campaign | 1:02:13 |
| 45432 | shared issuer, Qwen-72B, W = 0 (kept) and W = 2 (excluded: port collision) | 26:08 |
| 45433 | shared issuer, gpt-oss, W = 0 (excluded: port collision) and W = 2 (kept) | 22:57 |
| 45444 | IPC wallet, Qwen-7B, mm, t0 | 4:39 |
| 48495 | shared issuer, gpt-oss, W = 0 (re-run) | 12:23 |
| 48496 | shared issuer, Qwen-72B, W = 2 (re-run), failed at start-up: tool-server port taken | 2:23 |
| 48510 | shared issuer, Qwen-72B, W = 2 (re-run) | 16:02 |

Total: 25,568 s = 7.1 GPU-hours (sacct ElapsedRaw, all jobs above), of the 40 GPU-hour budget. No job left running; Hedy home quota 409 GB at the end (unchanged from the start); no model downloaded. Harness self-tests (oracle policy) and the build ran on the login node.

## Problems met and how they were handled

* **NFS quota pre-allocation.** With the result/log files on the NFS home (as in v2), the first two jobs had pushed the quota from 409 to 445 GB within 4 minutes (31 GB charged for 1.1 MB of data: the server pre-allocates ~1 GB per file held open for appending). Both jobs were cancelled (45425-45426, partial data discarded) and the job script now writes everything to the node-local `/tmp` and copies results and logs to `$HOME` in the EXIT trap (also on failure). Quota stayed at 409-411 GB for the rest of the campaign with up to 4 jobs at once.
* **Port collision between two concurrent jobs on the same node.** The tool-server port range was derived from the job id (`20000 + (id % 200) * 100`), and the shared-issuer runs added `50 * W`; jobs 45432 (W = 2: ports 23300-23344) and 45433 (W = 0: the same ports) ran at the same time on m-gpu01, so some workers' calls reached the other job's tool servers (verifiers holding the other issuer's parameters). Symptom: 51-83 honest calls per run rejected with no accumulator-version difference, starting at the first call of the first task. Those two runs are excluded (kept in `results/e4v21/excluded_port_collision/` for the record) and re-run (48495, 48510). Fixes: the orchestrator now checks that each port is answered by its own tool-server process (pid in `/health`), and ports are `20000 + (id % 40) * 300` (disjoint per job and below the Linux ephemeral range: the first re-run, 48496, failed at start-up because port 48900, in the ephemeral range under an intermediate formula, was taken; the pid check made it fail loudly instead of silently). The five campaigns and the two kept shared runs used non-overlapping ranges (checked from the job ids and start/end times).
* **Low-level handler and MCP output validation.** Replacing FastMCP's `tools/call` handler by the raw handler made the SDK validate the stub tools' declared output schema ("outputSchema defined but no structured output returned"); fixed with `structured_output=False` on the declared tools (caught by the canonicalisation probe before any GPU job).
* **Wallet overflow.** An amount of 1e21 EUR made `Authority.present` raise `OverflowError` (u64) instead of `ValueError`; the wallet now treats both as a refusal (caught by the probe; never triggered by a model).
* **`LIMIT` default in the shared-issuer branch.** The job script's global `LIMIT=0` overrode the intended 12 tasks per template, so the shared-issuer runs used all 120 tasks (24 per template) instead of 60; the dummy pool (200 per worker) was large enough (never exhausted) and the larger sample is kept.
* **Code versions.** `e4v21.py` as run is archived in `results/e4v21/logs/code-as-run/` (campaign sha256 487f16a4..., IPC variant 4381c7ce..., fixed variant 3ce67f88..., identical to the final `code/e4v21/e4v21.py` except one table-header label of the analysis); the differences are additive (IPC switch behind `E4_IPC_WALLET`, pid check, analysis code), and each JSON stores the sha256 of the file it was produced with.

## Limitations

* Authorisation remains expensive in this setting: a single-core MM presentation costs ~0.45 s (prove + verify) and a delegation ~2.5 s, i.e. 35-59 % of task wall time and a median slowdown of 1.5-2.3x with 120 ms tool latency (1.6-3.1x without), against <= 0.5 % and 1.00x for JWT.
* The shared-issuer configuration rejects ~17-19 % of honest calls with W = 0 at one revocation every 2 s, because a presentation takes ~0.35 s to build and is verified ~0.1 s later; W = 2 removes the rejections but keeps a revoked mandate usable (by a dishonest holder; the honest wallet refuses immediately) for about W x the inter-revocation interval (4.2 s median here). The rate (0.5 revocations/s per worker) and the publish-then-refresh ordering are choices of this experiment; the opposite ordering (wallets refresh before tools install) would cause rejections that no grace window can absorb, and was not run. Agents do not retry after a rejection.
* `Authority` in the harness plays issuer, escrow, principal and every agent's wallet; in the shared configuration its `revoke` refreshes ~220 witnesses (100-115 ms) on the agent's core. A deployment would spread this work over the wallets.
* Template e enforcement is complete (0 calls beyond quota accepted under jwt/mm/mm_esc), but its success criterion also requires the agent to report the partial failure; Hermes-3 (and Granite in part) report DONE with 3 of 5 cities. Template e's quota is per tool and epoch (MM: interval carved at delegation; JWT: per-tree counters held by each tool, which need tool-side state and linkability, unlike MM).
* Replication control: Qwen-72B is deterministic at temperature 0 under this load (0 discordant units, 100 % identical transcripts); for the other models 1-7 of 120 units change outcome between identical runs, the same order as the mode-vs-none discordances; equivalence claims are therefore limited by this noise and by 72 clusters per model (CI half-widths 1-5 pp).
* Canonicalisation: client and tool share one JCS implementation and one MCP SDK version (1.30.0); 0 mismatches does not cover other SDKs or JSON parsers (e.g. integers above 2^53 are kept exact by this JCS implementation, whereas RFC 8785 serialises them as IEEE doubles).
* Tool latency simulated; synthetic deterministic world; template-generated tasks; 5 agents share one vLLM instance (LLM times are those of a lightly loaded server).
* Mistral-Small-3.2 not included (weights removed; a ~48 GB re-download would exceed the disk budget).

## Files

* Code: `code/e4v21/e4v21.py` (harness, tool servers, wallets, bench, canonicalisation probe, analysis), `code/e4v21/hedy_e4v21.sbatch`, `code/e4v21/templates/` (Hermes-3 and Granite chat templates, unchanged from v2), `code/e4v21/key_results_v21.md` and `tail_v21.md` (text blocks of this summary, including the design section). `code/e4v2/` unchanged.
* Results: `code/results/e4v21/e4v21_<model>.json` (5 campaigns: every run, every call, provenance, summary), `e4v21_shared_<model>_W{0,2}.json` (4 shared-issuer runs, with per-worker revocation logs), `e4v21_ipc_qwen2.5-7b-instruct.json`, `bench-1thread-*.json`, `bench-16threads-*.json`, `canonprobe-*.json`, `cores-*`, `lscpu-*`, `gpu-*`, `vllm-cmd-*`; `excluded_port_collision/` (2 excluded runs); `logs/` (Slurm outputs, orchestrator and worker logs, vLLM logs, gzipped LLM-visible transcripts in `parts-*`, aborted jobs, code as run).
* Regenerate this file: `cd code && python3 e4v21/e4v21.py analyse --inputs results/e4v21/e4v21_{qwen2.5-7b-instruct,qwen2.5-72b-instruct-awq,gpt-oss-20b,hermes-3-llama-3.1-8b,granite-3.3-8b-instruct}.json --shared results/e4v21/e4v21_shared_*.json --ipc results/e4v21/e4v21_ipc_qwen2.5-7b-instruct.json --canonprobe results/e4v21/canonprobe-*.json --bench results/e4v21/bench-1thread-*.json results/e4v21/bench-16threads-*.json --boot 10000 --extra-md e4v21/key_results_v21.md --tail-md e4v21/tail_v21.md --md results/e4v21_summary.md`.

