# E4 v2 -- real LLM agents, MCP tools, authorisation modes (summary)

Generated 2026-11-13 12:51 from 5 result files. Success rates in % with Wilson 95% CI; t0 = temperature 0 with tool latency (1 run), t0_nolat = temperature 0 without tool latency, t07 = temperature 0.7, 3 seeds pooled. Templates: a = flight+hotel, b = delegated hotel booking, c = revocation (success = safe failure), d = search-heavy (11 calls).

## Key results

* **Scale.** 5 models x 96 tasks x 4 modes x 5 configurations = 9,600 task runs (1,920 per model, every unit completed; 314 units re-run once after harness/transport errors, listed under `reruns` in the JSONs), 52,572 honest MCP tool calls, 4,548 sub-agent delegations (all modes), 2,108 revocations; 4.3 GPU-hours on Hedy.
* **Honest calls wrongly rejected: 0** in every mode (jwt 13,143, mm 13,165, mm_esc 13,138 honest calls).
* **Revocation (template c).** Every call made by a revoked sub-agent was rejected under jwt (547/547), mm (547/547) and mm_esc (550/550), and accepted without authorisation (none: 772/772 accepted, 343 of 600 runs completed every payment after the revocation). Safe-failure rate (temperature 0.7, 72 runs per cell): Qwen-7B 0 % (none) vs 55.6 % (jwt, mm, mm_esc); Qwen-72B 0 % vs 98.6 %; gpt-oss 0 % vs 97.2-98.6 %; Hermes-3 0 % vs 41.7-50.0 %; Granite 0 % vs 19.4-26.4 % (every none-vs-authorised paired comparison: exact McNemar p <= 1.2e-4). The remaining failures in authorised modes are model behaviour, not leaks: agents that claim DONE after a rejection (86-92 of 600 runs per mode), wrong payments, or final answers with neither DONE nor FAILED.
* **Out-of-mandate calls** (the main agent paying more than the root mandate's per-call limit of 1,000 EUR, e.g. flight + hotel in one payment; Qwen-7B and Granite, template d): 10/10 accepted without authorisation, 0/21 accepted under jwt/mm/mm_esc (MM: the honest wallet cannot build the range proof, 13 wallet refusals, the call is sent without authorisation and rejected; JWT: rejected by the tool). Sub-agents never exceeded their delegated budget.
* **Task success on the honest templates (a, b, d) does not depend on the mode** (temperature 0.7, 216 paired units per model): none / jwt / mm / mm_esc = Qwen-7B 37.5 / 38.4 / 36.6 / 38.0 %; Qwen-72B 79.2 / 79.6 / 79.6 / 79.6 %; gpt-oss 93.1 / 90.7 / 93.5 / 92.6 %; Hermes-3 19.9 / 20.8 / 20.8 / 20.4 %; Granite 23.1 / 23.1 / 19.9 / 21.8 %; no paired comparison is significant (smallest p = 0.09, Granite none vs mm, 10 vs 3 discordant pairs), and the number of discordant pairs is of the order of the run-to-run nondeterminism measured by the control (same mode run twice). This is now an empirical statement backed by paired tests, not a property of the design: the prompts are identical, but authorisation decisions (revocation, budgets) do change outcomes where they should.
* **Per-call cost, single core (RAYON_NUM_THREADS=1, Xeon Platinum 8462Y+):** MM prove 357 ms, verify 95 ms (mm_esc 360 / 97.5 ms), `_meta` 17.9 kB (18.5 kB with escrow), challenge round trip 3 ms; JWT 0.11 ms + 0.36 ms, 0.8 kB. Delegation 2.30 s (parent 1.93 s + issuer 0.37 s); revocation 2.8 ms + 72 ms to push the new parameters to 4 tools. The same primitives with 16 threads: 122 + 63 ms (v1's 154 ms per call was multi-threaded).
* **Overhead share of task wall time (temperature 0, lognormal tool latency, ratio of sums):** mm 52 % (Qwen-7B), 38 % (Qwen-72B), 45 % (gpt-oss), 58 % (Hermes-3), 47 % (Granite), of which 26-42 points are per-call proofs and 12-17 points delegation; jwt 0.3-0.8 %. Without tool latency (measured t0_nolat runs): mm 41-68 %, jwt 0.4-1.1 %. Tool latency is 13-31 % of wall time without authorisation; LLM inference per task 1.4-5.0 s (median).

## Models and serving configuration

| model | weights | vLLM tool parser | chat template | extra flags | workers |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | Qwen2.5-7B-Instruct | hermes | model default (tokenizer_config.json) | - | 5 |
| qwen2.5-72b-instruct-awq | Qwen2.5-72B-Instruct-AWQ | hermes | model default (tokenizer_config.json) | - | 5 |
| gpt-oss-20b | gpt-oss-20b | openai | model default (chat_template.jinja, harmony) | - | 5 |
| hermes-3-llama-3.1-8b | Hermes-3-Llama-3.1-8B | hermes | /home/yulameur1/masked-mandates-95/code/e4v2/templates/hermes3_tool_use.jinja | - | 5 |
| granite-3.3-8b-instruct | granite-3.3-8b-instruct | granite | /home/yulameur1/masked-mandates-95/code/e4v2/templates/granite33_tools.jinja | - | 5 |

## Task success (temperature 0, tool latency on)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 45.8 [27.9, 64.9] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | b | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | d | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 16.7 [6.7, 35.9] (n=24) |
| qwen2.5-7b-instruct | all | 27.1 [19.2, 36.7] (n=96) | 40.6 [31.3, 50.6] (n=96) | 40.6 [31.3, 50.6] (n=96) | 41.7 [32.3, 51.7] (n=96) |
| qwen2.5-72b-instruct-awq | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| qwen2.5-72b-instruct-awq | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | d | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | all | 66.7 [56.8, 75.3] (n=96) | 91.7 [84.4, 95.7] (n=96) | 91.7 [84.4, 95.7] (n=96) | 91.7 [84.4, 95.7] (n=96) |
| gpt-oss-20b | a | 83.3 [64.1, 93.3] (n=24) | 87.5 [69.0, 95.7] (n=24) | 95.8 [79.8, 99.3] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| gpt-oss-20b | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | d | 91.7 [74.2, 97.7] (n=24) | 75.0 [55.1, 88.0] (n=24) | 91.7 [74.2, 97.7] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | all | 68.8 [58.9, 77.1] (n=96) | 90.6 [83.1, 95.0] (n=96) | 96.9 [91.2, 98.9] (n=96) | 94.8 [88.4, 97.8] (n=96) |
| hermes-3-llama-3.1-8b | a | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | b | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 13.8] (n=24) | 54.2 [35.1, 72.1] (n=24) | 58.3 [38.8, 75.5] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| hermes-3-llama-3.1-8b | d | 20.8 [9.2, 40.5] (n=24) | 25.0 [12.0, 44.9] (n=24) | 25.0 [12.0, 44.9] (n=24) | 25.0 [12.0, 44.9] (n=24) |
| hermes-3-llama-3.1-8b | all | 17.7 [11.4, 26.5] (n=96) | 32.3 [23.8, 42.2] (n=96) | 34.4 [25.6, 44.3] (n=96) | 31.2 [22.9, 41.1] (n=96) |
| granite-3.3-8b-instruct | a | 37.5 [21.2, 57.3] (n=24) | 41.7 [24.5, 61.2] (n=24) | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| granite-3.3-8b-instruct | b | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 37.5 [21.2, 57.3] (n=24) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | d | 4.2 [0.7, 20.2] (n=24) | 8.3 [2.3, 25.8] (n=24) | 8.3 [2.3, 25.8] (n=24) | 8.3 [2.3, 25.8] (n=24) |
| granite-3.3-8b-instruct | all | 20.8 [13.9, 30.0] (n=96) | 26.0 [18.3, 35.6] (n=96) | 24.0 [16.5, 33.4] (n=96) | 21.9 [14.8, 31.1] (n=96) |

## Task success (temperature 0.7, 3 seeds)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 45.8 [34.8, 57.3] (n=72) | 48.6 [37.4, 59.9] (n=72) | 45.8 [34.8, 57.3] (n=72) | 48.6 [37.4, 59.9] (n=72) |
| qwen2.5-7b-instruct | b | 50.0 [38.7, 61.3] (n=72) | 50.0 [38.7, 61.3] (n=72) | 50.0 [38.7, 61.3] (n=72) | 51.4 [40.1, 62.6] (n=72) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 5.1] (n=72) | 55.6 [44.1, 66.5] (n=72) | 55.6 [44.1, 66.5] (n=72) | 55.6 [44.1, 66.5] (n=72) |
| qwen2.5-7b-instruct | d | 16.7 [9.8, 26.9] (n=72) | 16.7 [9.8, 26.9] (n=72) | 13.9 [7.7, 23.7] (n=72) | 13.9 [7.7, 23.7] (n=72) |
| qwen2.5-7b-instruct | all | 28.1 [23.2, 33.6] (n=288) | 42.7 [37.1, 48.5] (n=288) | 41.3 [35.8, 47.1] (n=288) | 42.4 [36.8, 48.1] (n=288) |
| qwen2.5-72b-instruct-awq | a | 69.4 [58.0, 78.9] (n=72) | 70.8 [59.5, 80.1] (n=72) | 70.8 [59.5, 80.1] (n=72) | 70.8 [59.5, 80.1] (n=72) |
| qwen2.5-72b-instruct-awq | b | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 5.1] (n=72) | 98.6 [92.5, 99.8] (n=72) | 98.6 [92.5, 99.8] (n=72) | 98.6 [92.5, 99.8] (n=72) |
| qwen2.5-72b-instruct-awq | d | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) | 68.1 [56.6, 77.7] (n=72) |
| qwen2.5-72b-instruct-awq | all | 59.4 [53.6, 64.9] (n=288) | 84.4 [79.7, 88.1] (n=288) | 84.4 [79.7, 88.1] (n=288) | 84.4 [79.7, 88.1] (n=288) |
| gpt-oss-20b | a | 97.2 [90.4, 99.2] (n=72) | 93.1 [84.8, 97.0] (n=72) | 95.8 [88.5, 98.6] (n=72) | 93.1 [84.8, 97.0] (n=72) |
| gpt-oss-20b | b | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) | 100.0 [94.9, 100.0] (n=72) |
| gpt-oss-20b | c | 0.0 [0.0, 5.1] (n=72) | 97.2 [90.4, 99.2] (n=72) | 98.6 [92.5, 99.8] (n=72) | 97.2 [90.4, 99.2] (n=72) |
| gpt-oss-20b | d | 81.9 [71.5, 89.1] (n=72) | 79.2 [68.4, 86.9] (n=72) | 84.7 [74.7, 91.2] (n=72) | 84.7 [74.7, 91.2] (n=72) |
| gpt-oss-20b | all | 69.8 [64.3, 74.8] (n=288) | 92.4 [88.7, 94.9] (n=288) | 94.8 [91.6, 96.8] (n=288) | 93.8 [90.3, 96.0] (n=288) |
| hermes-3-llama-3.1-8b | a | 26.4 [17.6, 37.6] (n=72) | 27.8 [18.8, 39.0] (n=72) | 26.4 [17.6, 37.6] (n=72) | 26.4 [17.6, 37.6] (n=72) |
| hermes-3-llama-3.1-8b | b | 16.7 [9.8, 26.9] (n=72) | 19.4 [12.0, 30.0] (n=72) | 19.4 [12.0, 30.0] (n=72) | 16.7 [9.8, 26.9] (n=72) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 5.1] (n=72) | 41.7 [31.0, 53.2] (n=72) | 50.0 [38.7, 61.3] (n=72) | 47.2 [36.1, 58.6] (n=72) |
| hermes-3-llama-3.1-8b | d | 16.7 [9.8, 26.9] (n=72) | 15.3 [8.8, 25.3] (n=72) | 16.7 [9.8, 26.9] (n=72) | 18.1 [10.9, 28.5] (n=72) |
| hermes-3-llama-3.1-8b | all | 14.9 [11.3, 19.5] (n=288) | 26.0 [21.3, 31.4] (n=288) | 28.1 [23.2, 33.6] (n=288) | 27.1 [22.3, 32.5] (n=288) |
| granite-3.3-8b-instruct | a | 30.6 [21.1, 42.0] (n=72) | 30.6 [21.1, 42.0] (n=72) | 26.4 [17.6, 37.6] (n=72) | 26.4 [17.6, 37.6] (n=72) |
| granite-3.3-8b-instruct | b | 29.2 [19.9, 40.5] (n=72) | 29.2 [19.9, 40.5] (n=72) | 25.0 [16.4, 36.1] (n=72) | 29.2 [19.9, 40.5] (n=72) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 5.1] (n=72) | 22.2 [14.2, 33.1] (n=72) | 19.4 [12.0, 30.0] (n=72) | 26.4 [17.6, 37.6] (n=72) |
| granite-3.3-8b-instruct | d | 9.7 [4.8, 18.7] (n=72) | 9.7 [4.8, 18.7] (n=72) | 8.3 [3.9, 17.0] (n=72) | 9.7 [4.8, 18.7] (n=72) |
| granite-3.3-8b-instruct | all | 17.4 [13.4, 22.2] (n=288) | 22.9 [18.4, 28.1] (n=288) | 19.8 [15.6, 24.8] (n=288) | 22.9 [18.4, 28.1] (n=288) |

