# Changelog

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
