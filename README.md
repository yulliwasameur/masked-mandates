# Masked Mandates — artifact

Code, scripts and result files for the paper

> Y. Ameur, *Masked Mandates: Unlinkable, Attenuable and Accountable Delegation for LLM Agents*,
> submitted to IEEE Transactions on Information Forensics and Security, 2026.

Masked Mandates lets an AI agent prove, for one tool call, that it holds a valid,
unrevoked and sufficiently scoped mandate, without revealing who mandated it and
without being linkable across tools. Mandates are BBS+ credentials, and revocation
uses a VB universal accumulator. Range checks use Bulletproofs++, and an optional
2-of-3 escrow lifts anonymity after abuse.

**This is a research prototype. Do not use it in production.**

## Contents

| Path | What it is |
|---|---|
| `code/src/lib.rs` | Rust crate `mmcore`: setup, root issuance, delegation, presentation, verification, revocation, escrow, Judge |
| `code/src/bin/attacks.rs` | Attack suite (A2–A6, 48 attacks) and 17 correctness checks → `results/attacks.json` |
| `code/src/bin/bench.rs` | Micro-benchmarks E1 (`costs`, `depth`, `msgs`, `rev`) → `results/e1_*.json` |
| `code/src/bin/smoke.rs` | Quick end-to-end smoke test |
| `code/mmpy/` | PyO3 bindings (agent-side wallet, tool-side verifier) |
| `code/e2/e2.py` | E2: end-to-end calls over the official MCP Python SDK, with JWT, Biscuit and macaroon baselines |
| `code/sim/e3.py` | E3/E3b: collusion of 50 tools (identifier linkage and timing attacker) |
| `code/gen_tex.py` | Generates every number, table and figure of the paper from `results/*.json` |
| `code/results/` | Result files of the campaign reported in the paper, with `env.json`, `campaign.log` and `SHA256SUMS` |
| `run_campaign.sh` | Runs E1 and E2 and records the environment and hashes |
| `manuscrit/` | Generated `numbers.tex`, `tab_*.tex`, `fig_*.pdf` |

## Requirements

- Rust 1.85 or later (edition 2024). The paper uses Rust 1.99.1.
- Python 3.12 or 3.13 with `maturin`, `mcp==1.30.0`, `pyjwt`, `cryptography`, `biscuit-python`, `pymacaroons`, `numpy` and `matplotlib`.
- Pinned cryptographic libraries (see `code/Cargo.toml`): `proof_system` 0.34.0, `bbs_plus` 0.25.0, `vb_accumulator` 0.29.0 and `bulletproofs_plus_plus` 0.9.0 (docknetwork/crypto), over BLS12-381.

## Reproducing the results

```sh
cd code
cargo build --release
./target/release/attacks                      # results/attacks.json (48/48 rejected, 17/17 checks)
RAYON_NUM_THREADS=1 ./target/release/bench costs   # then: depth, msgs, rev
(cd mmpy && maturin develop --release)         # inside a Python virtual environment
python e2/e2.py client results/e2.json         # E2 (spawns three MCP stdio servers)
python sim/e3.py                               # E3 / E3b
python gen_tex.py ../manuscrit                 # numbers.tex, tab_*.tex, fig_*.pdf
```

Instead of the bench and E2 steps, `./run_campaign.sh` runs E1 and E2 in sequence. It
also records `env.json`, `campaign.log` and `SHA256SUMS`. On macOS with a broken
Command Line Tools SDK, set `SDKROOT` to an installed SDK (the script does this).

The seed is 20261109. The attack suite and E3 are deterministic and reproduce byte
for byte. Timings depend on the machine. The paper reports one thread on an Apple
M5 Pro laptop on mains power (`results/env.json`).

## What the attack suite checks

Each attack runs against the real prover, verifier, issuer or Judge. Revocation
attacks count as rejected only if they fail on the non-membership statement of
the revoked identifier itself: statement 5 for the own id, 6 for the parent and
7 for the grandparent; statements 1 and 2 for delegation. `results/attacks_before_wraparound_fix.json`
keeps the run that exposed the wrap-around attack before the range proofs on the
child's values were added (47/48).

## Limitations

- The escrow uses a trusted dealer and a lookup table of registered principals. A deployment would use a DKG.
- The PyO3 `Verifier` rebuilds the whole system from the seed, secret keys included. It is a test harness, not a deployment component.
- E3 is a synthetic simulation. The Masked Mandates row of the identifier-linkage table is analytic (one pseudonym per call).
- No language model runs in the loop.

## Provenance

This is the second implementation of Masked Mandates. The author wrote the first one, which was lost
before release. This one was rebuilt on 11 November 2026 from Section IV of the paper with an AI assistant
(Claude, Anthropic), then corrected and re-measured:
- revocation tests now check that each attack fails on the revoked identifier itself;
- delegation proofs are checked against reuse with another child commitment or in another issuer session;
- openings go through a full Judge;
- delegated identifiers are drawn at random;
- delegated values carry range proofs against wrap-around modulo the group order
  (`code/results/attacks_before_wraparound_fix.json` shows the attack before the fix).

Every number in the paper comes from this implementation (`code/results/`, `env.json`, `SHA256SUMS`).
The commit history and `docs/reconstruction-notes-2026-11-11-fr.md` record how it was built. The author
reviewed the code on 12 November 2026.

## Licence

- Code: MIT (see `LICENSE`).
- Result files in `code/results/` and generated tables and figures: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

## Citation

See `CITATION.cff`. Archived version: DOI [10.5281/zenodo.24148363](https://doi.org/10.5281/zenodo.24148363).

## Contact

Yulliwas Ameur, Efrei Research Lab and Cédric (Cnam), Paris — yulliwas.ameur@efrei.fr — ORCID 0000-0003-1435-2982