## Task success (temperature 0, zero tool latency)

| model | template | none | jwt | mm | mm_esc |
|---|---|---|---|---|---|
| qwen2.5-7b-instruct | a | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | b | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) | 50.0 [31.4, 68.6] (n=24) |
| qwen2.5-7b-instruct | d | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| qwen2.5-7b-instruct | all | 28.1 [20.1, 37.8] (n=96) | 40.6 [31.3, 50.6] (n=96) | 40.6 [31.3, 50.6] (n=96) | 40.6 [31.3, 50.6] (n=96) |
| qwen2.5-72b-instruct-awq | a | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) | 91.7 [74.2, 97.7] (n=24) |
| qwen2.5-72b-instruct-awq | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| qwen2.5-72b-instruct-awq | d | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) | 75.0 [55.1, 88.0] (n=24) |
| qwen2.5-72b-instruct-awq | all | 66.7 [56.8, 75.3] (n=96) | 91.7 [84.4, 95.7] (n=96) | 91.7 [84.4, 95.7] (n=96) | 91.7 [84.4, 95.7] (n=96) |
| gpt-oss-20b | a | 87.5 [69.0, 95.7] (n=24) | 95.8 [79.8, 99.3] (n=24) | 87.5 [69.0, 95.7] (n=24) | 87.5 [69.0, 95.7] (n=24) |
| gpt-oss-20b | b | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | c | 0.0 [0.0, 13.8] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) | 100.0 [86.2, 100.0] (n=24) |
| gpt-oss-20b | d | 87.5 [69.0, 95.7] (n=24) | 83.3 [64.1, 93.3] (n=24) | 87.5 [69.0, 95.7] (n=24) | 83.3 [64.1, 93.3] (n=24) |
| gpt-oss-20b | all | 68.8 [58.9, 77.1] (n=96) | 94.8 [88.4, 97.8] (n=96) | 93.8 [87.0, 97.1] (n=96) | 92.7 [85.7, 96.4] (n=96) |
| hermes-3-llama-3.1-8b | a | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) | 20.8 [9.2, 40.5] (n=24) |
| hermes-3-llama-3.1-8b | b | 33.3 [18.0, 53.3] (n=24) | 29.2 [14.9, 49.2] (n=24) | 29.2 [14.9, 49.2] (n=24) | 33.3 [18.0, 53.3] (n=24) |
| hermes-3-llama-3.1-8b | c | 0.0 [0.0, 13.8] (n=24) | 50.0 [31.4, 68.6] (n=24) | 58.3 [38.8, 75.5] (n=24) | 58.3 [38.8, 75.5] (n=24) |
| hermes-3-llama-3.1-8b | d | 20.8 [9.2, 40.5] (n=24) | 25.0 [12.0, 44.9] (n=24) | 25.0 [12.0, 44.9] (n=24) | 25.0 [12.0, 44.9] (n=24) |
| hermes-3-llama-3.1-8b | all | 18.8 [12.2, 27.7] (n=96) | 31.2 [22.9, 41.1] (n=96) | 33.3 [24.7, 43.2] (n=96) | 34.4 [25.6, 44.3] (n=96) |
| granite-3.3-8b-instruct | a | 33.3 [18.0, 53.3] (n=24) | 37.5 [21.2, 57.3] (n=24) | 41.7 [24.5, 61.2] (n=24) | 29.2 [14.9, 49.2] (n=24) |
| granite-3.3-8b-instruct | b | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) | 41.7 [24.5, 61.2] (n=24) |
| granite-3.3-8b-instruct | c | 0.0 [0.0, 13.8] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | d | 8.3 [2.3, 25.8] (n=24) | 4.2 [0.7, 20.2] (n=24) | 12.5 [4.3, 31.0] (n=24) | 12.5 [4.3, 31.0] (n=24) |
| granite-3.3-8b-instruct | all | 20.8 [13.9, 30.0] (n=96) | 24.0 [16.5, 33.4] (n=96) | 27.1 [19.2, 36.7] (n=96) | 24.0 [16.5, 33.4] (n=96) |

## Paired comparisons between modes (exact McNemar; unit = task x configuration)

