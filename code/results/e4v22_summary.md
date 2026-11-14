# E4 v2.2 -- dishonest wallet (R2-B1) and grace window / retry (R2-B3) (summary)

Generated 2026-11-14 11:18 by `e4v22.py analyse22`. Harness `code/e4v22/e4v22.py` (derived from `code/e4v21/e4v21.py`, which is unchanged, as are the E4 v2.1 results). Every number below is computed from the result JSON files listed under Provenance and is also in `code/results/e4v22_key.json`.

## Key results

**Evidence base.**
* All the runs below use the scripted policy (`--base-url oracle`, no LLM; the harness self-test policy that follows each task's reference plan and replies FAILED at the first rejection). The decision to present belongs to the wallet, and the decision to accept belongs to the tool, so these mechanisms do not depend on the LLM.
* The runs were on the Hedy login node (niced; 5 workers, 1 agent core and 1 tool-server core each, `RAYON_NUM_THREADS=1`), with the real MCP client and servers, the real mmpy proofs and the same tasks, tools and scoring as E4 v2.1.
* LLM confirmation: the Slurm jobs (51013, 51014, 51052; 2.01 GPU-hours) started after the scripted-policy runs, at 07:53 and 08:14. They were not cancelled because they had started by the time this session could check again (it was cut off by a network error from ~07:05 to 11:05). They ran the same configurations with the five models. Their results confirm the scripted-policy ones in every respect and are reported in the tables below, and under new keys `dw.llm.*`, `grace.llm.*` and `probe.llm.*` in the key file; the oracle keys are unchanged.

**R2-B1, dishonest wallet.** The wallet ignores revocation and quota, but its proofs are real (`Authority.present_dishonest`). Templates c and e, 24 tasks each, per-task issuer (W = 0).
* **Revoked sub-agent, template c.**
  * Stale V (`mm_dw`: pre-revocation witnesses against the pre-revocation accumulator value): 24 presentations sent, 24 rejected by the tools, all with the uniform error `rejected`, 0 accepted. The tool's internal reason was "accumulator value not accepted".
  * Current V with a stale witness (`mm_dw_cv`): the proof can be built (the prover does not check the witness), but the tool rejects it in the pairing check of the non-membership proof ("VBAccumProofContributionFailed(9, PairingResponseInvalid)"): 24 of 24 rejected, uniform error, 0 accepted.
* **Beyond quota, template e (k = 3 searches).** Reusing a counter of its own part: 48 of 48 presentations (both modes) rejected by the tool's seen-set ("pseudonym replay (counter reused)"), uniform error, 0 accepted.
* **Counter outside the interval.** The library refuses to prove: Bulletproofs++ "Only supports 64 bit values", because k - j - 1 wraps modulo p. Nothing can be sent (deterministic check `dwprobe`).
* **Honest calls in these runs:** 0 of 480 rejected.
* **The per-task issuer has W = 0, so a stale-V presentation is never accepted.** With a count window W the same stale-V presentation *is* accepted until W further accumulator updates (`dwprobe`: accepted after 0 and 1 further updates, rejected after 2). With a time window D it is accepted only within D of the installation (accepted at 105 ms, rejected at 1,069 ms with D = 1,000 ms). The grace window is therefore exactly the dishonest holder's revocation delay.

**R2-B3, shared issuer, one dummy revocation every 2 s per worker** (120 tasks, mode mm, t0, 200 dummies per worker, publish-then-refresh).
* **W = 0, no retry:** 80 of 460 honest calls rejected, all from accumulator churn; success 57.5 %. The oracle stops at the first rejection, hence fewer calls.
* **W = 0 + wallet retry:** 192 first attempts rejected (all churn), all 192 retries accepted, 0 of 696 honest calls rejected in the end; success 100 %. Revocation delay 0.24 s median (0.28 s p95), 0 updates.
* **Time window D = 1,000 ms, no retry:** 0 of 696 rejected; success 100 %; delay 1.25 s median (1.28 s p95), 0 updates median (1 at p95).
* **W = 2, no retry:** 0 of 696 rejected; success 100 %; delay 4.24 s median (6.02 s p95), 2 updates.
* **No revoked or beyond-quota call was accepted in any run.**
* **First retry variant:** the retry consumed a new hidden counter, which wasted quota (template e, k = 3): 18 of 696 honest calls ended rejected (14 later calls refused by the wallet for exhausted quota, 4 retries refused for quota). The harness now reuses the rejected presentation's counter (`Authority.release_counter`; a tool never records a rejected pseudonym). Both runs are reported.

**R2-B3, sparse schedule** (one dummy revocation every 60 s per worker; 30 tasks; revoker kept running at least 600 s; 45 dummy + 6 task revocations per configuration).
* **W = 2:** revocation delay 120.15 s median (120.16 s p95), i.e. W x the revocation interval; 2 updates. The count-based delay scales with the interval.
* **D = 1,000 ms:** 1.15 s median (1.16 s p95), 0 updates. The time-based delay is bounded by D plus the push time, whatever the interval.
* **Dishonest-wallet probes** of the revoked dummies (stale V):
  * Under W = 2: accepted right after installation (45 of 45), accepted again ~61 s later after one more update (40 of 40), rejected after the second update ~122 s later (0 of 35 accepted), and accepted 2.4 s after installation (45 of 45).
  * Under D = 1,000 ms: accepted right after installation (45 of 45, ~0.75 s after the request), rejected ~2 s after the request (0 of 45), and rejected at every later probe (0 of 40, 0 of 35).
* **Honest calls:** 0 of 174 rejected in both configurations.

**LLM confirmation (t0, 24 tasks per template; dense: 120 tasks; sparse: 30 tasks; one job per model group).**
* **Dishonest wallet**, 5 models x {mm_dw, mm_dw_cv} x {c, e}:
  * Template c: 0 of 215 presentations by revoked sub-agents accepted (215 rejected, all with the uniform error).
  * Template e: 0 of 414 beyond-quota presentations accepted (414 rejected, all with the uniform error).
  * No proof failed to build, and 0 of 2,147 honest calls were rejected.
  * The tools' internal reasons are the same as with the scripted policy.
* **Dense schedule.**
  * W = 0 + retry: 0 of 629 honest calls rejected for both Qwen2.5-72B-AWQ and gpt-oss-20b (first attempts rejected by churn and all accepted on retry: 102 and 124). Success 89.2 % and 94.2 %, against 65.0 % and 52.5 % for W = 0 without retry in v2.1. Revocation delay 0.24 s median.
  * D = 1,000 ms: 0 of 629 and 0 of 631 rejected; success 89.2 % and 95.0 %; delay 1.24 s median (1.27 s p95).
* **Sparse schedule:** W = 2 delay 120.14 s median for both models, D = 1,000 ms 1.14 s. The probes reproduce the oracle pattern exactly, 45/40/0/45 accepted for W = 2 and 45/0/0/0 for D. 0 honest calls rejected.

**Disclosure (E4 v2.1).** The v2.1 W = 0 and W = 2 shared-issuer runs came from different jobs and two harness versions (e4v21.py sha256 487f16a4... vs 3ce67f88...). Details are in the dedicated section below. In v2.2 all oracle configurations ran in one session with one harness and mmpy build, except the same-counter retry run (one later build that adds only `release_counter`; see Provenance).

## Provenance

| file | job | git commit (local tree copied to Hedy) | mmpy .so sha256 | e4v22.py sha256 | rows |
|---|---|---|---|---|---|
| e4v22_dw_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 96 |
| e4v22_dw_qwen2.5-7b-instruct.json | 51052 | df4f429 | 0b120113e3fb4e1e... | 72b11e647f8c | 96 |
| e4v22_dw_qwen2.5-72b-instruct-awq.json | 51013 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 96 |
| e4v22_dw_gpt-oss-20b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 96 |
| e4v22_dw_hermes-3-llama-3.1-8b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 96 |
| e4v22_dw_granite-3.3-8b-instruct.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 96 |
| e4v22_w0_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 120 |
| e4v22_retry0newctr_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 120 |
| e4v22_retry0_oracle.json | - | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 120 |
| e4v22_w2_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 120 |
| e4v22_d1000_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 120 |
| e4v22_sparse_w2_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 30 |
| e4v22_sparse_d1000_oracle.json | - | e340685 | c3c54fbe39f1f33d... | 3100540aa8fe | 30 |
| e4v22_retry0_qwen2.5-72b-instruct-awq.json | 51013 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 120 |
| e4v22_retry0_gpt-oss-20b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 120 |
| e4v22_d1000_qwen2.5-72b-instruct-awq.json | 51013 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 120 |
| e4v22_d1000_gpt-oss-20b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 120 |
| e4v22_sparse_w2_qwen2.5-72b-instruct-awq.json | 51013 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 30 |
| e4v22_sparse_w2_gpt-oss-20b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 30 |
| e4v22_sparse_d1000_qwen2.5-72b-instruct-awq.json | 51013 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 30 |
| e4v22_sparse_d1000_gpt-oss-20b.json | 51014 | a4149d7 | 0b120113e3fb4e1e... | c277d0fdd937 | 30 |

## Dishonest wallet and grace rules, deterministic checks (`e4v22.py dwprobe`, no LLM; strict non-debug verifiers)

| case | outcome | error returned to the caller | tool's internal reason | acceptance path |
|---|---|---|---|---|
| baseline_child_honest | accepted |  | | |
| revoked_W0_honest_wallet | wallet refused: wallet: mandate revoked or witnesses stale |  | | |
| revoked_W0_dishonest_staleV | rejected | rejected | accumulator value not accepted |  |
| revoked_W0_dishonest_currentV_stale_witness | rejected | rejected | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid) |  |
| revoked_W2_dishonest_staleV_after_0_more_updates | accepted |  |  | count_window |
| revoked_W2_dishonest_currentV_stale_witness | rejected | rejected | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid) |  |
| revoked_W2_dishonest_staleV_after_1_more_update | accepted |  |  | count_window |
| revoked_W2_dishonest_staleV_after_2_more_updates | rejected | rejected | accumulator value not accepted |  |
| revoked_D1000_dishonest_staleV_verified_right_after_install | accepted (105 ms after installation) |  |  | time_window |
| D1000_honest_presentation_built_before_install_verified_after | accepted |  |  | time_window |
| revoked_D1000_dishonest_staleV_verified_1050ms_after_install | rejected (1069 ms after installation) | rejected | accumulator value not accepted |  |
| quota_calls_1_to_3_honest | accepted, accepted, accepted | | | |
| quota_call_4_honest_wallet | wallet refused: wallet: quota exhausted for this tool and epoch |  | | |
| quota_call_4_dishonest_reuse_own_counter | rejected | rejected | pseudonym replay (counter reused) |  |
| quota_call_4_dishonest_counter_outside_interval | proof could not be built: `prove: UnsupportedValue("Only supports 64 bit values Bulletproofs++ range proof but found 524358751751261904794477405081` | (nothing sent) | | |

