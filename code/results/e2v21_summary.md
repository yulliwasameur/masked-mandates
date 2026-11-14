# E2 v2.1 -- end-to-end MCP authorisation, 3 independent runs (summary)

Harness `code/e2v2/e2v21.py` (sha256 9a472e3834992427...); git HEAD 027180671fa7c7ace0cc66b86319e85b268168c7, 690add5a2eb8fb012f5756d31be719a919a47f4a (the harness and results are not committed; `git status code/` at run time: 3 entries); mmpy 2.1 .so sha256 ebfe6a5529010e54...; MCP SDK 1.30.0; Python 3.13.16; macOS-26.7.1-arm64-arm-64bit-Mach-O; RAYON_NUM_THREADS=1.

Per (mode, transport, run): 200 measured calls after 15 warm-up calls, round-robin over airline, hotel, payment; canonical call = RFC 8785 JCS of {name, arguments} with `cur` = "EUR" in the arguments. Three independent runs, each a fresh `python e2v21.py run k` process (fresh servers), seeds [20262109, 20263109, 20264109].

## Machine load per run

Each run starts only when the 1-minute load average is <= 3.0 (polled every 30 s, up to 20 min).

| run | seed | quiet at start | waited s | uptime at start | uptime at end |
|---|---|---|---:|---|---|
| 1 | 20262109 | yes | 30.0 | `13:39  up 2 days, 15:42, 1 user, load averages: 2.56 2.73 2.46` | `13:55  up 2 days, 15:57, 1 user, load averages: 2.58 2.70 2.62` |
| 2 | 20263109 | yes | 0.0 | `13:55  up 2 days, 15:57, 1 user, load averages: 2.58 2.70 2.62` | `14:10  up 2 days, 16:12, 1 user, load averages: 2.31 3.28 3.15` |
| 3 | 20264109 | yes | 0.0 | `14:10  up 2 days, 16:12, 1 user, load averages: 2.31 3.28 3.15` | `14:25  up 2 days, 16:28, 1 user, load averages: 3.96 3.16 3.05` |

## What changed vs e2v2