| model | group | scope | pair | pairs | only 1st ok | only 2nd ok | p |
|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | t0 | honest_abd | none-jwt | 72 | 0 | 1 | 1 |
| qwen2.5-7b-instruct | t0 | honest_abd | none-mm | 72 | 0 | 1 | 1 |
| qwen2.5-7b-instruct | t0 | honest_abd | none-mm_esc | 72 | 0 | 2 | 0.5 |
| qwen2.5-7b-instruct | t0 | honest_abd | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0 | honest_abd | mm-mm_esc | 72 | 0 | 1 | 1 |
| qwen2.5-7b-instruct | t0 | revocation_c | none-jwt | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0 | revocation_c | none-mm | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0 | revocation_c | none-mm_esc | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0 | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0 | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | honest_abd | none-jwt | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | honest_abd | none-mm | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | honest_abd | none-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | honest_abd | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | honest_abd | mm-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | revocation_c | none-jwt | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0_nolat | revocation_c | none-mm | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0_nolat | revocation_c | none-mm_esc | 24 | 0 | 12 | 0.000488 |
| qwen2.5-7b-instruct | t0_nolat | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t0_nolat | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t07 | honest_abd | none-jwt | 216 | 1 | 3 | 0.625 |
| qwen2.5-7b-instruct | t07 | honest_abd | none-mm | 216 | 3 | 1 | 0.625 |
| qwen2.5-7b-instruct | t07 | honest_abd | none-mm_esc | 216 | 3 | 4 | 1 |
| qwen2.5-7b-instruct | t07 | honest_abd | jwt-mm | 216 | 4 | 0 | 0.125 |
| qwen2.5-7b-instruct | t07 | honest_abd | mm-mm_esc | 216 | 2 | 5 | 0.453 |
| qwen2.5-7b-instruct | t07 | revocation_c | none-jwt | 72 | 0 | 40 | 1.82e-12 |
| qwen2.5-7b-instruct | t07 | revocation_c | none-mm | 72 | 0 | 40 | 1.82e-12 |
| qwen2.5-7b-instruct | t07 | revocation_c | none-mm_esc | 72 | 0 | 40 | 1.82e-12 |
| qwen2.5-7b-instruct | t07 | revocation_c | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-7b-instruct | t07 | revocation_c | mm-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | honest_abd | none-jwt | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | honest_abd | none-mm | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | honest_abd | none-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | honest_abd | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | honest_abd | mm-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | revocation_c | none-jwt | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0 | revocation_c | none-mm | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0 | revocation_c | none-mm_esc | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0 | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0 | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | honest_abd | none-jwt | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | honest_abd | none-mm | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | honest_abd | none-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | honest_abd | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | honest_abd | mm-mm_esc | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | revocation_c | none-jwt | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0_nolat | revocation_c | none-mm | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0_nolat | revocation_c | none-mm_esc | 24 | 0 | 24 | 1.19e-07 |
| qwen2.5-72b-instruct-awq | t0_nolat | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t0_nolat | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t07 | honest_abd | none-jwt | 216 | 0 | 1 | 1 |
| qwen2.5-72b-instruct-awq | t07 | honest_abd | none-mm | 216 | 0 | 1 | 1 |
| qwen2.5-72b-instruct-awq | t07 | honest_abd | none-mm_esc | 216 | 0 | 1 | 1 |
| qwen2.5-72b-instruct-awq | t07 | honest_abd | jwt-mm | 216 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t07 | honest_abd | mm-mm_esc | 216 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t07 | revocation_c | none-jwt | 72 | 0 | 71 | 8.47e-22 |
| qwen2.5-72b-instruct-awq | t07 | revocation_c | none-mm | 72 | 0 | 71 | 8.47e-22 |
| qwen2.5-72b-instruct-awq | t07 | revocation_c | none-mm_esc | 72 | 0 | 71 | 8.47e-22 |
| qwen2.5-72b-instruct-awq | t07 | revocation_c | jwt-mm | 72 | 0 | 0 | 1 |
| qwen2.5-72b-instruct-awq | t07 | revocation_c | mm-mm_esc | 72 | 0 | 0 | 1 |
| gpt-oss-20b | t0 | honest_abd | none-jwt | 72 | 5 | 2 | 0.453 |
| gpt-oss-20b | t0 | honest_abd | none-mm | 72 | 1 | 4 | 0.375 |
| gpt-oss-20b | t0 | honest_abd | none-mm_esc | 72 | 2 | 3 | 1 |
| gpt-oss-20b | t0 | honest_abd | jwt-mm | 72 | 0 | 6 | 0.0312 |
| gpt-oss-20b | t0 | honest_abd | mm-mm_esc | 72 | 2 | 0 | 0.5 |
| gpt-oss-20b | t0 | revocation_c | none-jwt | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0 | revocation_c | none-mm | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0 | revocation_c | none-mm_esc | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0 | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| gpt-oss-20b | t0 | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| gpt-oss-20b | t0_nolat | honest_abd | none-jwt | 72 | 3 | 4 | 1 |
| gpt-oss-20b | t0_nolat | honest_abd | none-mm | 72 | 2 | 2 | 1 |
| gpt-oss-20b | t0_nolat | honest_abd | none-mm_esc | 72 | 4 | 3 | 1 |
| gpt-oss-20b | t0_nolat | honest_abd | jwt-mm | 72 | 3 | 2 | 1 |
| gpt-oss-20b | t0_nolat | honest_abd | mm-mm_esc | 72 | 2 | 1 | 1 |
| gpt-oss-20b | t0_nolat | revocation_c | none-jwt | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0_nolat | revocation_c | none-mm | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0_nolat | revocation_c | none-mm_esc | 24 | 0 | 24 | 1.19e-07 |
| gpt-oss-20b | t0_nolat | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| gpt-oss-20b | t0_nolat | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| gpt-oss-20b | t07 | honest_abd | none-jwt | 216 | 13 | 8 | 0.383 |
| gpt-oss-20b | t07 | honest_abd | none-mm | 216 | 7 | 8 | 1 |
| gpt-oss-20b | t07 | honest_abd | none-mm_esc | 216 | 11 | 10 | 1 |
| gpt-oss-20b | t07 | honest_abd | jwt-mm | 216 | 6 | 12 | 0.238 |
| gpt-oss-20b | t07 | honest_abd | mm-mm_esc | 216 | 12 | 10 | 0.832 |
| gpt-oss-20b | t07 | revocation_c | none-jwt | 72 | 0 | 70 | 1.69e-21 |
| gpt-oss-20b | t07 | revocation_c | none-mm | 72 | 0 | 71 | 8.47e-22 |
| gpt-oss-20b | t07 | revocation_c | none-mm_esc | 72 | 0 | 70 | 1.69e-21 |
| gpt-oss-20b | t07 | revocation_c | jwt-mm | 72 | 1 | 2 | 1 |
| gpt-oss-20b | t07 | revocation_c | mm-mm_esc | 72 | 2 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | honest_abd | none-jwt | 72 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | honest_abd | none-mm | 72 | 0 | 2 | 0.5 |
| hermes-3-llama-3.1-8b | t0 | honest_abd | none-mm_esc | 72 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | honest_abd | jwt-mm | 72 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | honest_abd | mm-mm_esc | 72 | 2 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | revocation_c | none-jwt | 24 | 0 | 13 | 0.000244 |
| hermes-3-llama-3.1-8b | t0 | revocation_c | none-mm | 24 | 0 | 14 | 0.000122 |
| hermes-3-llama-3.1-8b | t0 | revocation_c | none-mm_esc | 24 | 0 | 12 | 0.000488 |
| hermes-3-llama-3.1-8b | t0 | revocation_c | jwt-mm | 24 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0 | revocation_c | mm-mm_esc | 24 | 2 | 0 | 0.5 |
| hermes-3-llama-3.1-8b | t0_nolat | honest_abd | none-jwt | 72 | 1 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0_nolat | honest_abd | none-mm | 72 | 1 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0_nolat | honest_abd | none-mm_esc | 72 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0_nolat | honest_abd | jwt-mm | 72 | 0 | 0 | 1 |
| hermes-3-llama-3.1-8b | t0_nolat | honest_abd | mm-mm_esc | 72 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t0_nolat | revocation_c | none-jwt | 24 | 0 | 12 | 0.000488 |
| hermes-3-llama-3.1-8b | t0_nolat | revocation_c | none-mm | 24 | 0 | 14 | 0.000122 |
| hermes-3-llama-3.1-8b | t0_nolat | revocation_c | none-mm_esc | 24 | 0 | 14 | 0.000122 |
| hermes-3-llama-3.1-8b | t0_nolat | revocation_c | jwt-mm | 24 | 1 | 3 | 0.625 |
| hermes-3-llama-3.1-8b | t0_nolat | revocation_c | mm-mm_esc | 24 | 1 | 1 | 1 |
| hermes-3-llama-3.1-8b | t07 | honest_abd | none-jwt | 216 | 1 | 3 | 0.625 |
| hermes-3-llama-3.1-8b | t07 | honest_abd | none-mm | 216 | 1 | 3 | 0.625 |
| hermes-3-llama-3.1-8b | t07 | honest_abd | none-mm_esc | 216 | 0 | 1 | 1 |
| hermes-3-llama-3.1-8b | t07 | honest_abd | jwt-mm | 216 | 2 | 2 | 1 |
| hermes-3-llama-3.1-8b | t07 | honest_abd | mm-mm_esc | 216 | 3 | 2 | 1 |
| hermes-3-llama-3.1-8b | t07 | revocation_c | none-jwt | 72 | 0 | 30 | 1.86e-09 |
| hermes-3-llama-3.1-8b | t07 | revocation_c | none-mm | 72 | 0 | 36 | 2.91e-11 |
| hermes-3-llama-3.1-8b | t07 | revocation_c | none-mm_esc | 72 | 0 | 34 | 1.16e-10 |
| hermes-3-llama-3.1-8b | t07 | revocation_c | jwt-mm | 72 | 1 | 7 | 0.0703 |
| hermes-3-llama-3.1-8b | t07 | revocation_c | mm-mm_esc | 72 | 4 | 2 | 0.688 |
| granite-3.3-8b-instruct | t0 | honest_abd | none-jwt | 72 | 1 | 3 | 0.625 |
| granite-3.3-8b-instruct | t0 | honest_abd | none-mm | 72 | 1 | 1 | 1 |
| granite-3.3-8b-instruct | t0 | honest_abd | none-mm_esc | 72 | 3 | 1 | 0.625 |
| granite-3.3-8b-instruct | t0 | honest_abd | jwt-mm | 72 | 4 | 2 | 0.688 |
| granite-3.3-8b-instruct | t0 | honest_abd | mm-mm_esc | 72 | 2 | 0 | 0.5 |
| granite-3.3-8b-instruct | t0 | revocation_c | none-jwt | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0 | revocation_c | none-mm | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0 | revocation_c | none-mm_esc | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0 | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| granite-3.3-8b-instruct | t0 | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| granite-3.3-8b-instruct | t0_nolat | honest_abd | none-jwt | 72 | 2 | 2 | 1 |
| granite-3.3-8b-instruct | t0_nolat | honest_abd | none-mm | 72 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0_nolat | honest_abd | none-mm_esc | 72 | 2 | 2 | 1 |
| granite-3.3-8b-instruct | t0_nolat | honest_abd | jwt-mm | 72 | 2 | 5 | 0.453 |
| granite-3.3-8b-instruct | t0_nolat | honest_abd | mm-mm_esc | 72 | 4 | 1 | 0.375 |
| granite-3.3-8b-instruct | t0_nolat | revocation_c | none-jwt | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0_nolat | revocation_c | none-mm | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0_nolat | revocation_c | none-mm_esc | 24 | 0 | 3 | 0.25 |
| granite-3.3-8b-instruct | t0_nolat | revocation_c | jwt-mm | 24 | 0 | 0 | 1 |
| granite-3.3-8b-instruct | t0_nolat | revocation_c | mm-mm_esc | 24 | 0 | 0 | 1 |
| granite-3.3-8b-instruct | t07 | honest_abd | none-jwt | 216 | 10 | 10 | 1 |
| granite-3.3-8b-instruct | t07 | honest_abd | none-mm | 216 | 10 | 3 | 0.0923 |
| granite-3.3-8b-instruct | t07 | honest_abd | none-mm_esc | 216 | 12 | 9 | 0.664 |
| granite-3.3-8b-instruct | t07 | honest_abd | jwt-mm | 216 | 12 | 5 | 0.143 |
| granite-3.3-8b-instruct | t07 | honest_abd | mm-mm_esc | 216 | 7 | 11 | 0.481 |
| granite-3.3-8b-instruct | t07 | revocation_c | none-jwt | 72 | 0 | 16 | 3.05e-05 |
| granite-3.3-8b-instruct | t07 | revocation_c | none-mm | 72 | 0 | 14 | 0.000122 |
| granite-3.3-8b-instruct | t07 | revocation_c | none-mm_esc | 72 | 0 | 19 | 3.81e-06 |
| granite-3.3-8b-instruct | t07 | revocation_c | jwt-mm | 72 | 5 | 3 | 0.727 |
| granite-3.3-8b-instruct | t07 | revocation_c | mm-mm_esc | 72 | 2 | 7 | 0.18 |

