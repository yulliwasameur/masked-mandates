# E2 v2 -- end-to-end MCP authorisation (summary)

Seed 20261109; 200 measured calls after 15 warm-up calls per (mode, transport), round-robin over airline, hotel, payment; RAYON_NUM_THREADS=1; MCP SDK 1.30.0; Python 3.13.16; macOS-26.7.1-arm64-arm-64bit-Mach-O.

Load at start: `11:06  up 2 days, 13:08, 1 user, load averages: 6.38 4.95 4.32`  
Load at end: `11:18  up 2 days, 13:20, 1 user, load averages: 6.02 6.05 5.11`

Every authorised call = `challenge` round trip (tool-issued single-use nonce + tool time) + agent preparation + the tool call. Times in ms (median / p95). `verify` is measured inside the tool server (includes nonce lookup). `bytes` = JCS-serialised `_meta` authorisation material per call.

## Transport: stdio

_MCP stdio, one subprocess per tool server_

| mode | total med | total p95 | challenge RTT med | prep med | call RTT med | verify med | verify p95 | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 1.51 | 2.04 | 0.00 | 0.00 | 1.51 | 0.00 | 0.00 | 0 |
| jwt_chain | 4.17 | 5.08 | 1.83 | 0.07 | 2.21 | 0.37 | 0.57 | 1296 |
| biscuit | 3.68 | 7.94 | 1.70 | 0.09 | 1.85 | 0.29 | 0.49 | 1575 |
| macaroon | 3.63 | 7.63 | 1.74 | 0.07 | 1.76 | 0.11 | 0.19 | 574 |
| batch_tokens | 3.32 | 4.21 | 1.57 | 0.06 | 1.65 | 0.20 | 0.23 | 381 |
| blind_tokens | 3.01 | 3.87 | 1.52 | 0.00 | 1.50 | 0.08 | 0.11 | 654 |
| mm | 373.36 | 377.00 | 1.92 | 292.03 | 79.46 | 77.10 | 78.21 | 17846 |
| mm_esc | 377.15 | 382.00 | 1.93 | 293.73 | 81.51 | 79.15 | 80.66 | 18510 |

## Transport: http

_MCP streamable HTTP over 127.0.0.1, one FastMCP server process per tool (distinct ports)_

| mode | total med | total p95 | challenge RTT med | prep med | call RTT med | verify med | verify p95 | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 2.98 | 3.49 | 0.00 | 0.00 | 2.98 | 0.00 | 0.00 | 0 |
| jwt_chain | 6.48 | 7.52 | 3.06 | 0.05 | 3.31 | 0.35 | 0.38 | 1299 |
| biscuit | 6.74 | 7.75 | 3.16 | 0.09 | 3.39 | 0.30 | 0.33 | 1579 |
| macaroon | 6.63 | 7.67 | 3.19 | 0.07 | 3.30 | 0.11 | 0.12 | 576 |
| batch_tokens | 6.53 | 7.71 | 3.14 | 0.07 | 3.25 | 0.20 | 0.21 | 381 |
| blind_tokens | 6.29 | 7.33 | 3.11 | 0.00 | 3.11 | 0.09 | 0.11 | 654 |
| mm | 377.51 | 380.84 | 3.86 | 291.61 | 81.85 | 76.95 | 78.63 | 17846 |
| mm_esc | 381.59 | 391.34 | 3.86 | 293.51 | 84.07 | 79.18 | 81.25 | 18510 |

## Transport: http_delay10

_as http, through a per-server TCP relay process adding 10 ms one-way delay to every forwarded chunk in each direction (RTT +20 ms per HTTP exchange)_

| mode | total med | total p95 | challenge RTT med | prep med | call RTT med | verify med | verify p95 | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 26.43 | 28.36 | 0.00 | 0.01 | 26.41 | 0.00 | 0.00 | 0 |
| jwt_chain | 52.58 | 54.20 | 27.31 | 0.08 | 25.20 | 0.38 | 0.49 | 1299 |
| biscuit | 55.93 | 117.34 | 28.95 | 0.14 | 27.04 | 0.40 | 0.61 | 1579 |
| macaroon | 53.38 | 55.31 | 27.87 | 0.09 | 25.36 | 0.12 | 0.15 | 576 |
| batch_tokens | 52.88 | 54.70 | 27.65 | 0.09 | 25.29 | 0.22 | 0.28 | 381 |
| blind_tokens | 53.04 | 55.14 | 27.73 | 0.01 | 25.35 | 0.12 | 0.15 | 654 |
| mm | 422.20 | 482.47 | 27.78 | 288.84 | 105.72 | 76.31 | 88.76 | 17846 |
| mm_esc | 421.70 | 466.65 | 25.91 | 290.02 | 105.52 | 78.13 | 86.28 | 18510 |

## Delegation / issuance cost before calls (two hops; from the first transport's run)