- MM uses mmpy 2.1: `Authority(..., grace=0)`; `delegate(parent, classes, budget, k, exp, epoch)` carves disjoint counter intervals (root [0,100000), agent1 gets 10000 counters, agent2 5000 of agent1's); the wallet refuses revoked/stale mandates.
- MM tools run in STRICT mode: the tool's `challenge` MCP tool returns `Verifier.challenge()` (single-use nonce held by the Rust tool) and the tool's own time; the agent proves with that tool time; the tool checks epoch, |t - now| <= 300 s, nonce issued and unused; errors are the uniform string `rejected`.
- Currency `cur` is part of every canonical call (all modes) and passed to MM `present`/`verify`; new control `tampered currency`.
- `blind_tokens` is now PoP-bound (RFC 9474 token message commits to SHA-256 of a fresh Ed25519 key; redemption reveals the key and signs call hash, tool identity, tool nonce, tool time). The e2v2 bearer variant is kept as `blind_tokens_bearer`.
- New transport `http_stateless`: new TCP connection + new MCP session (initialize) + session close for every challenge and every call.
- Property table gains `issuer_learns`.
- 3 independent runs with different seeds and fresh processes; per-mode medians with range and bootstrap CI over runs; p95.
- MM delegation cost: median of 5 two-hop chains per (mode, transport, run) instead of 3.
- Ports / server names differ (e2v21-*); tool identities are `stdio://e2v21-<tool>|<tool>` or `http://127.0.0.1:<port>|<tool>`.

## Statistics

per (mode, transport): each run gives the median (and p95) over its 200 measured calls; we report the median of the 3 per-run values, their range [min, max], and a percentile bootstrap 95% CI of the median obtained by resampling the 3 per-run values with replacement (10000 resamples; with 3 runs this CI can only take values among the run values and is coarse). pooled_p95 = p95 over all 600 calls.

Cells: median over runs of the per-run medians, then [min, max] over the 3 runs. `CI95` = bootstrap CI of the median over runs. `p95` = median over runs of per-run p95 [range]. ms unless stated.

## Transport: stdio

_MCP stdio, one subprocess per tool server, one long-lived ClientSession per tool_

| mode | total median [range] | CI95 | total p95 [range] | pooled p95 | challenge RTT | prep | call RTT | verify (in tool) | session setup+close | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 1.29 [1.28, 1.33] | [1.28, 1.33] | 1.38 [1.36, 1.46] | 1.41 | 0.00 | 0.00 | 1.29 | 0.00 | 0.00 | 0 |
| jwt_chain | 3.07 [2.96, 3.11] | [2.96, 3.11] | 3.32 [3.31, 3.45] | 3.41 | 1.37 | 0.04 | 1.66 | 0.31 | 0.00 | 1298 |
| biscuit | 2.92 [2.91, 3.02] | [2.91, 3.02] | 3.17 [3.05, 3.26] | 3.20 | 1.31 | 0.06 | 1.55 | 0.24 | 0.00 | 1579 |
| macaroon | 2.73 [2.70, 2.83] | [2.70, 2.83] | 3.17 [2.81, 3.23] | 3.09 | 1.31 | 0.05 | 1.38 | 0.08 | 0.00 | 575 |
| batch_tokens | 2.82 [2.81, 3.29] | [2.81, 3.29] | 3.03 [2.91, 3.72] | 3.56 | 1.30 | 0.05 | 1.47 | 0.17 | 0.00 | 381 |
| blind_tokens | 2.86 [2.82, 3.02] | [2.82, 3.02] | 3.12 [3.08, 3.58] | 3.24 | 1.33 | 0.06 | 1.48 | 0.15 | 0.00 | 802 |
| blind_tokens_bearer | 2.67 [2.65, 2.75] | [2.65, 2.75] | 2.80 [2.75, 2.98] | 2.89 | 1.30 | 0.00 | 1.36 | 0.06 | 0.00 | 661 |
| mm | 371.83 [371.20, 376.92] | [371.20, 376.92] | 395.10 [378.80, 402.33] | 397.39 | 1.90 | 290.32 | 79.76 | 77.32 | 0.00 | 18115 |
| mm_esc | 376.43 [375.17, 376.91] | [375.17, 376.91] | 391.49 [377.95, 394.31] | 390.96 | 1.85 | 292.62 | 81.90 | 79.56 | 0.00 | 18783 |

## Transport: http

_MCP streamable HTTP over 127.0.0.1, one FastMCP server process per tool (distinct ports), one long-lived ClientSession (one Mcp-Session-Id, keep-alive connection) per tool_

| mode | total median [range] | CI95 | total p95 [range] | pooled p95 | challenge RTT | prep | call RTT | verify (in tool) | session setup+close | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 2.97 [2.89, 3.15] | [2.89, 3.15] | 3.43 [3.40, 4.56] | 3.75 | 0.00 | 0.00 | 2.96 | 0.00 | 0.00 | 0 |
| jwt_chain | 6.40 [6.27, 6.41] | [6.27, 6.41] | 7.47 [6.77, 7.47] | 7.30 | 3.02 | 0.05 | 3.29 | 0.35 | 0.00 | 1299 |
| biscuit | 6.36 [6.29, 6.49] | [6.29, 6.49] | 7.60 [7.18, 7.74] | 7.58 | 3.02 | 0.08 | 3.21 | 0.29 | 0.00 | 1579 |
| macaroon | 6.33 [6.01, 6.37] | [6.01, 6.37] | 7.08 [6.58, 8.03] | 7.26 | 3.07 | 0.07 | 3.15 | 0.10 | 0.00 | 576 |
| batch_tokens | 6.25 [6.09, 6.39] | [6.09, 6.39] | 6.83 [6.71, 7.44] | 7.12 | 3.02 | 0.07 | 3.13 | 0.19 | 0.00 | 381 |
| blind_tokens | 6.33 [6.13, 6.47] | [6.13, 6.47] | 7.14 [6.94, 7.64] | 7.37 | 3.05 | 0.07 | 3.14 | 0.18 | 0.00 | 802 |
| blind_tokens_bearer | 5.84 [5.84, 6.22] | [5.84, 6.22] | 6.31 [6.29, 7.13] | 6.71 | 2.91 | 0.00 | 2.92 | 0.08 | 0.00 | 661 |
| mm | 377.35 [375.73, 379.25] | [375.73, 379.25] | 389.43 [379.47, 395.42] | 389.68 | 3.63 | 291.38 | 82.41 | 77.76 | 0.00 | 18115 |
| mm_esc | 381.26 [380.57, 382.46] | [380.57, 382.46] | 392.50 [389.45, 393.11] | 391.99 | 3.74 | 293.10 | 84.41 | 79.70 | 0.00 | 18783 |

## Transport: http_delay10

_as http, through a per-server TCP relay process adding 10 ms one-way delay to every forwarded chunk in each direction (RTT +20 ms per HTTP exchange)_

| mode | total median [range] | CI95 | total p95 [range] | pooled p95 | challenge RTT | prep | call RTT | verify (in tool) | session setup+close | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 26.79 [25.48, 27.42] | [25.48, 27.42] | 28.69 [25.90, 29.42] | 28.76 | 0.00 | 0.01 | 26.78 | 0.00 | 0.00 | 0 |
| jwt_chain | 53.18 [50.06, 53.32] | [50.06, 53.32] | 56.36 [51.90, 56.46] | 55.94 | 26.78 | 0.12 | 26.22 | 0.54 | 0.00 | 1299 |
| biscuit | 52.68 [49.96, 53.42] | [49.96, 53.42] | 56.59 [51.46, 56.65] | 55.97 | 26.52 | 0.17 | 25.92 | 0.44 | 0.00 | 1579 |
| macaroon | 52.70 [49.90, 53.99] | [49.90, 53.99] | 55.76 [50.82, 57.21] | 56.48 | 26.75 | 0.13 | 25.77 | 0.17 | 0.00 | 576 |
| batch_tokens | 53.16 [50.41, 53.35] | [50.41, 53.35] | 56.99 [51.77, 57.16] | 56.62 | 26.76 | 0.13 | 26.03 | 0.31 | 0.00 | 381 |
| blind_tokens | 52.37 [50.45, 52.97] | [50.45, 52.97] | 55.99 [51.47, 56.34] | 55.90 | 26.44 | 0.15 | 25.66 | 0.31 | 0.00 | 802 |
| blind_tokens_bearer | 51.11 [51.11, 51.71] | [51.11, 51.71] | 54.01 [53.75, 54.11] | 53.93 | 26.04 | 0.01 | 25.01 | 0.16 | 0.00 | 661 |
| mm | 421.65 [421.51, 431.29] | [421.51, 431.29] | 439.52 [437.33, 442.88] | 440.73 | 25.75 | 290.90 | 105.00 | 77.69 | 0.00 | 18115 |
| mm_esc | 430.95 [423.27, 436.38] | [423.27, 436.38] | 441.65 [427.90, 466.17] | 451.46 | 25.60 | 296.10 | 107.97 | 80.48 | 0.00 | 18783 |

## Transport: http_stateless

_as http, but a fresh httpx client (new TCP connection), a fresh ClientSession (initialize, new Mcp-Session-Id) and a session close for EVERY challenge and EVERY call (4 HTTP exchanges + connection setup per rpc); clientInfo is the SDK default, identical for all clients_

| mode | total median [range] | CI95 | total p95 [range] | pooled p95 | challenge RTT | prep | call RTT | verify (in tool) | session setup+close | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 15.39 [15.21, 17.70] | [15.21, 17.70] | 16.86 [16.83, 23.45] | 21.46 | 0.00 | 0.00 | 15.39 | 0.00 | 8.21 | 0 |
| jwt_chain | 31.81 [31.40, 32.12] | [31.40, 32.12] | 37.89 [32.88, 40.08] | 37.60 | 15.68 | 0.07 | 15.91 | 0.37 | 16.64 | 1299 |
| batch_tokens | 31.64 [31.31, 32.03] | [31.31, 32.03] | 33.76 [33.37, 35.56] | 34.03 | 15.65 | 0.08 | 15.65 | 0.21 | 16.56 | 381 |
| blind_tokens | 31.53 [31.36, 31.85] | [31.36, 31.85] | 40.40 [35.34, 42.31] | 39.28 | 15.57 | 0.10 | 15.68 | 0.21 | 16.77 | 802 |
| mm | 404.46 [400.25, 404.92] | [400.25, 404.92] | 410.57 [405.68, 431.93] | 419.39 | 16.43 | 291.20 | 96.32 | 77.54 | 18.78 | 18115 |

## Cost of `http_stateless` vs `http` (same mode, same run)

Added = median total (stateless) - median total (http), per run; then median [range] and bootstrap CI over the 3 runs.

| mode | added ms median [range] | CI95 | ratio stateless/http | session setup+close ms (per call, both rpcs) |
|---|---:|---:|---:|---:|
| none | 12.32 [12.25, 14.73] | [12.25, 14.73] | 5.27 [4.89, 5.97] | 8.19 [8.18, 9.34] |
| jwt_chain | 25.40 [25.14, 25.72] | [25.14, 25.72] | 5.01 [4.96, 5.02] | 16.70 [16.34, 17.17] |
| batch_tokens | 25.55 [25.06, 25.64] | [25.06, 25.64] | 5.01 [5.01, 5.20] | 16.66 [16.48, 16.93] |
| blind_tokens | 25.24 [25.06, 25.52] | [25.06, 25.52] | 5.03 [4.87, 5.12] | 16.78 [16.77, 16.81] |
| mm | 25.67 [22.90, 28.74] | [22.90, 28.74] | 1.07 [1.06, 1.08] | 18.69 [18.50, 19.09] |

## Delegation / issuance cost before calls (two hops)

`all chains` = median [min, max] over every timed two-hop chain of every (transport, run); `per run` = median of per-run medians [range]. Issuance details: median over all (transport, run) configs.

| mode | all chains ms | per run ms | details (median) |
|---|---:|---:|---|
| none | 0.000 [0.000, 0.000] (n=12) | 0.000 [0.000, 0.000] |  |
| jwt_chain | 0.060 [0.058, 0.249] (n=600) | 0.060 [0.059, 0.060] | hop1_issuer_sign_ms=0.029, hop2_agent1_sign_ms=0.030, reps=50 |
| biscuit | 0.157 [0.154, 0.554] (n=450) | 0.157 [0.157, 0.158] | authority_block_issuer_ms=0.050, hop1_attenuation_block_ms=0.053, hop2_attenuation_block_ms=0.054, reps=50 |
| macaroon | 0.008 [0.008, 0.106] (n=450) | 0.008 [0.008, 0.008] | root_mint_ms=0.004, hop1_caveat_ms=0.002, hop2_caveat_ms=0.002, reps=50 |
| batch_tokens | 0.059 [0.058, 0.345] (n=600) | 0.059 [0.059, 0.060] | hop1_issuer_sign_ms=0.029, hop2_agent1_sign_ms=0.030, reps=50, batch_size=240, agent_keygen_and_request_ms=6.934, issuer_chain_check_ms=1.857, issuer_sign_batch_ms=8.983, issuance_total_ms=17.762, per_token_issuance_ms=0.074, per_token_issuer_sign_ms=0.037, per_token_agent_keygen_ms=0.029 |
| blind_tokens | 0.060 [0.059, 0.169] (n=600) | 0.060 [0.059, 0.060] | hop1_issuer_sign_ms=0.029, hop2_agent1_sign_ms=0.030, reps=50, batch_size=240, variant=pop, agent_keygen_blind_and_request_ms=143.125, issuer_chain_check_ms=2.536, issuer_blind_sign_batch_ms=1707.695, agent_finalize_batch_ms=8.254, issuance_total_ms=1862.764, per_token_issuance_ms=7.762, per_token_agent_keygen_blind_ms=0.596, per_token_issuer_blind_sign_ms=7.115, per_token_agent_finalize_ms=0.034 |
| blind_tokens_bearer | 0.060 [0.059, 0.149] (n=450) | 0.060 [0.060, 0.060] | hop1_issuer_sign_ms=0.029, hop2_agent1_sign_ms=0.030, reps=50, batch_size=240, variant=bearer, agent_keygen_blind_and_request_ms=134.636, issuer_chain_check_ms=2.571, issuer_blind_sign_batch_ms=1713.156, agent_finalize_batch_ms=8.152, issuance_total_ms=1860.451, per_token_issuance_ms=7.752, per_token_agent_keygen_blind_ms=0.561, per_token_issuer_blind_sign_ms=7.138, per_token_agent_finalize_ms=0.034 |
| mm | 4008.029 [3961.457, 4135.497] (n=60) | 4004.662 [4000.951, 4037.697] | hop1_parent_ms=1687.915, hop1_issuer_ms=312.137, hop1_wall_ms=2004.351, hop2_parent_ms=1688.676, hop2_issuer_ms=311.815, hop2_wall_ms=2001.491, reps=5, authority_setup_ms=38.457, intervals={'root': [0, 100000, 50000], 'agent1': [90000, 100000, 95000], 'agent2': [95000, 100000, 100000]} |
| mm_esc | 4058.927 [3994.173, 4399.644] (n=45) | 4065.901 [4040.277, 4070.432] | hop1_parent_ms=1697.434, hop1_issuer_ms=313.885, hop1_wall_ms=2012.018, hop2_parent_ms=1696.145, hop2_issuer_ms=313.722, hop2_wall_ms=2011.486, reps=5, authority_setup_ms=39.228, intervals={'root': [0, 100000, 50000], 'agent1': [90000, 100000, 95000], 'agent2': [95000, 100000, 100000]} |

## Negative controls (accepted? identical in all 3 runs unless marked MIXED)

Expected: everything rejected except `none`; `macaroon`, `blind_tokens` and `blind_tokens_bearer` have no revocation mechanism (ACCEPTED after revocation is the honest, expected outcome); `blind_tokens_bearer` only has bearer-level call binding (tampered call ACCEPTED expected). `tampered call` = on-path attacker takes a fresh, unused authorisation and changes `amt` (resp. `cur`), rewriting only unsigned fields. `after revocation` = authorisation prepared, then agent1's delegation revoked and the status list / new accumulator pushed to the tool, then sent. `wallet after revocation` (MM only) = the agent tries to produce a new presentation with the revoked sub-mandate.

| transport | mode | replay same | replay other | replay same + fresh nonce | replay other + fresh nonce | tampered amt | tampered cur | after revocation | wallet after revocation |
|---|---|---|---|---|---|---|---|---|---|
| stdio | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| stdio | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| stdio | biscuit | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| stdio | macaroon | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| stdio | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| stdio | blind_tokens | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| stdio | blind_tokens_bearer | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| stdio | mm | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| stdio | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| http | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| http | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http | biscuit | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http | macaroon | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| http | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http | blind_tokens | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| http | blind_tokens_bearer | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| http | mm | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| http | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| http_delay10 | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http_delay10 | biscuit | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http_delay10 | macaroon | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| http_delay10 | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http_delay10 | blind_tokens | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| http_delay10 | blind_tokens_bearer | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| http_delay10 | mm | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |
| http_stateless | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED | ACCEPTED | n/a |
| http_stateless | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http_stateless | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected | rejected | n/a |
| http_stateless | blind_tokens | rejected | rejected | rejected | rejected | rejected | rejected | ACCEPTED | n/a |
| http_stateless | mm | rejected | rejected | rejected | rejected | rejected | rejected | rejected | rejected |

## What each tool verifies, and what the issuer learns

| mode | property | value |
|---|---|---|
| none | signature_chain | no |
| none | attenuation | no |
| none | per_call_binding | no |
| none | replay | no |
| none | expiry | no |
| none | revocation_status | no |
| none | rate_limit | no |
| none | unlinkable_across_tools | no |
| none | unlinkable_vs_issuer | no |
| none | accountability_escrow | no |
| none | issuer_learns | no issuer |
| none | notes | No authorisation; no challenge fetched. |
| jwt_chain | signature_chain | yes: issuer-signed root JWT + agent1-signed delegation JWT, cnf-key linkage and prev-hash |
| jwt_chain | attenuation | yes: tool checks scope subset, budget and exp monotone along the chain |
| jwt_chain | per_call_binding | yes: PoP JWT by the leaf cnf key over SHA-256(JCS call incl. currency), aud=tool identity, tool nonce, tool time |
| jwt_chain | replay | yes: tool nonce single-use + seen-set of PoP hashes |
| jwt_chain | expiry | yes: exp of every JWT (pyjwt) and t <= leaf exp |
| jwt_chain | revocation_status | yes (added): in-memory status list of mandate jti pushed by the issuer |
| jwt_chain | rate_limit | no (not implemented; feasible because calls are linkable) |
| jwt_chain | unlinkable_across_tools | no: identical chain shown to every tool |
| jwt_chain | unlinkable_vs_issuer | no (only if tools share logs with the issuer; see issuer_learns) |
| jwt_chain | accountability_escrow | in the clear (tool learns principal and agents) |
| jwt_chain | issuer_learns | Directly: only the root it signs (principal, agent1's key, root scope/budget/exp, jti, time). It does NOT see the agent1->agent2 delegation (signed offline by agent1) nor any call. But every tool receives the whole chain in the clear (principal, both agents' keys, jtis), so any tool that shares its logs with the issuer (or with other tools) links every call to the principal and both agents. |
| biscuit | signature_chain | yes: authority block (issuer root key) + 2 attenuation blocks + per-call block (Ed25519 chain) |
| biscuit | attenuation | yes: every block's checks must hold (class, amount, time) |
| biscuit | per_call_binding | partial: last block binds call hash, tool identity and nonce; bearer token, no PoP: whoever holds the pre-call token can append a block for any call |
| biscuit | replay | yes: tool nonce single-use + seen-set |
| biscuit | expiry | yes: time checks against tool time |
| biscuit | revocation_status | yes (added): revocation_ids of the token checked against a pushed list |
| biscuit | rate_limit | no |
| biscuit | unlinkable_across_tools | no: same token prefix/revocation ids everywhere |
| biscuit | unlinkable_vs_issuer | no (with tool collusion) |
| biscuit | accountability_escrow | in the clear (delegate facts) |
| biscuit | issuer_learns | Directly: the authority block it mints (principal, rights, bounds) and when. Attenuation and per-call blocks are appended offline. Tools see all blocks and revocation ids in the clear, so issuer + any tool links every call to the root token and the delegate names. |
| macaroon | signature_chain | HMAC chain only; the tool must hold the issuer's root HMAC key (shared secret, it can mint mandates) |
| macaroon | attenuation | yes: both delegation caveats checked (class, amount, exp) |
| macaroon | per_call_binding | partial: caveats on call hash, tool identity, nonce; bearer, no PoP |
| macaroon | replay | yes: tool nonce single-use + seen-set |
| macaroon | expiry | yes: exp caveats vs tool time |
| macaroon | revocation_status | no |
| macaroon | rate_limit | no |
| macaroon | unlinkable_across_tools | no: same identifier/signature chain |
| macaroon | unlinkable_vs_issuer | no |
| macaroon | accountability_escrow | in the clear (caveats) |
| macaroon | issuer_learns | Directly: the root identifier and principal it mints, and when; caveats are added offline. Every tool holds the root key (it is an issuer) and sees the identifier and all caveats, so any tool alone links all calls of the mandate. |
| batch_tokens | signature_chain | at issuance only: issuer verifies the JWT chain in the clear; tool checks one issuer Ed25519 signature |
| batch_tokens | attenuation | at issuance only (class set and budget tier copied from the chain leaf); tool checks class and amount <= tier |
| batch_tokens | per_call_binding | yes: PoP by the per-token cnf key over SHA-256(JCS call), tool identity, tool nonce, tool time |
| batch_tokens | replay | yes: tool nonce single-use + seen-set of token ids (per tool; class metadata pins a token to one tool here) |
| batch_tokens | expiry | epoch granularity only |
| batch_tokens | revocation_status | yes (added): status list of token ids (issuer pushes all ids of the revoked delegation) |
| batch_tokens | rate_limit | issuer-side only (batch size per epoch); tools cannot enforce per-agent limits |
| batch_tokens | unlinkable_across_tools | yes (fresh token and key per call) unless tools collude with the issuer |
| batch_tokens | unlinkable_vs_issuer | no: issuer saw every token id and cnf key with the agent identity |
| batch_tokens | accountability_escrow | via issuer log (token id -> agent), not threshold |
| batch_tokens | issuer_learns | At every issuance: the full delegation chain in the clear (principal, agent1, agent2, scopes, budgets, expiries), the request time, the number of tokens per class and epoch, and every token id and cnf public key. Not the calls themselves; but any token a tool reports back is linked by the issuer to the agent and principal (no unlinkability against issuer + tool collusion). |
| blind_tokens | signature_chain | at issuance only: issuer verifies the JWT chain in the clear; tool checks one RSA-PSS signature |
| blind_tokens | attenuation | at issuance only via key choice (one key per class/tier/epoch); tool checks class and amount <= tier |
| blind_tokens | per_call_binding | yes (PoP, added in v2.1): the blind-signed message commits to SHA-256 of a fresh per-token Ed25519 key; at redemption the agent reveals the key and signs (SHA-256(JCS call), tool identity, tool nonce, tool time); an intercepted unused token cannot be attached to another call |
| blind_tokens | replay | yes: tool nonce single-use + seen-set of token randoms (per tool) |
| blind_tokens | expiry | epoch granularity (key rotation) |
| blind_tokens | revocation_status | no (issued tokens valid until epoch end) |
| blind_tokens | rate_limit | issuer-side only (batch size per epoch) |
| blind_tokens | unlinkable_across_tools | yes |
| blind_tokens | unlinkable_vs_issuer | yes up to public metadata (blind issuance; the PoP key is inside the blinded message) |
| blind_tokens | accountability_escrow | no |
| blind_tokens | issuer_learns | At every issuance: the full delegation chain in the clear (principal, agents, scope, budget, exp), the request time, and the number of tokens per class/tier/epoch (public metadata, via the key choice). Not the token messages, token ids or PoP keys (blinded), and not the calls. With tool collusion, a redeemed token links back only through its public metadata and timing, i.e. within the set of tokens issued under the same key in that epoch; small anonymity sets or distinctive batch sizes/timing de-anonymise. |
| mm | signature_chain | yes, hidden: ZK proof of an issuer BBS+ signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation |
| mm | attenuation | enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK |
| mm | per_call_binding | yes: proof bound to (tool identity, JCS call incl. currency, class, amt, cur, epoch, tool time, tool nonce) |
| mm | replay | yes: strict tool (v2.1): own single-use nonce, epoch == tool epoch, |t - now| <= 300 s, per-tool per-epoch pseudonym seen-set |
| mm | expiry | yes: t <= exp proven in ZK with the tool's time |
| mm | revocation_status | yes: accumulator non-membership of the mandate id and its ancestors (public params update, grace = 0); the v2.1 wallet also refuses to present with a revoked/stale mandate |
| mm | rate_limit | yes: per tool per epoch via Dodis-Yampolskiy pseudonyms with a hidden counter in the mandate's interval; children get disjoint intervals carved from the parent (subtree-wide cap per root) |
| mm | unlinkable_across_tools | yes |
| mm | unlinkable_vs_issuer | yes (for calls); see issuer_learns |
| mm | accountability_escrow | no |
| mm | issuer_learns | At root issuance: the principal's registered label (uid binding), the root's attributes (classes, cap, counter interval, expiry, given in the clear to the issuer), the root id it chooses, and the time. At each delegation (src/lib.rs deleg_issue): that a delegation happened in this epoch and when, the fresh id it assigns, and a delegation pseudonym (DY PRF of the subtree secret and a hidden counter); the parent, its root and the child's attributes stay hidden (committed, attenuation proven in ZK). None of the calls. With tool collusion, presentations show only per-tool per-epoch pseudonyms and the accumulator value, so calls do not link to root or mandate ids except by timing. When it revokes, the issuer knows the revoked id (it assigned it) but not which calls it made. |
| mm_esc | signature_chain | yes, hidden: ZK proof of an issuer BBS+ signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation |
| mm_esc | attenuation | enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK |
| mm_esc | per_call_binding | yes: proof bound to (tool identity, JCS call incl. currency, class, amt, cur, epoch, tool time, tool nonce) |
| mm_esc | replay | yes: strict tool (v2.1): own single-use nonce, epoch == tool epoch, |t - now| <= 300 s, per-tool per-epoch pseudonym seen-set |
| mm_esc | expiry | yes: t <= exp proven in ZK with the tool's time |
| mm_esc | revocation_status | yes: accumulator non-membership of the mandate id and its ancestors (public params update, grace = 0); the v2.1 wallet also refuses to present with a revoked/stale mandate |
| mm_esc | rate_limit | yes: per tool per epoch via Dodis-Yampolskiy pseudonyms with a hidden counter in the mandate's interval; children get disjoint intervals carved from the parent (subtree-wide cap per root) |
| mm_esc | unlinkable_across_tools | yes |
| mm_esc | unlinkable_vs_issuer | yes (for calls); see issuer_learns |
| mm_esc | accountability_escrow | yes: 2-of-3 threshold escrow (g^u, g^id), verified by the tool |
| mm_esc | issuer_learns | At root issuance: the principal's registered label (uid binding), the root's attributes (classes, cap, counter interval, expiry, given in the clear to the issuer), the root id it chooses, and the time. At each delegation (src/lib.rs deleg_issue): that a delegation happened in this epoch and when, the fresh id it assigns, and a delegation pseudonym (DY PRF of the subtree secret and a hidden counter); the parent, its root and the child's attributes stay hidden (committed, attenuation proven in ZK). None of the calls. With tool collusion, presentations show only per-tool per-epoch pseudonyms and the accumulator value, so calls do not link to root or mandate ids except by timing. When it revokes, the issuer knows the revoked id (it assigned it) but not which calls it made. Additionally, 2 of the 3 escrow members together can open g^u and g^id of any escrowed presentation a tool hands them (accountability by design). |
| mm_esc | notes | as mm, plus verifiable threshold escrow of the principal identity and mandate id (tool requires the escrow ciphertext) |
| blind_tokens_bearer | signature_chain | at issuance only: issuer verifies the JWT chain in the clear; tool checks one RSA-PSS signature |
| blind_tokens_bearer | attenuation | at issuance only via key choice (one key per class/tier/epoch); tool checks class and amount <= tier |
| blind_tokens_bearer | per_call_binding | weak (e2v2 variant, kept for comparison): bearer token next to a plain call_hash field; tool nonce prevents re-use after redemption but an on-path attacker holding an unused token can attach it to any call of that class (tampered_call control) |
| blind_tokens_bearer | replay | yes: tool nonce single-use + seen-set of token randoms (per tool) |
| blind_tokens_bearer | expiry | epoch granularity (key rotation) |
| blind_tokens_bearer | revocation_status | no (issued tokens valid until epoch end) |
| blind_tokens_bearer | rate_limit | issuer-side only (batch size per epoch) |
| blind_tokens_bearer | unlinkable_across_tools | yes |
| blind_tokens_bearer | unlinkable_vs_issuer | yes up to public metadata (blind issuance) |
| blind_tokens_bearer | accountability_escrow | no |
| blind_tokens_bearer | issuer_learns | At every issuance: the full delegation chain in the clear (principal, agents, scope, budget, exp), the request time, and the number of tokens per class/tier/epoch (public metadata, via the key choice). Not the token messages, token ids or PoP keys (blinded), and not the calls. With tool collusion, a redeemed token links back only through its public metadata and timing, i.e. within the set of tokens issued under the same key in that epoch; small anonymity sets or distinctive batch sizes/timing de-anonymise. |

## Not implemented

- ARC (Anonymous Rate-limited Credentials) and anonymous counting tokens (ACT) are NOT implemented in this harness and were not measured; no numbers in this file refer to them. They are the closest deployed-track designs to MM's per-tool rate limiting; comparing against them remains future work.

## Limitations / deviations

- Blind tokens: RFC 9474 RSABSSA-SHA384-PSS-Randomized (2048-bit), client and issuer operations in pure Python (issuer BlindSign uses CRT big-int pow, no GMP), so issuance is pessimistic; tools verify RSA-PSS with OpenSSL. Not checked against the RFC test vectors (every finalized token is checked by OpenSSL PSS verification). Public metadata bound by one issuer key per (variant, class, tier, epoch); RSA keys derived deterministically from the run seed.
- PoP blind tokens follow the standard key-binding pattern (token commits to a key hash; the key signs the call); the per-token Ed25519 key is generated at issuance time (counted in the agent's issuance cost) and revealed once, at redemption.
- Status lists (jwt_chain, batch_tokens) and biscuit revocation ids are pushed through an unauthenticated experiment-only `admin_update` tool; MM public parameters (new accumulator) are pushed the same way.
- Macaroon tools hold the issuer's root HMAC key (they could mint mandates).
- Replay seen-sets and nonce stores are per tool, in memory; token double-spend across tools is prevented only because class metadata maps 1:1 to tools. MM nonces live in the Rust strict tool (no TTL; the 300 s time tolerance bounds use).
- MM strict-mode rejections carry the uniform reason `rejected` (debug off), so the controls table shows only accept/reject for MM.
- http_stateless removes the MCP session id and the TCP connection as linking handles; it does not hide the client's IP address (all 127.0.0.1 here), TLS session resumption (no TLS here) or timing. The default clientInfo is the same for all clients.
- The 10 ms delay is a userspace TCP relay (per forwarded chunk, each direction), not netem; TCP handshakes are not delayed.
- `none` fetches no challenge. Other-mode delegation timing: median of 50 builds; MM: 5 two-hop chains per (transport, run).
- 3 runs give a coarse between-run CI; all runs on one Mac (Apple Silicon, see platform), other user processes not stopped (load averages above).