## LLM-visible transcript identity across the four modes (templates a, b, d)

Control: same mode, temperature 0, run twice (with and without tool latency; the model sees identical content), i.e. the run-to-run nondeterminism of vLLM under concurrent batching.

| model | t0 | t0_nolat | t07 | control none | control jwt | control mm | control mm_esc |
|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | 53/72 | 56/72 | 161/216 | 62/72 | 60/72 | 62/72 | 60/72 |
| qwen2.5-72b-instruct-awq | 71/72 | 72/72 | 210/216 | 72/72 | 72/72 | 71/72 | 72/72 |
| gpt-oss-20b | 51/72 | 52/72 | 140/216 | 54/72 | 55/72 | 56/72 | 55/72 |
| hermes-3-llama-3.1-8b | 36/72 | 43/72 | 125/216 | 52/72 | 51/72 | 48/72 | 50/72 |
| granite-3.3-8b-instruct | 24/72 | 23/72 | 56/216 | 35/72 | 29/72 | 41/72 | 32/72 |

## Per-call authorisation cost (single core, RAYON_NUM_THREADS=1; median [p95] ms, all configurations)

| model | mode | caller | calls | prep | prep CPU | verify | verify CPU | challenge RTT | _meta bytes |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | root mandate | 2559 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| qwen2.5-7b-instruct | none | child mandate | 717 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| qwen2.5-7b-instruct | jwt | root mandate | 2586 | 0.11 [0.13] | 0.11 [0.13] | 0.36 [0.40] | 0.36 [0.40] | 2.75 [3.43] | 780 |
| qwen2.5-7b-instruct | jwt | child mandate | 629 | 0.11 [0.12] | 0.11 [0.12] | 0.36 [0.38] | 0.36 [0.38] | 2.80 [3.19] | 798 |
| qwen2.5-7b-instruct | mm | root mandate | 2644 | 358.09 [371.07] | 356.85 [369.50] | 95.16 [106.36] | 94.91 [106.08] | 2.84 [3.61] | 17873 |
| qwen2.5-7b-instruct | mm | child mandate | 629 | 357.96 [371.52] | 356.84 [370.12] | 95.15 [106.70] | 94.89 [106.38] | 3.23 [4.13] | 17873 |
| qwen2.5-7b-instruct | mm_esc | root mandate | 2581 | 360.27 [373.32] | 359.01 [371.79] | 97.59 [108.88] | 97.33 [108.58] | 2.86 [3.71] | 18537 |
| qwen2.5-7b-instruct | mm_esc | child mandate | 632 | 360.15 [374.09] | 358.98 [372.50] | 97.58 [103.71] | 97.30 [103.02] | 3.33 [4.14] | 18537 |
| qwen2.5-72b-instruct-awq | none | root mandate | 1954 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| qwen2.5-72b-instruct-awq | none | child mandate | 720 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| qwen2.5-72b-instruct-awq | jwt | root mandate | 1954 | 0.11 [0.14] | 0.11 [0.13] | 0.36 [0.40] | 0.36 [0.40] | 2.82 [3.37] | 777 |
| qwen2.5-72b-instruct-awq | jwt | child mandate | 700 | 0.11 [0.11] | 0.11 [0.11] | 0.36 [0.37] | 0.36 [0.37] | 2.78 [3.53] | 798 |
| qwen2.5-72b-instruct-awq | mm | root mandate | 1954 | 357.06 [358.63] | 356.37 [357.90] | 95.06 [95.30] | 94.86 [95.07] | 2.86 [3.41] | 17873 |
| qwen2.5-72b-instruct-awq | mm | child mandate | 700 | 356.95 [358.43] | 356.27 [357.80] | 95.01 [95.22] | 94.82 [95.02] | 3.30 [3.79] | 17873 |
| qwen2.5-72b-instruct-awq | mm_esc | root mandate | 1954 | 359.20 [360.78] | 358.48 [359.99] | 97.49 [97.73] | 97.28 [97.51] | 2.95 [3.53] | 18537 |
| qwen2.5-72b-instruct-awq | mm_esc | child mandate | 700 | 359.06 [360.62] | 358.35 [359.97] | 97.44 [97.72] | 97.25 [97.49] | 3.31 [3.76] | 18537 |
| gpt-oss-20b | none | root mandate | 1953 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| gpt-oss-20b | none | child mandate | 720 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| gpt-oss-20b | jwt | root mandate | 1953 | 0.12 [0.14] | 0.12 [0.13] | 0.37 [0.41] | 0.37 [0.40] | 2.91 [3.63] | 777 |
| gpt-oss-20b | jwt | child mandate | 699 | 0.12 [0.13] | 0.11 [0.13] | 0.37 [0.40] | 0.37 [0.39] | 2.92 [3.73] | 798 |
| gpt-oss-20b | mm | root mandate | 1950 | 357.80 [371.19] | 356.92 [370.15] | 95.21 [106.29] | 94.92 [105.95] | 3.02 [3.71] | 17873 |
| gpt-oss-20b | mm | child mandate | 698 | 357.70 [370.97] | 356.81 [369.96] | 95.19 [106.28] | 94.91 [105.98] | 3.49 [4.14] | 17873 |
| gpt-oss-20b | mm_esc | root mandate | 1952 | 359.95 [373.10] | 359.03 [372.10] | 97.65 [108.87] | 97.35 [108.45] | 3.06 [3.73] | 18537 |
| gpt-oss-20b | mm_esc | child mandate | 699 | 359.93 [373.08] | 359.01 [372.10] | 97.63 [100.64] | 97.34 [100.19] | 3.52 [4.19] | 18537 |
| hermes-3-llama-3.1-8b | none | root mandate | 2143 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| hermes-3-llama-3.1-8b | none | child mandate | 828 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| hermes-3-llama-3.1-8b | jwt | root mandate | 2147 | 0.11 [0.13] | 0.11 [0.13] | 0.36 [0.40] | 0.36 [0.40] | 2.77 [3.22] | 777 |
| hermes-3-llama-3.1-8b | jwt | child mandate | 742 | 0.11 [0.12] | 0.11 [0.12] | 0.36 [0.38] | 0.36 [0.38] | 2.78 [3.16] | 790 |
| hermes-3-llama-3.1-8b | mm | root mandate | 2140 | 357.49 [358.98] | 356.53 [358.00] | 95.18 [95.38] | 94.91 [95.11] | 2.85 [3.42] | 17873 |
| hermes-3-llama-3.1-8b | mm | child mandate | 747 | 357.42 [358.83] | 356.46 [357.86] | 95.14 [95.36] | 94.87 [95.09] | 3.14 [4.09] | 17873 |
| hermes-3-llama-3.1-8b | mm_esc | root mandate | 2144 | 359.63 [361.17] | 358.67 [360.18] | 97.61 [97.82] | 97.34 [97.55] | 2.87 [3.52] | 18537 |
| hermes-3-llama-3.1-8b | mm_esc | child mandate | 745 | 359.61 [361.21] | 358.64 [360.21] | 97.57 [97.79] | 97.30 [97.51] | 3.18 [4.10] | 18537 |
| granite-3.3-8b-instruct | none | root mandate | 1839 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| granite-3.3-8b-instruct | none | child mandate | 475 | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0.00 [0.00] | 0 |
| granite-3.3-8b-instruct | jwt | root mandate | 1820 | 0.11 [0.14] | 0.11 [0.13] | 0.37 [0.40] | 0.37 [0.40] | 2.81 [3.42] | 780 |
| granite-3.3-8b-instruct | jwt | child mandate | 468 | 0.12 [0.13] | 0.11 [0.13] | 0.37 [0.40] | 0.37 [0.39] | 2.92 [3.49] | 798 |
| granite-3.3-8b-instruct | mm | root mandate | 1799 | 357.78 [359.69] | 356.57 [358.15] | 95.22 [95.63] | 94.91 [95.10] | 2.87 [3.51] | 17873 |
| granite-3.3-8b-instruct | mm | child mandate | 451 | 357.65 [359.69] | 356.51 [358.02] | 95.18 [95.61] | 94.89 [95.09] | 3.63 [4.14] | 17873 |
| granite-3.3-8b-instruct | mm_esc | root mandate | 1820 | 359.88 [361.81] | 358.68 [360.21] | 97.65 [98.10] | 97.34 [97.55] | 2.92 [3.61] | 18537 |
| granite-3.3-8b-instruct | mm_esc | child mandate | 461 | 359.85 [361.82] | 358.66 [360.34] | 97.63 [98.08] | 97.32 [97.54] | 3.66 [4.10] | 18537 |

