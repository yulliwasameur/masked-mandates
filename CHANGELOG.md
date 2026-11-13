# Changelog

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