| mode | two-hop delegation ms | issuance details |
|---|---:|---|
| none | 0.000 |  |
| jwt_chain | 0.060 | hop1_issuer_sign_ms=0.029, hop2_agent1_sign_ms=0.030, reps=50 |
| biscuit | 0.159 | authority_block_issuer_ms=0.050, hop1_attenuation_block_ms=0.054, hop2_attenuation_block_ms=0.054, reps=50 |
| macaroon | 0.009 | root_mint_ms=0.004, hop1_caveat_ms=0.002, hop2_caveat_ms=0.002, reps=50 |
| batch_tokens | 0.060 | hop1_issuer_sign_ms=0.030, hop2_agent1_sign_ms=0.031, reps=50, batch_size=240, agent_keygen_and_request_ms=6.172, issuer_chain_check_ms=1.740, issuer_sign_batch_ms=8.709, issuance_total_ms=16.621, per_token_issuance_ms=0.069, per_token_issuer_sign_ms=0.036, per_token_agent_keygen_ms=0.026 |
| blind_tokens | 0.068 | hop1_issuer_sign_ms=0.033, hop2_agent1_sign_ms=0.035, reps=50, batch_size=240, agent_blind_and_request_ms=151.302, issuer_chain_check_ms=3.258, issuer_blind_sign_batch_ms=1784.940, agent_finalize_batch_ms=13.215, issuance_total_ms=1952.715, per_token_issuance_ms=8.136, per_token_agent_blind_ms=0.630, per_token_issuer_blind_sign_ms=7.437, per_token_agent_finalize_ms=0.055 |
| mm | 3748.633 | hop1_parent_ms=1581.589, hop1_issuer_ms=289.130, hop1_wall_ms=1872.439, hop2_parent_ms=1585.835, hop2_issuer_ms=292.392, hop2_wall_ms=1876.194, reps=3, authority_setup_ms=37.249 |
| mm_esc | 3736.496 | hop1_parent_ms=1572.729, hop1_issuer_ms=292.218, hop1_wall_ms=1865.268, hop2_parent_ms=1578.412, hop2_issuer_ms=290.607, hop2_wall_ms=1871.228, reps=3, authority_setup_ms=30.079 |

## Negative controls (accepted?)

Expected: everything rejected except `none`; by design `macaroon` and `blind_tokens` have no revocation mechanism and `blind_tokens` only has bearer-level call binding, so ACCEPTED there is the honest, expected outcome. `tampered call` = on-path attacker takes a fresh, unused authorisation and changes `amt` (rewriting only unsigned fields). `after revocation` = authorisation prepared, then agent1's delegation revoked and the status list / new public params pushed to the tool, then the authorisation is sent.

| transport | mode | replay same | replay other | replay same + fresh nonce | replay other + fresh nonce | tampered call | after revocation |
|---|---|---|---|---|---|---|---|
| stdio | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED |
| stdio | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected |
| stdio | biscuit | rejected | rejected | rejected | rejected | rejected | rejected |
| stdio | macaroon | rejected | rejected | rejected | rejected | rejected | ACCEPTED |
| stdio | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected |
| stdio | blind_tokens | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED |
| stdio | mm | rejected | rejected | rejected | rejected | rejected | rejected |
| stdio | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected |
| http | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED |
| http | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected |
| http | biscuit | rejected | rejected | rejected | rejected | rejected | rejected |
| http | macaroon | rejected | rejected | rejected | rejected | rejected | ACCEPTED |
| http | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected |
| http | blind_tokens | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED |
| http | mm | rejected | rejected | rejected | rejected | rejected | rejected |
| http | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | none | ACCEPTED | ACCEPTED | n/a | n/a | ACCEPTED | ACCEPTED |
| http_delay10 | jwt_chain | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | biscuit | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | macaroon | rejected | rejected | rejected | rejected | rejected | ACCEPTED |
| http_delay10 | batch_tokens | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | blind_tokens | rejected | rejected | rejected | rejected | ACCEPTED | ACCEPTED |
| http_delay10 | mm | rejected | rejected | rejected | rejected | rejected | rejected |
| http_delay10 | mm_esc | rejected | rejected | rejected | rejected | rejected | rejected |

## What each tool actually verifies