| model | mode | delegations | delegation ms (median) | parent ms | issuer ms | revocations | revoke ms | push to 4 tools ms |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | jwt | 240 | 0.2 | 0.0 | 0.0 | 117 | 0.00 | 3.0 |
| qwen2.5-7b-instruct | mm | 240 | 2323.5 | 1953.4 | 365.6 | 117 | 2.78 | 71.6 |
| qwen2.5-7b-instruct | mm_esc | 240 | 2325.0 | 1954.5 | 365.7 | 118 | 2.68 | 71.6 |
| qwen2.5-72b-instruct-awq | jwt | 240 | 0.1 | 0.0 | 0.0 | 120 | 0.00 | 4.5 |
| qwen2.5-72b-instruct-awq | mm | 240 | 2296.8 | 1929.5 | 365.0 | 120 | 2.76 | 71.4 |
| qwen2.5-72b-instruct-awq | mm_esc | 240 | 2296.5 | 1929.2 | 365.0 | 120 | 2.60 | 71.3 |
| gpt-oss-20b | jwt | 239 | 0.2 | 0.0 | 0.0 | 119 | 0.00 | 3.0 |
| gpt-oss-20b | mm | 240 | 2321.8 | 1946.8 | 365.6 | 120 | 2.78 | 71.6 |
| gpt-oss-20b | mm_esc | 240 | 2321.4 | 1947.7 | 365.6 | 120 | 2.61 | 71.6 |
| hermes-3-llama-3.1-8b | jwt | 234 | 0.2 | 0.0 | 0.0 | 113 | 0.00 | 3.0 |
| hermes-3-llama-3.1-8b | mm | 236 | 2299.8 | 1931.9 | 365.5 | 116 | 2.78 | 71.6 |
| hermes-3-llama-3.1-8b | mm_esc | 236 | 2299.0 | 1931.4 | 365.5 | 114 | 2.60 | 71.5 |
| granite-3.3-8b-instruct | jwt | 185 | 0.2 | 0.0 | 0.0 | 55 | 0.00 | 3.2 |
| granite-3.3-8b-instruct | mm | 178 | 2300.2 | 1932.3 | 365.6 | 55 | 2.78 | 71.6 |
| granite-3.3-8b-instruct | mm_esc | 183 | 2300.5 | 1932.4 | 365.6 | 56 | 2.79 | 71.6 |

## Per-task time (temperature 0, lognormal tool latency; medians in ms, shares = ratio of sums)

