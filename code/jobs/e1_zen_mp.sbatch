#!/bin/bash
#SBATCH -J mm95-e1mp
#SBATCH -A m26297
#SBATCH -p compute
#SBATCH -N 1
#SBATCH --exclusive
#SBATCH -t 04:00:00
#SBATCH -o mm95-e1mp-%j.out
# Multi-core verification throughput: P independent single-threaded verifier processes, each pinned to its own core,
# run the throughput benchmark at the same time; aggregate rate = P * n / slowest wall time.
set -u
cd "${SLURM_SUBMIT_DIR}"
OUT=${E1_OUT:-results/v22/zen}/mp; mkdir -p $OUT || true
export RAYON_NUM_THREADS=1 HOSTNAME=$(hostname) BIN_SHA256=$(sha256sum target/release/bench | cut -d' ' -f1)
lscpu > $OUT/lscpu.txt
{ echo "git_commit=${GIT_COMMIT:-unknown}"; echo "git_tag=${GIT_TAG:-none}"; sha256sum target/release/bench; echo "rayon=1"; echo "node=$(hostname)"; echo "job=${SLURM_JOB_ID}"; } > $OUT/provenance.txt
for P in 1 2 4 8 16 32 64; do
  mkdir -p $OUT/p$P
  for i in $(seq 0 $((P-1))); do
    mkdir -p $OUT/p$P/w$i
    ( RESULTS_DIR=$OUT/p$P/w$i BENCH_SEED=$((20261200 + i)) PIN="taskset -c $i" taskset -c $i ./target/release/bench throughput 2> $OUT/p$P/w$i/log ) &
  done
  wait; echo "P=$P done $(date -Is)"
done