| mode | property | verified |
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
| none | notes | No authorisation; no challenge fetched. |
| jwt_chain | signature_chain | yes: issuer-signed root JWT + agent1-signed delegation JWT, cnf-key linkage and prev-hash |
| jwt_chain | attenuation | yes: tool checks scope subset, budget and exp monotone along the chain |
| jwt_chain | per_call_binding | yes: PoP JWT by the leaf cnf key over SHA-256(JCS call), aud=tool identity, tool nonce, tool time |
| jwt_chain | replay | yes: tool nonce single-use + seen-set of PoP hashes |
| jwt_chain | expiry | yes: exp of every JWT (pyjwt) and t <= leaf exp |
| jwt_chain | revocation_status | yes (added): in-memory status list of mandate jti pushed by the issuer |
| jwt_chain | rate_limit | no (not implemented; feasible because calls are linkable) |
| jwt_chain | unlinkable_across_tools | no: identical chain shown to every tool |
| jwt_chain | unlinkable_vs_issuer | no |
| jwt_chain | accountability_escrow | in the clear (tool learns principal and agents) |
| biscuit | signature_chain | yes: authority block (issuer root key) + 2 attenuation blocks + per-call block (Ed25519 chain) |
| biscuit | attenuation | yes: every block's checks must hold (class, amount, time) |
| biscuit | per_call_binding | partial: last block binds call hash, tool identity and nonce; bearer token, no PoP: whoever holds the pre-call token can append a block for any call |
| biscuit | replay | yes: tool nonce single-use + seen-set |
| biscuit | expiry | yes: time checks against tool time |
| biscuit | revocation_status | yes (added): revocation_ids of the token checked against a pushed list |
| biscuit | rate_limit | no |
| biscuit | unlinkable_across_tools | no: same token prefix/revocation ids everywhere |
| biscuit | unlinkable_vs_issuer | no |
| biscuit | accountability_escrow | in the clear (delegate facts) |
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
| blind_tokens | signature_chain | at issuance only: issuer verifies the JWT chain in the clear; tool checks one RSA-PSS signature |
| blind_tokens | attenuation | at issuance only via key choice (one key per class/tier/epoch); tool checks class and amount <= tier |
| blind_tokens | per_call_binding | weak: bearer token sent next to a plain call_hash field; tool nonce prevents re-use after redemption but an on-path attacker holding an unused token can attach it to any call of that class (demonstrated by the tampered_call control) |
| blind_tokens | replay | yes after redemption: tool nonce + seen-set of token randoms (per tool) |
| blind_tokens | expiry | epoch granularity (key rotation) |
| blind_tokens | revocation_status | no (issued tokens valid until epoch end) |
| blind_tokens | rate_limit | issuer-side only (batch size per epoch) |
| blind_tokens | unlinkable_across_tools | yes |
| blind_tokens | unlinkable_vs_issuer | yes (blind issuance), except public metadata (class, tier, epoch) and batch counts |
| blind_tokens | accountability_escrow | no |
| mm | signature_chain | yes, hidden: ZK proof of an issuer BBS signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation |
| mm | attenuation | enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK |
| mm | per_call_binding | yes: proof bound to SHA-256 of (tool identity, JCS call, class, amt, epoch, tool time, tool nonce) |
| mm | replay | yes: tool nonce single-use + per-tool pseudonym seen-set |
| mm | expiry | yes: t <= exp proven in ZK with tool time |
| mm | revocation_status | yes: accumulator non-membership of the mandate id and its ancestors (public params update) |
| mm | rate_limit | yes: per tool per epoch, k calls via Dodis-Yampolskiy pseudonyms |
| mm | unlinkable_across_tools | yes |
| mm | unlinkable_vs_issuer | yes |
| mm | accountability_escrow | no |
| mm_esc | signature_chain | yes, hidden: ZK proof of an issuer BBS signature on the sub-agent mandate; parent proofs checked by the issuer at each delegation |
| mm_esc | attenuation | enforced by the issuer at delegation (ZK range proofs on the hidden attributes); tool checks class in scope, amt <= budget in ZK |
| mm_esc | per_call_binding | yes: proof bound to SHA-256 of (tool identity, JCS call, class, amt, epoch, tool time, tool nonce) |
| mm_esc | replay | yes: tool nonce single-use + per-tool pseudonym seen-set |
| mm_esc | expiry | yes: t <= exp proven in ZK with tool time |
| mm_esc | revocation_status | yes: accumulator non-membership of the mandate id and its ancestors (public params update) |
| mm_esc | rate_limit | yes: per tool per epoch, k calls via Dodis-Yampolskiy pseudonyms |
| mm_esc | unlinkable_across_tools | yes |
| mm_esc | unlinkable_vs_issuer | yes |
| mm_esc | accountability_escrow | yes: threshold escrow, verified by the tool |
| mm_esc | notes | as mm, plus verifiable threshold escrow of the principal identity (tool requires the escrow ciphertext) |

## Limitations / deviations

- Blind tokens: RFC 9474 RSABSSA-SHA384-PSS-Randomized (2048-bit), client and issuer operations in pure Python (issuer BlindSign uses CRT big-int pow, no GMP), so issuance is pessimistic; tools verify the final RSA-PSS signature with OpenSSL. Not checked against the RFC test vectors (correctness checked by OpenSSL PSS verification of every finalized token). Public metadata bound by one issuer key per (class, tier, epoch); RSA keys are generated deterministically from the seed for reproducibility only.
- Blind tokens are bearer: the call hash travels in a plain field, so binding to the call is only by co-transport (tampered-call control is accepted).
- Status lists (jwt_chain, batch_tokens) and biscuit revocation ids are pushed through an unauthenticated experiment-only `admin_update` tool; MM public parameters (new accumulator) are pushed the same way.
- Macaroon tools hold the issuer's root HMAC key (they could mint mandates).
- Replay seen-sets and nonce stores are per tool, in memory; double-spend of a token across tools is prevented here only because class metadata maps 1:1 to tools.
- The 10 ms delay is a userspace TCP relay (per forwarded chunk, each direction), not netem; TCP handshakes are not delayed (connections kept alive).
- `none` fetches no challenge. MM delegation timing: median of 3 two-hop chains; other modes median of 50.
- The Mac may be shared with other jobs (see load averages).