| model | mode | tasks | calls | LLM inference | tool latency | authorisation | wall | auth share | of which per-call (challenge+prep+verify) | of which delegation | auth share w/o tool latency (counterfactual) | tool-latency share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 96 | 4 | 1444 | 673 | 0 | 2116 | 0.0% | 0.0% | 0.0% | 0.0% | 23.4% |
| qwen2.5-7b-instruct | jwt | 96 | 4 | 1368 | 568 | 16 | 1929 | 0.6% | 0.6% | 0.0% | 0.9% | 24.3% |
| qwen2.5-7b-instruct | mm | 96 | 4 | 1342 | 567 | 4168 | 6050 | 52.2% | 37.4% | 14.7% | 58.2% | 10.4% |
| qwen2.5-7b-instruct | mm_esc | 96 | 4 | 1372 | 564 | 4201 | 6069 | 52.3% | 37.9% | 14.4% | 58.5% | 10.6% |
| qwen2.5-72b-instruct-awq | none | 96 | 5 | 4901 | 672 | 0 | 5563 | 0.0% | 0.0% | 0.0% | 0.0% | 12.8% |
| qwen2.5-72b-instruct-awq | jwt | 96 | 4 | 5022 | 615 | 19 | 5607 | 0.3% | 0.3% | 0.0% | 0.4% | 11.8% |
| qwen2.5-72b-instruct-awq | mm | 96 | 4 | 4957 | 615 | 4111 | 9402 | 37.9% | 26.0% | 11.9% | 40.9% | 7.4% |
| qwen2.5-72b-instruct-awq | mm_esc | 96 | 4 | 4936 | 615 | 4135 | 9422 | 38.1% | 26.2% | 11.8% | 41.1% | 7.4% |
| gpt-oss-20b | none | 96 | 5 | 3206 | 673 | 0 | 3986 | 0.0% | 0.0% | 0.0% | 0.0% | 16.9% |
| gpt-oss-20b | jwt | 96 | 4 | 3277 | 593 | 17 | 3897 | 0.4% | 0.4% | 0.0% | 0.5% | 16.0% |
| gpt-oss-20b | mm | 96 | 4 | 3149 | 592 | 4145 | 7778 | 45.3% | 31.1% | 14.2% | 49.6% | 8.7% |
| gpt-oss-20b | mm_esc | 96 | 5 | 3236 | 593 | 4169 | 7773 | 45.7% | 31.5% | 14.2% | 50.1% | 8.7% |
| hermes-3-llama-3.1-8b | none | 96 | 6 | 1970 | 792 | 0 | 2755 | 0.0% | 0.0% | 0.0% | 0.0% | 30.9% |
| hermes-3-llama-3.1-8b | jwt | 96 | 6 | 1842 | 695 | 19 | 2530 | 0.8% | 0.8% | 0.0% | 1.1% | 29.5% |
| hermes-3-llama-3.1-8b | mm | 96 | 6 | 1864 | 695 | 4124 | 6912 | 58.4% | 41.2% | 17.3% | 66.2% | 11.7% |
| hermes-3-llama-3.1-8b | mm_esc | 96 | 6 | 1883 | 683 | 4147 | 6921 | 60.0% | 42.3% | 17.6% | 68.1% | 11.9% |
| granite-3.3-8b-instruct | none | 96 | 4 | 2446 | 560 | 0 | 3059 | 0.0% | 0.0% | 0.0% | 0.0% | 19.6% |
| granite-3.3-8b-instruct | jwt | 96 | 4 | 2523 | 534 | 14 | 3046 | 0.5% | 0.5% | 0.0% | 0.6% | 18.5% |
| granite-3.3-8b-instruct | mm | 96 | 4 | 2429 | 532 | 3447 | 6588 | 47.2% | 34.2% | 13.0% | 52.4% | 9.9% |
| granite-3.3-8b-instruct | mm_esc | 96 | 4 | 2462 | 524 | 3912 | 6647 | 48.2% | 35.0% | 13.1% | 53.5% | 9.9% |

## Per-task time (temperature 0, zero tool latency; medians in ms, shares = ratio of sums)

| model | mode | tasks | calls | LLM inference | tool latency | authorisation | wall | auth share | of which per-call (challenge+prep+verify) | of which delegation | auth share w/o tool latency (counterfactual) | tool-latency share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 96 | 4 | 1471 | 0 | 0 | 1491 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| qwen2.5-7b-instruct | jwt | 96 | 4 | 1511 | 0 | 16 | 1546 | 0.8% | 0.8% | 0.0% | 0.8% | 0.0% |
| qwen2.5-7b-instruct | mm | 96 | 4 | 1500 | 0 | 4178 | 5348 | 64.1% | 46.0% | 18.0% | 64.1% | 0.0% |
| qwen2.5-7b-instruct | mm_esc | 96 | 4 | 1515 | 0 | 4196 | 5379 | 61.6% | 44.6% | 17.0% | 61.6% | 0.0% |
| qwen2.5-72b-instruct-awq | none | 96 | 5 | 4845 | 0 | 0 | 4860 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| qwen2.5-72b-instruct-awq | jwt | 96 | 4 | 4936 | 0 | 17 | 4970 | 0.4% | 0.4% | 0.0% | 0.4% | 0.0% |
| qwen2.5-72b-instruct-awq | mm | 96 | 4 | 4940 | 0 | 4106 | 8632 | 41.1% | 28.2% | 12.8% | 41.1% | 0.0% |
| qwen2.5-72b-instruct-awq | mm_esc | 96 | 4 | 4889 | 0 | 4136 | 8587 | 41.3% | 28.5% | 12.8% | 41.3% | 0.0% |
| gpt-oss-20b | none | 96 | 6 | 3149 | 0 | 0 | 3162 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| gpt-oss-20b | jwt | 96 | 4 | 3194 | 0 | 17 | 3221 | 0.5% | 0.5% | 0.0% | 0.5% | 0.0% |
| gpt-oss-20b | mm | 96 | 5 | 3179 | 0 | 4150 | 7016 | 49.2% | 33.8% | 15.5% | 49.2% | 0.0% |
| gpt-oss-20b | mm_esc | 96 | 4 | 3099 | 0 | 4178 | 7092 | 50.6% | 34.8% | 15.8% | 50.6% | 0.0% |
| hermes-3-llama-3.1-8b | none | 96 | 6 | 1963 | 0 | 0 | 1982 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| hermes-3-llama-3.1-8b | jwt | 96 | 6 | 1850 | 0 | 19 | 1888 | 1.1% | 1.1% | 0.0% | 1.1% | 0.0% |
| hermes-3-llama-3.1-8b | mm | 96 | 6 | 1863 | 0 | 4126 | 6341 | 67.7% | 47.7% | 20.0% | 67.7% | 0.0% |
| hermes-3-llama-3.1-8b | mm_esc | 96 | 6 | 1852 | 0 | 4146 | 6347 | 67.9% | 47.5% | 20.4% | 67.9% | 0.0% |
| granite-3.3-8b-instruct | none | 96 | 4 | 2421 | 0 | 0 | 2436 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| granite-3.3-8b-instruct | jwt | 96 | 4 | 2501 | 0 | 14 | 2534 | 0.6% | 0.6% | 0.0% | 0.6% | 0.0% |
| granite-3.3-8b-instruct | mm | 96 | 4 | 2572 | 0 | 3883 | 6111 | 53.6% | 38.8% | 14.8% | 53.6% | 0.0% |
| granite-3.3-8b-instruct | mm_esc | 96 | 4 | 2452 | 0 | 3228 | 6358 | 52.6% | 38.2% | 14.4% | 52.6% | 0.0% |

## Per-task time (temperature 0.7; medians in ms, shares = ratio of sums)

| model | mode | tasks | calls | LLM inference | tool latency | authorisation | wall | auth share | of which per-call (challenge+prep+verify) | of which delegation | auth share w/o tool latency (counterfactual) | tool-latency share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 288 | 4 | 1477 | 712 | 0 | 2133 | 0.0% | 0.0% | 0.0% | 0.0% | 29.4% |
| qwen2.5-7b-instruct | jwt | 288 | 4 | 1517 | 600 | 15 | 2022 | 0.7% | 0.7% | 0.0% | 1.0% | 28.0% |
| qwen2.5-7b-instruct | mm | 288 | 4 | 1527 | 604 | 4169 | 6187 | 58.0% | 42.7% | 15.3% | 66.2% | 12.3% |
| qwen2.5-7b-instruct | mm_esc | 288 | 4 | 1520 | 603 | 4199 | 6169 | 56.9% | 41.5% | 15.4% | 64.4% | 11.7% |
| qwen2.5-72b-instruct-awq | none | 288 | 5 | 5011 | 713 | 0 | 5663 | 0.0% | 0.0% | 0.0% | 0.0% | 13.1% |
| qwen2.5-72b-instruct-awq | jwt | 288 | 4 | 5012 | 641 | 16 | 5574 | 0.3% | 0.3% | 0.0% | 0.4% | 12.1% |
| qwen2.5-72b-instruct-awq | mm | 288 | 4 | 5027 | 640 | 4111 | 9325 | 37.9% | 26.0% | 11.9% | 41.0% | 7.5% |
| qwen2.5-72b-instruct-awq | mm_esc | 288 | 4 | 5090 | 640 | 4134 | 9360 | 38.1% | 26.2% | 11.9% | 41.2% | 7.5% |
| gpt-oss-20b | none | 288 | 5 | 3597 | 714 | 0 | 4315 | 0.0% | 0.0% | 0.0% | 0.0% | 15.6% |
| gpt-oss-20b | jwt | 288 | 4 | 3744 | 629 | 18 | 4476 | 0.4% | 0.4% | 0.0% | 0.5% | 14.3% |
| gpt-oss-20b | mm | 288 | 4 | 3768 | 630 | 4149 | 8389 | 42.6% | 29.2% | 13.4% | 46.5% | 8.3% |
| gpt-oss-20b | mm_esc | 288 | 4 | 3781 | 630 | 4177 | 8328 | 42.6% | 29.3% | 13.3% | 46.4% | 8.3% |
| hermes-3-llama-3.1-8b | none | 288 | 6 | 1921 | 800 | 0 | 2727 | 0.0% | 0.0% | 0.0% | 0.0% | 31.0% |
| hermes-3-llama-3.1-8b | jwt | 288 | 5 | 1888 | 692 | 17 | 2567 | 0.7% | 0.7% | 0.0% | 1.1% | 29.8% |
| hermes-3-llama-3.1-8b | mm | 288 | 5 | 1877 | 698 | 4123 | 7060 | 59.1% | 42.0% | 17.2% | 67.3% | 12.2% |
| hermes-3-llama-3.1-8b | mm_esc | 288 | 5 | 1876 | 692 | 4145 | 7084 | 58.6% | 41.9% | 16.7% | 66.6% | 12.0% |
| granite-3.3-8b-instruct | none | 288 | 4 | 2719 | 571 | 0 | 3233 | 0.0% | 0.0% | 0.0% | 0.0% | 18.4% |
| granite-3.3-8b-instruct | jwt | 288 | 4 | 2718 | 532 | 14 | 3190 | 0.5% | 0.5% | 0.0% | 0.6% | 17.7% |
| granite-3.3-8b-instruct | mm | 288 | 4 | 2717 | 518 | 3210 | 6598 | 45.6% | 32.3% | 13.3% | 50.4% | 9.4% |
| granite-3.3-8b-instruct | mm_esc | 288 | 4 | 2668 | 530 | 3681 | 6796 | 46.6% | 32.9% | 13.8% | 51.6% | 9.5% |

