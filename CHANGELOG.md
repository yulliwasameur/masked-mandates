# Changelog

## 2.2.1 (14/11/2026), DOI 10.5281/zenodo.24222783

Revised scheme (version 2.2 of the construction) and complete re-run of every experiment, after internal review rounds and an external review. Versions 2.0.0 to 2.2.0 were never published; 2.2.1 is the first published 2.x release.
- **External review (v2.2.0 and v2.2.1, 14/11/2026):**
  - Revocation authorization at the log (`System::revoke_authorized`, `RevocationAuth`): an anonymous BBS+ proof made with the credential of the revoked mandate itself (its holder, or the parent that keeps the child credential it obtained when delegating; since v2.2.1 never a descendant, which could otherwise revoke its ancestor and its siblings), or Schnorr signatures of two distinct committee members; single-use log nonces; identifier 0 is never revocable.
  - mmpy: a released counter is bound to the call it was reserved for (`release_counter`, `retry_state()`).
  - Benchmark layout fixed to L = 13 + n signed messages (29 for n = 16).
  - Attack suite: 96 attacks (class REV, rejecting party "log") and 37 checks.
  - E1 re-run on v2.2.0 (`results/v22/`): three Zen campaigns, multi-core, laptop. A first run of campaign 1 (job 1680010, node068) was uniformly 1.51x slower on every operation and was excluded under a rule fixed before its rerun (job 1680015, node005); it is kept in `results/v22/zen/excluded_node068/`.
- **Third round (v2.2, 14/11/2026):**
  - Issuer: checks the attribute layout of root requests (closes a reviewer's layout-shift attack that evaded Q and tracing), bounds root intervals by Q = 2^20, limits roots per principal.
  - Wallets verify every non-membership witness on receipt and after refresh; Judge takes the registry from outside the issuer (`judge_with`).
  - Verifier class-index check; tool-side time-bounded grace window and wallet retry (mmpy).
  - 82 attacks (7 malicious-delegator attacks with positive and negative controls, layout shift, root limit, key substitution, tampered update data) and 33 checks; public spot check of accumulator updates.
  - Experiments: E3 v2.2 (recalibrated on E4 v2.1, load sweep, issuer attacker, decoupled identity calls); E4 v2.2 (dishonest wallet, retry, time window, sparse revocations; scripted agent and five LLMs).
  - Generators: `gen_e3v22.py`, `gen_e4v22.py`; manifest `results/SHA256SUMS-v2.2`.
- **Second round (v2.1):**
  - Proof-system and accumulator parameters are derived from public labels, which closes a de-anonymisation by an issuer that chose the accumulator proving key.
  - Per-root tag bound by the principal's Schnorr signature; delegates never receive the principal's long-term key.
  - Signed counter intervals with disjoint sub-intervals for children.
  - The issuer and the tools fix epochs, time and single-use nonces.
  - Accumulator grace window; atomic seen-set reservation; currency in the invocation.
  - Pedersen-VSS DKG; Judge lookup by hash map; uniform tool errors; the wallet refuses stale mandates.
  - 70 attacks and 21 checks.
  - Experiments re-run: E1 (Zen x3 + multi-core + laptop), E2 (3 runs, stateless HTTP, PoP blind tokens), E3 (5 seeds, identified-tool attacker, coalitions), E4 (replication, binding quota, shared issuer).
  - Generator: `code/gen_tex_v21.py`.
- **First round (v2):**
- **Scheme (`code/src/lib.rs`).**
  - Shared domain issuer; the signed uid is the principal's registered secret u, committed blindly with a proof u = log_g pk_u.
  - The issuer chooses every mandate identifier.
  - The link secret is inherited by the whole delegation tree, with a hidden counter (Dodis–Yampolskiy pseudonym); quotas are per root, tool and epoch.
  - Escrow of (g^u, g^id) under a 2-of-3 Feldman DKG.
  - Domain-separated hashes; authenticated tool identity "origin|name"; tool-issued nonce; RFC 8785 call canonicalisation.
  - Public-only serialisable verifier; guarded parsing.
- **Attack suite (`code/src/bin/attacks.rs`).** 62 attacks with a taxonomy (threat x rejecting party), including 6 malicious-prover attacks, 2,000 bit-flip mutations and parser tests; 18 correctness checks.
- **E1 (`code/src/bin/bench.rs`).**
  - Warm-up, n >= 30, verification from bytes, ablation, throughput.
  - Three independent campaigns on an AMD EPYC core (MesoNET Zen, `results/zen/`) and one on an Apple M5 Pro core (`results/mac/`).
- **E2 v2 (`code/e2v2/`).** Streamable HTTP and delayed transport; tool nonce; JWT chain, Biscuit, macaroon, batch one-time tokens and RFC 9474 blind tokens.
- **E3 v2 (`code/sim/e3v2.py`).** Content, intersection and timing attackers; 100 to 10,000 users; sensitivity analysis.
- **E4 v2 (`code/e4v2/`).**
  - 96 tasks, including delegation to a sub-agent and revocation in the middle of a task.
  - Injected tool latency; T = 0 and T = 0.7 with three seeds; single-core authorisation.
- **Tooling.** Python bindings with separated roles (`Authority`, public-only `Verifier`); `code/gen_tex_v2.py` generates every number, table and figure of the revised paper.
- **Unchanged.** Version 1.0.x results stay in `code/results/` (e1_*.json, e2.json, e3.json, e4/) for reference; `code/gen_tex.py` still regenerates the first paper.

## 1.0.3 (2026-11-13)

- Metadata only: the paper now has three authors (Y. Ameur, S. Bouzefrane, S. Banerjee) and is submitted to
  IEEE Open Journal of the Computer Society; `CITATION.cff`, `.zenodo.json` and `README.md` are updated.
  The paper cites version 1.0.2 (DOI 10.5281/zenodo.24182546).
- No change to code, results or generated files.

## 1.0.2 (2026-11-13)

- New experiment E4: a real LLM agent in the loop (`code/e4/e4.py`, Slurm job `code/e4/hedy_e4.sbatch`).
  Six open models served by vLLM 0.33.0 on one H100 (MesoNET Hedy): Qwen2.5-7B-Instruct, Hermes-3-Llama-3.1-8B,
  Granite-3.3-8B-Instruct, gpt-oss-20b, Mistral-Small-3.2-24B-Instruct-2506, Qwen2.5-72B-Instruct-AWQ;
  24 tasks x 2 repetitions x 3 modes (none, jwt, Masked Mandates).
- Results in `code/results/e4/` with their own `SHA256SUMS`; diagnostic runs in `code/results/e4/debug/`.
- `code/gen_tex.py` also generates `tab_e4.tex` and the `\EFour...` macros; all other generated files are unchanged.
- No change to the scheme, the attack suite or the E1-E3 results.

## 1.0.1 (2026-11-12)

- `code/results/SHA256SUMS` now lists only the shipped result files, so that
  `cd code && shasum -a 256 -c results/SHA256SUMS` passes. Version 1.0.0 still listed
  `attacks_avant_correctif_bouclage.json` (renamed `attacks_before_wraparound_fix.json`,
  same content and hash) and the two campaign binaries, which are not shipped.
- The hashes of the campaign binaries move to `code/results/binaries-SHA256.txt`.
- `run_campaign.sh` writes the two files separately.
- No change to the code, the result files or the generated tables and figures.

## 1.0.0 (2026-11-12)

- Version archived on Zenodo (DOI 10.5281/zenodo.24148363) and cited in the paper.