## R2-B1: dishonest wallet (modes mm_dw, mm_dw_cv), per-task issuer, configuration t0 (temperature 0, tool latency on)

The wallet ignores revocation and quota (mmpy `Authority.present_dishonest`: policy checks bypassed, proofs real). `mm_dw`: after its revocation the sub-agent presents with its pre-revocation witnesses against the pre-revocation accumulator value (stale V); `mm_dw_cv`: with its current witnesses against the current value (current V; the witness of its own, revoked identifier cannot be refreshed). Beyond its quota (template e: 3 hotel searches) it reuses the counters of its own part. *Policy-violating calls* = calls by the revoked sub-agent (template c) or beyond the sub-agent's quota (template e). *Tool-side rejected* = a presentation was sent and the tool rejected it; *uniform* = the error the caller received was the uniform `rejected`; internal reasons are the tool's own log. Honest calls = in-mandate calls before any revocation.

| model | mode | template | runs | policy-violating calls | presentations sent | tool-side rejected | of which uniform error | accepted | proof not built (sent without authorisation; rejected) | tool's internal reasons | honest calls / rejected | success (safe failure) | v2.1 honest-wallet mm, t0 (same tasks) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle | mm_dw | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | accumulator value not accepted: 24 | 120 / 0 | 100.0 [86.2, 100.0] | - |
| oracle | mm_dw | e | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | pseudonym replay (counter reused): 24 | 120 / 0 | 100.0 [86.2, 100.0] | - |
| oracle | mm_dw_cv | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 24 | 120 / 0 | 100.0 [86.2, 100.0] | - |
| oracle | mm_dw_cv | e | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | pseudonym replay (counter reused): 24 | 120 / 0 | 100.0 [86.2, 100.0] | - |
| qwen2.5-7b-instruct | mm_dw | c | 24 | 27 | 27 | 27 | 27 | 0 | 0 (0) | accumulator value not accepted: 27 | 102 / 0 | 50.0 [31.4, 68.6] | 50.0 [31.4, 68.6] |
| qwen2.5-7b-instruct | mm_dw | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 120 / 0 | 75.0 [55.1, 88.0] | 75.0 [55.1, 88.0] |
| qwen2.5-7b-instruct | mm_dw_cv | c | 24 | 25 | 25 | 25 | 25 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 25 | 101 / 0 | 50.0 [31.4, 68.6] | 50.0 [31.4, 68.6] |
| qwen2.5-7b-instruct | mm_dw_cv | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 120 / 0 | 75.0 [55.1, 88.0] | 75.0 [55.1, 88.0] |
| qwen2.5-72b-instruct-awq | mm_dw | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | accumulator value not accepted: 24 | 119 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| qwen2.5-72b-instruct-awq | mm_dw | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 120 / 0 | 75.0 [55.1, 88.0] | 70.8 [50.8, 85.1] |
| qwen2.5-72b-instruct-awq | mm_dw_cv | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 24 | 119 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| qwen2.5-72b-instruct-awq | mm_dw_cv | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 120 / 0 | 75.0 [55.1, 88.0] | 70.8 [50.8, 85.1] |
| gpt-oss-20b | mm_dw | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | accumulator value not accepted: 24 | 115 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| gpt-oss-20b | mm_dw | e | 24 | 31 | 31 | 31 | 31 | 0 | 0 (0) | pseudonym replay (counter reused): 31 | 120 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| gpt-oss-20b | mm_dw_cv | c | 24 | 24 | 24 | 24 | 24 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 24 | 115 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| gpt-oss-20b | mm_dw_cv | e | 24 | 27 | 27 | 27 | 27 | 0 | 0 (0) | pseudonym replay (counter reused): 27 | 120 / 0 | 100.0 [86.2, 100.0] | 100.0 [86.2, 100.0] |
| hermes-3-llama-3.1-8b | mm_dw | c | 24 | 23 | 23 | 23 | 23 | 0 | 0 (0) | accumulator value not accepted: 23 | 104 / 0 | 58.3 [38.8, 75.5] | 37.5 [21.2, 57.3] |
| hermes-3-llama-3.1-8b | mm_dw | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 100 / 0 | 0.0 [0.0, 13.8] | 0.0 [0.0, 13.8] |
| hermes-3-llama-3.1-8b | mm_dw_cv | c | 24 | 23 | 23 | 23 | 23 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 23 | 105 / 0 | 62.5 [42.7, 78.8] | 37.5 [21.2, 57.3] |
| hermes-3-llama-3.1-8b | mm_dw_cv | e | 24 | 48 | 48 | 48 | 48 | 0 | 0 (0) | pseudonym replay (counter reused): 48 | 102 / 0 | 0.0 [0.0, 13.8] | 0.0 [0.0, 13.8] |
| granite-3.3-8b-instruct | mm_dw | c | 24 | 10 | 10 | 10 | 10 | 0 | 0 (0) | accumulator value not accepted: 10 | 75 / 0 | 12.5 [4.3, 31.0] | 12.5 [4.3, 31.0] |
| granite-3.3-8b-instruct | mm_dw | e | 24 | 33 | 33 | 33 | 33 | 0 | 0 (0) | pseudonym replay (counter reused): 33 | 96 / 0 | 20.8 [9.2, 40.5] | 16.7 [6.7, 35.9] |
| granite-3.3-8b-instruct | mm_dw_cv | c | 24 | 11 | 11 | 11 | 11 | 0 | 0 (0) | verify: VBAccumProofContributionFailed(9, PairingResponseInvalid): 11 | 80 / 0 | 12.5 [4.3, 31.0] | 12.5 [4.3, 31.0] |
| granite-3.3-8b-instruct | mm_dw_cv | e | 24 | 35 | 35 | 35 | 35 | 0 | 0 (0) | pseudonym replay (counter reused): 35 | 94 / 0 | 20.8 [9.2, 40.5] | 16.7 [6.7, 35.9] |