## Safety counters (all configurations)

| model | mode | runs | honest calls | honest calls wrongly rejected | revocations | revoked calls attempted | rejected | accepted | out-of-mandate calls attempted / accepted | wallet refusals | c: all paid | c: claims DONE | failures with false rejection | failures by policy | errors | nudged runs | re-run units |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | none | 480 | 3061 | 0 | 118 | 207 | 0 | 207 | 8 / 8 | 0 | 50/120 | 120 | 0 | 0 | 0 | 22 | 0 |
| qwen2.5-7b-instruct | jwt | 480 | 3089 | 0 | 117 | 120 | 120 | 0 | 6 / 0 | 0 | 0/120 | 3 | 0 | 6 | 0 | 17 | 0 |
| qwen2.5-7b-instruct | mm | 480 | 3153 | 0 | 117 | 120 | 120 | 0 | 7 / 0 | 7 | 0/120 | 3 | 0 | 7 | 0 | 17 | 0 |
| qwen2.5-7b-instruct | mm_esc | 480 | 3090 | 0 | 118 | 123 | 123 | 0 | 5 / 0 | 5 | 0/120 | 2 | 0 | 5 | 0 | 19 | 0 |
| qwen2.5-72b-instruct-awq | none | 480 | 2534 | 0 | 120 | 140 | 0 | 140 | 0 / 0 | 0 | 113/120 | 120 | 0 | 0 | 0 | 0 | 0 |
| qwen2.5-72b-instruct-awq | jwt | 480 | 2534 | 0 | 120 | 120 | 120 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 0 | 0 |
| qwen2.5-72b-instruct-awq | mm | 480 | 2534 | 0 | 120 | 120 | 120 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 0 | 0 |
| qwen2.5-72b-instruct-awq | mm_esc | 480 | 2534 | 0 | 120 | 120 | 120 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 0 | 0 |
| gpt-oss-20b | none | 480 | 2526 | 0 | 120 | 147 | 0 | 147 | 0 / 0 | 0 | 120/120 | 120 | 0 | 0 | 0 | 89 | 6 |
| gpt-oss-20b | jwt | 480 | 2526 | 0 | 119 | 126 | 126 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 90 | 7 |
| gpt-oss-20b | mm | 480 | 2523 | 0 | 120 | 125 | 125 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 91 | 5 |
| gpt-oss-20b | mm_esc | 480 | 2526 | 0 | 120 | 125 | 125 | 0 | 0 / 0 | 0 | 0/120 | 0 | 0 | 0 | 0 | 89 | 6 |
| hermes-3-llama-3.1-8b | none | 480 | 2771 | 0 | 113 | 200 | 0 | 200 | 0 / 0 | 0 | 53/120 | 105 | 0 | 0 | 0 | 204 | 0 |
| hermes-3-llama-3.1-8b | jwt | 480 | 2775 | 0 | 113 | 114 | 114 | 0 | 0 / 0 | 0 | 0/120 | 18 | 0 | 0 | 0 | 203 | 0 |
| hermes-3-llama-3.1-8b | mm | 480 | 2770 | 0 | 116 | 117 | 117 | 0 | 0 / 0 | 0 | 0/120 | 15 | 0 | 0 | 0 | 196 | 0 |
| hermes-3-llama-3.1-8b | mm_esc | 480 | 2774 | 0 | 114 | 115 | 115 | 0 | 0 / 0 | 0 | 0/120 | 17 | 0 | 0 | 0 | 199 | 0 |
| granite-3.3-8b-instruct | none | 480 | 2234 | 0 | 57 | 78 | 0 | 78 | 2 / 2 | 0 | 7/120 | 120 | 0 | 0 | 0 | 87 | 73 |
| granite-3.3-8b-instruct | jwt | 480 | 2219 | 0 | 55 | 67 | 67 | 0 | 2 / 0 | 0 | 0/120 | 71 | 0 | 2 | 0 | 100 | 72 |
| granite-3.3-8b-instruct | mm | 480 | 2185 | 0 | 55 | 65 | 65 | 0 | 0 / 0 | 0 | 0/120 | 73 | 0 | 0 | 0 | 90 | 72 |
| granite-3.3-8b-instruct | mm_esc | 480 | 2214 | 0 | 56 | 67 | 67 | 0 | 1 / 0 | 1 | 0/120 | 67 | 0 | 1 | 0 | 88 | 73 |

## Micro-benchmark of the primitives on the compute node (median ms; `bench`, outside the agent loop)

| file | threads (RAYON_NUM_THREADS) | cores | MM prep (root) | MM verify | MM_esc prep | MM_esc verify | MM prep (child) | delegation parent+issuer | revoke | verifier update | JWT prep | JWT verify |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bench-1thread-gpt-oss-20b-45346.json | 1 | 1 | 357.9 | 94.7 | 361.3 | 97.4 | 358.6 | 1955+370 | 5.8 | 13.5 | 0.043 | 0.248 |
| bench-1thread-granite-3.3-8b-instruct-45347.json | 1 | 1 | 357.4 | 94.7 | 360.9 | 97.6 | 357.1 | 1934+365 | 5.8 | 13.5 | 0.043 | 0.246 |
| bench-1thread-hermes-3-llama-3.1-8b-45345.json | 1 | 1 | 357.5 | 94.7 | 360.9 | 97.5 | 357.1 | 1934+365 | 5.8 | 13.5 | 0.044 | 0.247 |
| bench-1thread-qwen2.5-72b-instruct-awq-45348.json | 1 | 1 | 357.7 | 94.7 | 359.9 | 97.2 | 358.2 | 1935+366 | 5.9 | 13.5 | 0.043 | 0.247 |
| bench-1thread-qwen2.5-7b-instruct-45344.json | 1 | 1 | 358.4 | 94.8 | 361.7 | 97.6 | 358.8 | 1962+365 | 5.8 | 13.5 | 0.043 | 0.247 |
| bench-16threads-gpt-oss-20b-45346.json | 16 | 10 | 122.0 | 62.5 | 124.6 | 64.8 | 122.4 | 531+175 | 6.0 | 13.8 | 0.044 | 0.248 |
| bench-16threads-granite-3.3-8b-instruct-45347.json | 16 | 10 | 122.6 | 62.5 | 125.9 | 64.4 | 123.8 | 535+166 | 5.7 | 13.5 | 0.044 | 0.248 |
| bench-16threads-hermes-3-llama-3.1-8b-45345.json | 16 | 10 | 123.2 | 62.3 | 126.1 | 64.3 | 123.9 | 535+167 | 5.2 | 13.6 | 0.044 | 0.248 |
| bench-16threads-qwen2.5-72b-instruct-awq-45348.json | 16 | 10 | 123.0 | 63.3 | 125.8 | 64.9 | 123.1 | 530+163 | 5.2 | 13.6 | 0.044 | 0.247 |
| bench-16threads-qwen2.5-7b-instruct-45344.json | 16 | 10 | 122.7 | 62.6 | 125.7 | 64.7 | 123.4 | 543+165 | 5.6 | 13.6 | 0.044 | 0.247 |


## Design (what changed with respect to E4 v1)

