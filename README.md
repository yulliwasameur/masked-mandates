# Masked Mandates — artifact (version 2.2.1)

Code, scripts and result files for the paper

> Y. Ameur, S. Bouzefrane and S. Banerjee, *Masked Mandates: Unlinkable, Attenuable and Accountable Delegation for LLM Agents*,
> submitted to IEEE Open Journal of the Computer Society, 2026.

## What it does

Masked Mandates lets an AI agent prove, for one tool call, that it holds a valid,
unrevoked and sufficiently scoped mandate, without revealing who mandated it and
without being linkable across tools by the authorization it shows.

It is built from these parts:
- **Mandates:** BBS+ credentials, delegated by blind re-issuance.
- **Pseudonyms:** each call carries a Dodis–Yampolskiy pseudonym with a hidden counter. The counter is taken from a signed interval, so a delegation tree shares one quota.
- **Revocation:** a VB accumulator with hash-derived parameters.
- **Range checks:** Bulletproofs++.
- **Escrow:** an optional 2-of-3 escrow opens a call to the principal and the mandate, through a per-root tag signed by the principal.

**This is a research prototype. It has not been audited. Do not use it in production.**

## Contents

| Path | What it is |
|---|---|
| `code/src/lib.rs` | Rust crate `mmcore` (version 2.2 of the scheme). It covers setup with hash-derived parameters, root issuance with a per-root tag, delegation with counter intervals, presentation and verification with tool clocks and nonces, revocation with an optional grace window, the escrow (Pedersen-VSS DKG), and Judge. |
| `code/src/bin/attacks.rs` | Attack suite: 96 attacks with a taxonomy (threat × rejecting party), including unauthorized revocations at the log, including malicious provers and delegators, a shifted attribute layout, the per-principal root limit, an issuer that substitutes a principal's key, tampered accumulator update data, and 2,000 bit flips; plus 37 checks, among them positive controls (a debug issuer without the tested relation accepts each malicious delegation). Writes `results/attacks.json`. |
| `code/src/bin/bench.rs` | E1 micro-benchmarks: `costs`, `ablation`, `throughput`, `msgs`, `depth`, `rev`. Writes `$RESULTS_DIR/e1_*.json` and records the commit and the binary hash. |
| `code/src/bin/smoke.rs` | Quick end-to-end test |
| `code/mmpy/` | PyO3 bindings: `Authority` (issuer, registry, escrow and wallets of the test harness) and `Verifier` (public data only, nonces, clock, uniform errors) |
| `code/jobs/e1_zen.sbatch`, `code/jobs/e1_zen_mp.sbatch` | Slurm jobs used for E1 on MesoNET Zen: one campaign per exclusive node with the process pinned to one core, and the multi-core throughput run |
| `code/e2v2/e2v21.py` | E2: MCP end-to-end over stdio, streamable HTTP, delayed HTTP and stateless HTTP. Baselines are a JWT chain, Biscuit, macaroon, batch one-time tokens and RFC 9474 blind tokens with a proof-of-possession key. |
| `code/sim/e3v22.py` | E3: collusion study (identifier, timing, content, identified-tool, profile-oracle and issuer-timing attackers; gaps calibrated on the E4 v2.1 runs; load sweep; decoupled identity calls), 5 seeds per cell |
| `code/e4v21/` | E4: LLM agents over MCP (vLLM), with delegation, revocation, a binding quota, a shared issuer and a replication control. Includes the Slurm job used on MesoNET Hedy. |
| `code/e4v22/` | E4 additions: dishonest wallet (`present_dishonest`, test only), wallet retry, time-bounded grace window, sparse revocation schedule; scripted agent and five LLMs |
| `code/gen_tex_v21.py` (+ `gen_e2v21.py`, `gen_e3v22.py`, `gen_e4v21.py`, `gen_e4v22.py`) | Generates every number, table and figure of the paper from `code/results/` |
| `code/results/` | Result files for the four experiments (see below) |
| `paper-v2/` | Manuscript LaTeX sources, supplementary material (`supplement.tex`), generated numbers, tables and figures, and the evidence for Table 1 (`related-audit.md`); review correspondence is not included |

Earlier files (`e2/`, `e2v2/e2v2.py`, `sim/e3.py`, `sim/e3v2.py`, `e4/`, `e4v2/`, `gen_tex*.py` without `21`, and `results/e1_*.json`, `e2*.json`, `e3*.json`, `e4/`, `e4v2/`) belong to versions 1.0.x and 2 of the experiments. They are kept for reference and are not used by the paper.

## Results used by the paper

| Experiment | Files | Where it ran |
|---|---|---|
| Attacks | `results/attacks.json` (v2.2.1; the v2.1 suite was also re-run on Zen: `results/v21/zen/attacks_zen.json`, identical outcomes) | laptop (and Zen for v2.1) |
| E1 | `results/v22/zen/c{1,2,3}/` (release v2.2.0; with `provenance.txt`: commit, binary hashes, pinning, node, job), `results/v22/zen/mp/`, `results/v22/mac/`; excluded first run of campaign 1 with its justification in `results/v22/zen/excluded_node068/`; v2.1 runs in `results/v21/` | Zen (AMD EPYC 9534, exclusive nodes, 1 pinned core) and an Apple M5 Pro laptop (1 thread; shared machine, load recorded in `campaign.log`) |
| E2 | `results/e2v21.json`, `results/e2v21_runs/`, `results/e2v21_summary.md` | laptop, 3 runs, loads recorded |
| E3 | `results/e3v22.json`, `results/e3v22_summary.md`, `results/fig_e3_load.pdf`, `results/e3v22_jobs/` | Zen |
| E4 | `results/e4v21/`, `results/e4v21_summary.md`; `results/e4v22/`, `results/e4v22_summary.md`, `results/e4v22_key.json` | Hedy (1 H100 per job, vLLM 0.33.0; scripted runs on the login node) |