* Total scripted policy, mm_dw, template c: 24 policy-violating calls, 24 presentations sent, 24 rejected by the tools (24 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total LLMs (all models), mm_dw, template c: 108 policy-violating calls, 108 presentations sent, 108 rejected by the tools (108 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total scripted policy, mm_dw, template e: 24 policy-violating calls, 24 presentations sent, 24 rejected by the tools (24 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total LLMs (all models), mm_dw, template e: 208 policy-violating calls, 208 presentations sent, 208 rejected by the tools (208 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total scripted policy, mm_dw_cv, template c: 24 policy-violating calls, 24 presentations sent, 24 rejected by the tools (24 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total LLMs (all models), mm_dw_cv, template c: 107 policy-violating calls, 107 presentations sent, 107 rejected by the tools (107 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total scripted policy, mm_dw_cv, template e: 24 policy-violating calls, 24 presentations sent, 24 rejected by the tools (24 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.
* Total LLMs (all models), mm_dw_cv, template e: 206 policy-violating calls, 206 presentations sent, 206 rejected by the tools (206 with the uniform error), 0 accepted; 0 calls for which the proof could not be built.

## R2-B3: grace window and wallet retry under a dense revocation schedule (one revocation every 2 s per worker)

Shared issuer: one Authority per worker for all its tasks, 200 unrelated dummy mandates per worker, one dummy revoked every 2 s (fixed schedule) and the new public parameters pushed to the 4 tools; publish-then-refresh ordering; mode mm, temperature 0, tool latency on, 120 tasks. Churn = rejected honest call whose presentation was built against an older accumulator version than the one the tool held. With retry, honest rejected/churn are final outcomes after the single retry; first-attempt columns count rejections before it. Revocation delay = time from the revocation request to the moment no tool accepts a pre-revocation accumulator value: count window W, installation (last tool) of version v+W; time window D, installation of v plus D. Delay in accumulator updates = number of further accumulator values installed before that moment (W by construction for count windows).

| model | configuration | source (job) | revocation interval (s) | runs | success | honest calls | honest rejected | of which churn | first-attempt rejected (churn) | retries (accepted) | revocations (dummy + task) | delay s median [p95] (max) | delay in accumulator updates median [p95] (max) | revoked / beyond-quota calls accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-oss-20b | count W = 0, no retry [v2.1] | v2.1 e4v21_shared_gpt-oss-20b_W0.json (e4v21.py 3ce67f88; 48495) | 1.93 | 120 | 52.5 [43.6, 61.2] | 420 | 81 | 81 | 81 (81) | 0 (0) | 349 + 12 | 0.23 [0.27] (2.68) | 0 [0] (0) | 0 |
| gpt-oss-20b | count W = 0, retry (same counter) | v2.2 e4v22_retry0_gpt-oss-20b.json (51014) | 1.92 | 120 | 94.2 [88.4, 97.1] | 629 | 0 | 0 | 124 (124) | 124 (124) | 560 + 24 | 0.24 [0.26] (2.75) | 0 [0] (0) | 0 |
| gpt-oss-20b | count W = 2, no retry [v2.1] | v2.1 e4v21_shared_gpt-oss-20b_W2.json (e4v21.py 487f16a4; 45433) | 1.91 | 120 | 95.8 [90.6, 98.2] | 624 | 0 | 0 | 0 (0) | 0 (0) | 522 + 24 | 4.22 [5.93] (6.70) | 2 [2] (2) | 0 |
| gpt-oss-20b | time D = 1000 ms | v2.2 e4v22_d1000_gpt-oss-20b.json (51014) | 1.91 | 120 | 95.0 [89.5, 97.7] | 631 | 0 | 0 | 0 (0) | 0 (0) | 542 + 24 | 1.24 [1.27] (3.76) | 0 [1] (1) | 0 |
| oracle | count W = 0, no retry | v2.2 e4v22_w0_oracle.json (login node) | 1.96 | 120 | 57.5 [48.6, 66.0] | 460 | 80 | 80 | 80 (80) | 0 (0) | 255 + 5 | 0.24 [0.27] (0.38) | 0 [0] (0) | 0 |
| oracle | count W = 0, retry (new counter) | v2.2 e4v22_retry0newctr_oracle.json (login node) | 1.88 | 120 | 100.0 [96.9, 100.0] | 696 | 18 | 0 | 188 (174) | 174 (170) | 400 + 24 | 0.24 [0.28] (0.39) | 0 [0] (0) | 0 |
| oracle | count W = 0, retry (same counter) | v2.2 e4v22_retry0_oracle.json (login node) | 1.89 | 120 | 100.0 [96.9, 100.0] | 696 | 0 | 0 | 192 (192) | 192 (192) | 414 + 24 | 0.24 [0.28] (0.40) | 0 [0] (0) | 0 |
| oracle | count W = 2, no retry | v2.2 e4v22_w2_oracle.json (login node) | 1.87 | 120 | 100.0 [96.9, 100.0] | 696 | 0 | 0 | 0 (0) | 0 (0) | 365 + 24 | 4.24 [6.02] (6.68) | 2 [2] (2) | 0 |
| oracle | time D = 1000 ms | v2.2 e4v22_d1000_oracle.json (login node) | 1.87 | 120 | 100.0 [96.9, 100.0] | 696 | 0 | 0 | 0 (0) | 0 (0) | 364 + 24 | 1.25 [1.28] (1.41) | 0 [1] (1) | 0 |
| qwen2.5-72b-instruct-awq | count W = 0, no retry [v2.1] | v2.1 e4v21_shared_qwen2.5-72b-instruct-awq_W0.json (e4v21.py 487f16a4; 45432) | 1.96 | 120 | 65.0 [56.1, 72.9] | 556 | 94 | 94 | 94 (94) | 0 (0) | 602 + 11 | 0.24 [0.26] (0.38) | 0 [0] (0) | 0 |
| qwen2.5-72b-instruct-awq | count W = 0, retry (same counter) | v2.2 e4v22_retry0_qwen2.5-72b-instruct-awq.json (51013) | 1.94 | 120 | 89.2 [82.3, 93.6] | 629 | 0 | 0 | 102 (102) | 102 (102) | 736 + 24 | 0.24 [0.27] (0.36) | 0 [0] (0) | 0 |
| qwen2.5-72b-instruct-awq | count W = 2, no retry [v2.1] | v2.1 e4v21_shared_qwen2.5-72b-instruct-awq_W2.json (e4v21.py 3ce67f88; 48510) | 1.93 | 120 | 88.3 [81.4, 92.9] | 629 | 0 | 0 | 0 (0) | 0 (0) | 713 + 24 | 4.22 [5.54] (6.69) | 2 [2] (2) | 0 |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | v2.2 e4v22_d1000_qwen2.5-72b-instruct-awq.json (51013) | 1.93 | 120 | 89.2 [82.3, 93.6] | 629 | 0 | 0 | 0 (0) | 0 (0) | 713 + 24 | 1.24 [1.27] (1.33) | 0 [1] (1) | 0 |

## R2-B3: count-based (W = 2) vs time-based (D = 1,000 ms) grace under a sparse revocation schedule

Same configuration with one dummy revocation every 60 s per worker (revoker kept running for at least the stated duration); no retry. Delay definitions as above.

| model | configuration | source (job) | revocation interval (s) | runs | success | honest calls | honest rejected | of which churn | first-attempt rejected (churn) | retries (accepted) | revocations (dummy + task) | delay s median [p95] (max) | delay in accumulator updates median [p95] (max) | revoked / beyond-quota calls accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-oss-20b | count W = 2, no retry | v2.2 e4v22_sparse_w2_gpt-oss-20b.json (51014) | 56.25 | 30 | 96.7 [83.3, 99.4] | 159 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 120.14 [120.15] (120.15) | 2 [2] (2) | 0 |
| gpt-oss-20b | time D = 1000 ms | v2.2 e4v22_sparse_d1000_gpt-oss-20b.json (51014) | 56.28 | 30 | 100.0 [88.6, 100.0] | 159 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 1.14 [1.15] (1.15) | 0 [0] (0) | 0 |
| oracle | count W = 2, no retry | v2.2 e4v22_sparse_w2_oracle.json (login node) | 56.98 | 30 | 100.0 [88.6, 100.0] | 174 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 120.15 [120.16] (120.16) | 2 [2] (2) | 0 |
| oracle | time D = 1000 ms | v2.2 e4v22_sparse_d1000_oracle.json (login node) | 56.98 | 30 | 100.0 [88.6, 100.0] | 174 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 1.15 [1.16] (1.16) | 0 [0] (0) | 0 |
| qwen2.5-72b-instruct-awq | count W = 2, no retry | v2.2 e4v22_sparse_w2_qwen2.5-72b-instruct-awq.json (51013) | 55.48 | 30 | 80.0 [62.7, 90.5] | 160 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 120.14 [120.15] (120.15) | 2 [2] (2) | 0 |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | v2.2 e4v22_sparse_d1000_qwen2.5-72b-instruct-awq.json (51013) | 55.58 | 30 | 80.0 [62.7, 90.5] | 160 | 0 | 0 | 0 (0) | 0 (0) | 45 + 6 | 1.14 [1.15] (1.24) | 0 [0] (0) | 0 |

### Dishonest-wallet probes of revoked dummies (sparse schedule)

After each dummy revocation (version v, installed on the 4 tools), the revoker presents to the hotel tool with the pre-revocation witnesses and accumulator value (stale V, `present_dishonest`) of the dummy just revoked (lag 0), of the dummies revoked at the two previous dummy revocations (lag = current version minus their revocation version), and, `late`, the dummy just revoked again ~1.2 s after the installation. Accepted = the tool accepted the revoked mandate's call.

| model | configuration | probe | accepted / probes | median time from revocation request to verification (s) | internal reasons of rejections |
|---|---|---|---|---|---|
| oracle | count W = 2, no retry | immediate_lag0 | 45 / 45 | 0.76 |  |
| oracle | count W = 2, no retry | immediate_lag1 | 40 / 40 | 61.39 |  |
| oracle | count W = 2, no retry | immediate_lag2 | 0 / 35 | 121.81 | accumulator value not accepted: 35 |
| oracle | count W = 2, no retry | late | 45 / 45 | 2.41 |  |
| oracle | time D = 1000 ms | immediate_lag0 | 45 / 45 | 0.75 |  |
| oracle | time D = 1000 ms | immediate_lag1 | 0 / 40 | 61.17 | accumulator value not accepted: 40 |
| oracle | time D = 1000 ms | immediate_lag2 | 0 / 35 | 121.58 | accumulator value not accepted: 35 |
| oracle | time D = 1000 ms | late | 0 / 45 | 1.97 | accumulator value not accepted: 45 |
| qwen2.5-72b-instruct-awq | count W = 2, no retry | immediate_lag0 | 45 / 45 | 0.72 |  |
| qwen2.5-72b-instruct-awq | count W = 2, no retry | immediate_lag1 | 40 / 40 | 61.30 |  |
| qwen2.5-72b-instruct-awq | count W = 2, no retry | immediate_lag2 | 0 / 35 | 121.69 | accumulator value not accepted: 35 |
| qwen2.5-72b-instruct-awq | count W = 2, no retry | late | 45 / 45 | 2.27 |  |
| gpt-oss-20b | count W = 2, no retry | immediate_lag0 | 45 / 45 | 0.71 |  |
| gpt-oss-20b | count W = 2, no retry | immediate_lag1 | 40 / 40 | 61.30 |  |
| gpt-oss-20b | count W = 2, no retry | immediate_lag2 | 0 / 35 | 121.70 | accumulator value not accepted: 35 |
| gpt-oss-20b | count W = 2, no retry | late | 45 / 45 | 2.26 |  |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | immediate_lag0 | 45 / 45 | 0.71 |  |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | immediate_lag1 | 0 / 40 | 61.08 | accumulator value not accepted: 40 |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | immediate_lag2 | 0 / 35 | 121.46 | accumulator value not accepted: 35 |
| qwen2.5-72b-instruct-awq | time D = 1000 ms | late | 0 / 45 | 1.83 | accumulator value not accepted: 45 |
| gpt-oss-20b | time D = 1000 ms | immediate_lag0 | 45 / 45 | 0.70 |  |
| gpt-oss-20b | time D = 1000 ms | immediate_lag1 | 0 / 40 | 61.09 | accumulator value not accepted: 40 |
| gpt-oss-20b | time D = 1000 ms | immediate_lag2 | 0 / 35 | 121.47 | accumulator value not accepted: 35 |
| gpt-oss-20b | time D = 1000 ms | late | 0 / 45 | 1.83 | accumulator value not accepted: 45 |

## Disclosure: provenance of the E4 v2.1 shared-issuer runs

The W = 0 and W = 2 runs of E4 v2.1 for a given model came from different Slurm jobs and from two versions of the harness (e4v21.py sha256 487f16a4... and 3ce67f88...; the later version adds the IPC-wallet switch, the tool-server pid check and analysis code; the W comparison was not run in a single job with a single harness version): gpt-oss-20b W = 0: job 48495, e4v21.py sha256 3ce67f88; gpt-oss-20b W = 2: job 45433, e4v21.py sha256 487f16a4; qwen2.5-72b-instruct-awq W = 0: job 45432, e4v21.py sha256 487f16a4; qwen2.5-72b-instruct-awq W = 2: job 48510, e4v21.py sha256 3ce67f88. In E4 v2.2 each model's configurations were run in one job with one harness version (see Provenance).

## Jobs and compute (MesoNET Hedy, 1 H100 80GB + 16 cores per job)

| job | purpose | state | elapsed |
|---|---|---|---|
| 51013 | Qwen2.5-72B-AWQ: retry0, d1000, sparse_w2, sparse_d1000, dw; then Qwen2.5-7B dw (invalid: vLLM port collision with 51014, re-run in 51052) | COMPLETED | 54:33 |
| 51014 | gpt-oss-20b: retry0, d1000, sparse_w2, sparse_d1000, dw; then Hermes-3 dw, Granite-3.3 dw | COMPLETED | 1:01:07 |
| 51052 | Qwen2.5-7B dw (re-run) | COMPLETED | 4:44 |

Total: 7224 s = 2.01 GPU-hours (sacct ElapsedRaw).

## Design (what changed with respect to E4 v2.1)

* **mmpy v2.2** (`code/mmpy/src/lib.rs`; the core crate `code/src/lib.rs` is unchanged). `Authority.present_dishonest(idx, tool, call, class_, amt, epoch, t, nonce, escrow, cur, acc, counter)` is a test/debug method. It bypasses only the wallet's policy checks (stale or revoked mandate, quota exhausted) and builds a real proof with the witnesses the wallet holds:
  * `acc="stale"`: uses the snapshot taken in `Authority.revoke` just before the revocation that made the mandate stale, against the accumulator value of that moment (`Cheat{acc_value}` of the core).
  * `acc="current"`: uses the current, partially refreshed witnesses against the current value.
  * `counter="reuse"`: reuses the counters of the mandate's own part cyclically.
  * `counter="beyond"`: uses the counters after its own part.
  * It returns the presentation, the counter offset, the accumulator path and the policy checks it bypassed.
* **Tool-side changes.** `Verifier(..., grace_ms=D)` records the installation instant of every new accumulator value in `update`. Before each `verify` it rebuilds the accepted window: the issuer's count window, plus every previous value whose successor was installed at this tool less than D ms earlier. `Verifier.last_reason()` and `last_path()` give the tool's internal reason and acceptance path (current, count window, or time window). The caller still receives only the uniform error `rejected`.
* **Harness** `code/e4v22/e4v22.py`, derived from `e4v21.py` (unchanged):
  * Modes `mm_dw` (stale V) and `mm_dw_cv` (current V). Both reuse counters beyond the quota, and the tools are configured exactly as in `mm`.
  * `--grace-ms`.
  * `--retry`: if an honest call is rejected and the wallet has since received a newer accumulator version than the one it presented against, it gets a fresh nonce from the tool, rebuilds once and resends. The condition uses only the wallet's own view of the issuer's version.
  * `--probe`, `--probe-late-ms`, `--dummy-k` and `--min-duration` for the sparse schedule; `--templates`.
  * Shared-issuer runs keep the tool verifiers across tasks: parameters are updated rather than the verifiers re-created. The time-window history, seen-sets and nonce stores therefore persist for the whole run. In v2.1 the verifiers were re-created at each task start.
  * Workers wait for the LLM endpoint after setup, so the 200 dummy delegations per worker (about 8 min) overlap with model loading.
* **Unchanged from v2.1:** tasks, prompts, scoring, the nudge rule, the tool latency model, 5 workers with one agent core and one tool-server core each, `RAYON_NUM_THREADS=1`, vLLM 0.33.0 with the same parsers and chat templates, the dummy revocation schedule (2 s, 200 dummies, k = 1) and publish-then-refresh ordering.
* **Build.** mmpy v2.2 was built on the Hedy login node with maturin, release mode, the target directory on `/scratch` and the wheel unpacked into `~/masked-mandates-95/code22/pylib` (PYTHONPATH). The v2.1 `agentenv` and its mmpy were left untouched. Harness self-tests (oracle policy, 2 workers) and `dwprobe` ran on the login node before any GPU job.

## Problems met and how they were handled

* **GPU queue.**
  * Account m26297 allows 4 running and 10 submitted jobs per user, and another project's queue occupied them. The two LLM jobs were submitted at 04:58 and 05:01 and started only at 07:53 and 08:14.
  * The scripted-policy runs were therefore done first and are the primary evidence.
  * The coordinator asked to cancel the LLM jobs if they had not started within ~2 h. This session lost contact from about 07:05 to 11:05 (network error); by then both jobs had run to completion, so they were kept as the LLM confirmation.
* **vLLM port collision (Qwen2.5-7B, job 51013).**
  * Both jobs ran on m-gpu01, and the port formula `8000 + id % 900 + model index` gave job 51013's second model (Qwen2.5-7B) the port of job 51014's first model (gpt-oss-20b, 8614). The Qwen-7B vLLM could not bind, and its workers found the other job's healthy endpoint: all 96 Qwen-7B runs ended with HTTP 404 ("model does not exist").
  * That file is kept in `results/e4v22/invalid_port_collision/` and excluded.
  * The run was repeated in job 51052 after two fixes: a per-job block of 10 vLLM ports, and workers that require their own model in `/v1/models`.
  * The tool-server port ranges of the two jobs were disjoint (`20000 + (id % 40) * 300`), and the other files report 0 errors. gpt-oss received at most 96 rejected requests within a few seconds at 08:48.
* **Hedy home quota.** It was 444 GB of 450 at 11:05 (432 GB at the start of this session), above the 440 GB cap. This session's files on Hedy total ~70 MB (`code22` 37 MB, results 15 MB, logs 16 MB), and builds went to `/scratch`. The increase comes from elsewhere, presumably the other project's jobs; nothing was deleted.
* **No CPU partition.** The `genoa` partition is not open to account m26297. The Mac toolchain cannot link mmpy: the Command Line Tools SDK 27 `.tbd` files are rejected by the linker, and an older SDK produced a library for a different Python ABI. `taskset` is also Linux-only. The scripted-policy runs therefore ran on the Hedy login node: niced, 10 of 32 cores, about 85 min in total, with the node otherwise idle (as for the v2.1 self-tests).
* **Retry consumed a counter.** In the first retry variant the rebuilt presentation used a new hidden counter, so a churn rejection wasted one unit of quota: 18 of 696 honest calls ended rejected in template e. This was fixed by `Authority.release_counter`: the retry reuses the rejected presentation's counter, which is sound because the core verifier checks the accumulator value before the seen-set and releases its reservation on any failure, so a rejected pseudonym is never recorded. Both runs are kept (`e4v22_retry0newctr_oracle.json`, `e4v22_retry0_oracle.json`). Caveat: against a malicious tool that records rejected pseudonyms, the retry would be rejected as a replay and the two attempts would be linkable to each other (they are the same call).
* **Commit mix-up.** The first mmpy v2.2 changes (`present_dishonest`, `grace_ms`, `last_reason`/`last_path`) were committed by another session in e05a059, together with that session's own files, before this session committed. The content is identical: the sha256 of `code/mmpy/src/lib.rs` was checked against the copy built on Hedy.
* **Oracle scope.** The scripted policy replies FAILED at the first rejection. Each template c and e run therefore produces exactly one policy-violating call, and W = 0 without retry produces fewer honest calls (460) than the other configurations (696).

## Files

* Code:
  * `code/mmpy/src/lib.rs`: `present_dishonest`, `release_counter`, `Verifier(grace_ms)`, `last_reason`, `last_path`.
  * `code/e4v22/e4v22.py`: harness, `dwprobe`, `analyse22`.
  * `code/e4v22/hedy_e4v22.sbatch`: LLM jobs, several models per job.
  * `code/e4v22/oracle_login.sh`: scripted-policy runs.
  * `code/e4v22/build_mmpy_hedy.sh`.
* Results:
  * `code/results/e4v22/e4v22_{dw,retry0,d1000,sparse_w2,sparse_d1000}_<model>.json`: LLM confirmation (jobs 51013, 51014, 51052; `jobs.json`; `logs/gpu/`: Slurm, orchestrator, worker and vLLM logs, per-worker parts with LLM-visible transcripts).
  * `code/results/e4v22/e4v22_{dw,w0,retry0newctr,retry0,w2,d1000,sparse_w2,sparse_d1000}_oracle.json`: every run and call, provenance, revocation logs, probe logs.
  * `dwprobe-login.json`.
  * `logs/oracle/`: orchestrator and worker logs, per-worker parts.
* Key numbers: `code/results/e4v22_key.json`.
* Regenerate: `cd code && R=results/e4v22 && M="qwen2.5-7b-instruct qwen2.5-72b-instruct-awq gpt-oss-20b hermes-3-llama-3.1-8b granite-3.3-8b-instruct" && python3 e4v22/e4v22.py analyse22 --dw $R/e4v22_dw_oracle.json $(for m in $M; do echo $R/e4v22_dw_$m.json; done) --shared $R/e4v22_{w0,retry0newctr,retry0,w2,d1000,sparse_w2,sparse_d1000}_oracle.json $R/e4v22_{retry0,d1000,sparse_w2,sparse_d1000}_{qwen2.5-72b-instruct-awq,gpt-oss-20b}.json --dwprobe $R/dwprobe-login.json --v21 results/e4v21 --jobs $R/jobs.json --md results/e4v22_summary.md --key results/e4v22_key.json`. The `.head` and `.tail` files next to the summary are included.

