#!/bin/bash
#SBATCH -J mm95-e1
#SBATCH -A m26297
#SBATCH -p compute
#SBATCH -N 1
#SBATCH --exclusive
#SBATCH -t 24:00:00
#SBATCH -o mm95-e1-%j.out
# One independent E1 campaign of Masked Mandates v2.2 on MesoNET Zen: all parts, one pinned core,
# single-threaded crypto, exclusive node.
# Usage: sbatch --export=ALL,CAMPAIGN=<n>,GIT_COMMIT=<hash>,GIT_TAG=<tag>[,E1_OUT=results/v22/zen] jobs/e1_zen.sbatch
set -u
cd "${SLURM_SUBMIT_DIR}"
C=${CAMPAIGN:-1}
OUT=${E1_OUT:-results/v22/zen}/c$C
mkdir -p $OUT || true
CORE=8
export RAYON_NUM_THREADS=1 RESULTS_DIR=$OUT BENCH_SEED=$((20261109 + C)) PIN="taskset -c $CORE" HOSTNAME=$(hostname)
export BIN_SHA256=$(sha256sum target/release/bench | cut -d' ' -f1)
lscpu > $OUT/lscpu.txt; uname -a > $OUT/uname.txt
{ echo "git_commit=${GIT_COMMIT:-unknown}"; echo "git_tag=${GIT_TAG:-none}"; sha256sum target/release/bench target/release/attacks target/release/smoke; echo "pin=taskset -c $CORE"; echo "rayon=1"; echo "node=$(hostname)"; echo "job=${SLURM_JOB_ID}"; } > $OUT/provenance.txt
for part in costs ablation throughput msgs depth rev; do
  echo "== $part $(date -Is)"; taskset -c $CORE ./target/release/bench $part 2> $OUT/$part.log || { echo FAIL $part; tail $OUT/$part.log; }
done
RESULTS_DIR=$OUT taskset -c $CORE ./target/release/attacks > $OUT/attacks.txt 2>&1 || true
echo done $(date -Is)