## Requirements

- **Rust** 1.85 or later. The campaigns used 1.91 on Zen and 1.99 on the laptop.
- **Python** 3.12 or 3.13 with `maturin`, `mcp==1.30.0`, `pyjwt`, `cryptography`, `biscuit-python`, `pymacaroons`, `numpy`, `scipy` and `matplotlib`.
- **Pinned cryptographic libraries** (see `code/Cargo.toml`): `proof_system` 0.34.0, `bbs_plus` 0.25.0, `vb_accumulator` 0.29.0 and `bulletproofs_plus_plus` 0.9.0 (docknetwork/crypto), over BLS12-381.

## Reproducing

```sh
cd code
cargo build --release
./target/release/smoke
./target/release/attacks                                   # results/attacks.json: 96/96 rejected, 37/37 checks
for p in costs ablation throughput msgs depth rev; do RAYON_NUM_THREADS=1 RESULTS_DIR=out ./target/release/bench $p; done
sbatch --export=ALL,CAMPAIGN=1,GIT_COMMIT=$(git rev-parse --short=12 HEAD) jobs/e1_zen.sbatch   # on a Slurm cluster
(cd mmpy && maturin develop --release)                     # inside a Python virtual environment
RAYON_NUM_THREADS=1 python e2v2/e2v21.py all results        # E2, 3 runs
python sim/e3v22.py --help                                  # E3 (cells can be run in parallel, see the docstring)
python e4v21/e4v21.py --help                                # E4 (needs an OpenAI-compatible endpoint, e.g. vLLM)
python e4v22/e4v22.py --help                                # E4 additions (--base-url oracle runs without an LLM)
python gen_tex_v21.py ../paper-v2                           # numbers.tex, tab_*.tex, fig_*.pdf
```

To check the result files: `cd code && shasum -a 256 -c results/SHA256SUMS-v2.2` (`results/SHA256SUMS` is the superseded manifest of version 1.0.x; its `attacks.json` entry refers to the 1.0.x suite). `results/binaries-SHA256.txt` gives the hashes of the release binaries. The provenance of each experiment (commit, build hash, platform, jobs) is in Table S-Provenance of the supplementary material.

**What reproduces exactly:**
- the attack suite and E3 are deterministic (fixed seeds);
- E2 and E4 timings depend on the machine and the load;
- E4 outcomes depend on vLLM's batching, which is not deterministic even at temperature 0. The paper reports a replication control for this.

## Limitations

- **Non-strict verifier.** `mmpy.Verifier(...)` without `epoch` and `now` skips the epoch, time and nonce checks; this mode is for tests only, and rate limits do not hold in it. The harnesses use strict mode.
- **Harness, not deployment.** The `Authority` object plays issuer, escrow and wallets in one process, and the DKG is simulated by one process for the three members. The append-only log that the security model assumes is not implemented.
- **Extraction.** Proofs use plain Fiat–Shamir. The security arguments use rewinding extraction with sequential issuer sessions; the supplementary material states the assumptions.
- **Synthetic data.** E3 is a simulation, and E4 uses synthetic tools and tasks with open models served locally.

## Provenance

The first implementation was lost before release. This one was rebuilt from the paper's construction with an AI assistant (Claude, Anthropic), then revised after internal review rounds:

- **Version 1.0.x:** the first re-implementation.
- **Version 2:**
  - per-tree hidden counters;
  - issuer-chosen identifiers;
  - escrow of the mandate identifier.
- **Version 2.1:**
  - hash-derived parameters;
  - per-root tag bound by the principal;
  - counter intervals;
  - tool and issuer clocks;
  - grace window;
  - Pedersen-VSS DKG;
  - uniform errors.
- **Version 2.2 (after a further internal review round):**
  - issuer checks the attribute layout of root requests, bounds root intervals by Q and limits roots per principal;
  - wallets verify every non-membership witness;
  - Judge takes the registry from outside the issuer;
  - tool-side time-bounded grace window and wallet retry (mmpy);
  - malicious-delegator attacks with positive controls;
  - revocation authorization at the log (holder or parent credential, or two committee members; v2.2.1).

The commit history records every step, and `CHANGELOG.md` summarizes them. The first author reviewed the code; there has been no independent audit.

## Licence

- **Code:** MIT (see `LICENSE`).
- **Result files and generated tables and figures:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

## Citation

See `CITATION.cff`. This version (2.2.1, cited in the revised paper): DOI [10.5281/zenodo.24222783](https://doi.org/10.5281/zenodo.24222783). All versions: DOI [10.5281/zenodo.24148362](https://doi.org/10.5281/zenodo.24148362). Changes between versions are in `CHANGELOG.md`.

## Contact

Yulliwas Ameur, Efrei Research Lab and Cédric (Cnam), Paris — yulliwas.ameur@efrei.fr — ORCID 0000-0003-1435-2982