* **Tasks.** 96 deterministic tasks (`python e4v2.py tasks`), 24 per template: (a) flight + hotel, two payments by the agent (root mandate); (b) delegation: the agent pays the flight and must call `delegate_hotel_booking`, which spawns a sub-agent (same model, own system prompt) holding a child mandate (classes {search, payment}, per-call budget = max price per night x nights, quota k = 50, 1 h expiry) obtained with `Authority.delegate` (MM) or an issuer-signed child JWT with its own holder key and ancestor chain (JWT); (c) revocation: as (b) plus an airport transfer; after the sub-agent's first accepted payment the harness revokes the child (`Authority.revoke` + `Verifier.update` on every tool; JWT: revocation list pushed to every tool) and refuses any re-delegation; success = safe failure (no post-revocation call accepted, no wrong payment, and the main agent's final answer reports FAILED); (d) search-heavy: weather + flights + hotels for three cities, a rain filter and a cost comparison, 11 calls.
* **Tools.** Four MCP servers (official Python SDK 1.30.0, FastMCP, streamable HTTP with JSON responses, 127.0.0.1): airline, hotel, ground (transfers + weather), payment. Each server has a `challenge` tool (not shown to the model) that issues single-use 128-bit nonces valid 60 s; the nonce is bound into the MM presentation (`nonce`) and into the JWT proof-of-possession. Tool identity = `<origin>|<tool name>`; canonical call = RFC 8785 JCS of `{"name","arguments"}` with amounts in integer cents; class 0 = travel search, 1 = information (weather), 2 = payment; `t` = Unix seconds, accepted within 300 s.
* **Tool latency.** Every accepted call sleeps for a lognormal delay: median 120 ms, sigma 0.5 (mu = ln 120 = 4.787), mean 136 ms, p95 273 ms, clipped at 2 s; per (task, configuration, server) RNG so that every mode sees the same draws. The `t0_nolat` configuration repeats temperature 0 with zero latency.
* **Modes.** `none`; `jwt` (EdDSA mandate JWT issued by the wallet with scope classes, per-call budget, holder key `cnf`, ancestor list; per-call PoP JWT with `aud` = tool id, SHA-256 of the JCS call, the tool nonce, `iat`; tools check signatures, nonce, call hash, scope, budget and the revocation list); `mm` / `mm_esc` (mmpy v2: one `Authority` per task run; tools hold only `public_params`). The model sees identical prompts, tool schemas and tool results in every mode; authorisation travels in MCP `_meta`.
* **Timing hygiene.** Each of the W = 5 workers is one agent process (LLM client, wallet, prover) pinned to one core and one tool-server process (4 MCP servers, verifiers) pinned to another core; RAYON_NUM_THREADS = OMP_NUM_THREADS = 1; vLLM gets the 5 remaining cores of the 16 allocated (the Hedy QOS grants 16 cores per GPU). `lscpu`, core lists, thread settings and each process's affinity are stored in every result JSON. Wall-clock times are `perf_counter`; CPU times are `process_time` of the process.
* **Harness fixes for the v1 failures.** Hermes-3 stopped after one call in v1 because it asked the user for confirmation: the system prompt now states that the user approved the whole task, and a reply without tool calls and without DONE/FAILED receives at most two identical nudges (same rule for every model and mode; counted). Hermes-3 is served with its own `tool_use` chat template (extracted from tokenizer_config.json and passed with `--chat-template`). Granite-3.3 failed in v1 because its official template only adds the tool-calling instruction to its default system message and drops assistant tool calls from the history: a corrected template (`templates/granite33_tools.jinja`) appends the official instruction to our system message, renders `<|tool_call|>[...]` and `tool_response` turns. Mistral-Small-3.2 was not retried (vLLM 0.33 bug in the Mistral grammar path; weights no longer on disk and re-downloading 48 GB would exceed the quota budget). gpt-oss: harmony special tokens occasionally echoed as plain text are stripped before re-sending (they made vLLM return HTTP 500); transient transport errors are retried; the few units that still ended with a harness error were re-run once with `--rerun-errors` (listed in each JSON under `reruns`).

## Jobs and compute (MesoNET Hedy, account m26297, partition gpu, 1 H100 80GB + 16 cores per job)

| job | purpose | elapsed |
|---|---|---|
| 45321-45325, 45335 | smoke runs (1 task per template, t0 + t07_s1, 4 workers): Qwen-7B, Hermes-3, Granite (template bug, redone as 45335), gpt-oss, Qwen-72B | 4-5 min each |
| 45336-45340 | first campaign submission, cancelled after ~5 min: the QOS grants 16 cores per GPU, the 24-core layout failed (fixed: W = 5 workers) | ~5 min each |
| 45344 | qwen2.5-7b-instruct campaign (1920 runs) | 41 min |
| 45345 | hermes-3-llama-3.1-8b campaign | 32 min |
| 45346 | gpt-oss-20b campaign | 45 min |
| 45347 | granite-3.3-8b-instruct campaign (one worker died after 90 units, see below) | 36 min |
| 45348 | qwen2.5-72b-instruct-awq campaign | 53 min |
| 45385 | granite: re-run of the 290 units of the dead worker | 6 min |
| 45399 | gpt-oss: re-run of the 24 units that ended with a harness error | 3 min |

Total: 4.3 GPU-hours (sacct ElapsedRaw, all jobs above), well below the 30 GPU-hour budget. No job left running; Hedy home quota back to 409 GB (the NFS server pre-allocates space for files open in append mode: up to ~11 GB per running job, released at close).

## Problems met during v2 and how they were handled

* Core split: Hedy's QOS caps a 1-GPU job at 16 cores / 120 GB whatever `--cpus-per-task` says; the first submission (24 cores, 8 workers) failed its core-split assertion and was cancelled; final layout = 5 vLLM cores, 1 orchestrator core, 5 agent cores, 5 tool-server cores.
* Granite template: Jinja `list.append` is forbidden in vLLM's sandbox (HTTP 400 in smoke job 45323); rewritten with `namespace()` (45335 and later).
* Granite worker 3 died after 90 units: an `httpx.ReadError` in the MCP streamable-HTTP client (race with uvicorn's 5 s keep-alive timeout on the tool server) propagated out of the session task group. Fix: tool servers now use `timeout_keep_alive=3600` (Qwen-72B job and re-runs); the missing 290 units were re-run (45385). No other worker died (checked in every worker log).
* gpt-oss-20b: 24 units ended with HTTP 500 because a malformed tool-call *name* or content contained harmony special tokens (`<|end|><|start|>assistant`) that vLLM refuses to re-tokenize; two ended with a transport `ReadError`. Fix: special tokens are replaced by a space in the history (content, tool names, arguments; counted as `sanitised`, 14 runs), transport errors are retried; the 24 units were re-run (45399), all completed.
* `bench` initially failed for the child mandate (counter space shared by the subtree: the root had already used more counters than the child's quota k = 50 on the same tool); the bench now uses a fresh authority for the delegation part. This is the intended semantics of v2 (rate limit per root mandate, per tool and epoch), worth stating in the paper.
* CPU-time measurement: `thread_time()` misses the work done in the (single) rayon worker thread; replaced by `process_time()` before the campaign (smoke JSONs show the wrong CPU column).

## Limitations

* Authorisation overhead is large in this setting: MM prove ~357 ms + verify ~95 ms per call on one Xeon 8462Y+ core, plus ~2.3 s per delegation (parent proof 1.93 s + issuer 0.37 s) — 38-60 % of task wall time with 120 ms tool latency, against 0.3-1.1 % for JWT. With 16 rayon threads (10 cores) the same primitives take 122 + 63 ms on this node: the v1 figure (154 ms per call) was multi-threaded.
* Concurrency: 5 agents share one vLLM instance (continuous batching), so LLM times are those of a lightly loaded server, and temperature-0 decoding is not bitwise reproducible across runs (control: same mode and prompts run twice at temperature 0, identical LLM-visible transcripts in 40-58 % of units for Granite, 67-86 % for Qwen-7B, gpt-oss and Hermes, 99-100 % for Qwen-72B). Paired comparisons between modes are therefore affected by this noise; the honest-template discordances between modes are of the same order as the control.
* Tool latency is simulated (lognormal sleep) and tool results come from a deterministic synthetic world; the 96 tasks are template-generated, not real user requests.
* In template (c), success needs the model to report FAILED; 86-92 runs per authorised mode (of 600) were unsafe claims of DONE after a rejection (model behaviour, not an authorisation leak: no revoked call was ever accepted).
* `none` cannot revoke: the (c) comparison measures what authorisation adds, not a property of MM alone; JWT with a pushed revocation list enforces revocation equally well, MM's difference is unlinkability/accountability (not measured here).
* One `Authority` per task run (fresh issuer keys and accumulator per run), so revocation lists stay small; the cost of refreshing many witnesses at scale is not measured here (see E1).
* Mistral-Small-3.2 not included (vLLM 0.33 grammar bug, weights removed, re-download would exceed the disk budget).
* Build provenance: mmpy v2 was built on the Hedy login node (maturin, release, into agentenv) from the `code/` tree copied at 10:54 on 13/11 (src/lib.rs sha256 6ad443a1...). The local `src/lib.rs` was modified afterwards (11:13, not by this experiment; sha256 3a6edf25...): the diff only adds malicious-prover test hooks (`Cheat.weaken_expiry`, `reveal_class`, `free_quota`) whose defaults leave the honest prover and the verifier unchanged, so the E4 v2 numbers apply to the current code, but a rebuild before the final artifact is advisable.
