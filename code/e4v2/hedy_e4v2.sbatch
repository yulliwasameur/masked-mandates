#!/bin/bash
#SBATCH --job-name=95-e4v2
#SBATCH --account=m26297
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --output=/home/%u/masked-mandates-95/logs/e4v2-%j.out
# Masked Mandates -- E4 v2 (MesoNET Hedy, 1 H100 80GB, 16 cores: the QOS grants at most 16 cores per GPU).
# Core layout (from the cores Slurm allocates): the remaining cores (5 of 16 with W=5) for vLLM, 1 for the orchestrator, then for each of the W workers
# one core for the agent process (LLM client + agent-side authorisation) and one core for its tool-server process
# (4 MCP servers + tool-side verification). RAYON_NUM_THREADS=1: prover and verifier are single-threaded.
# RERUN=1 re-runs only the units of an existing $OUT/e4v2_$TAG.json that ended with an error or were never run.
# Usage: sbatch --export=ALL,MODEL=<hf dir>,SERVED=<name>,PARSER=<tool parser>[,TEMPLATE=<jinja path>][,EXTRA="..."]
#               [,WORKERS=5][,CFGS=t0,t0_nolat,t07_s1,t07_s2,t07_s3][,LIMIT=0][,BENCH=1][,TAG=...][,RERUN=1] hedy_e4v2.sbatch
set -uo pipefail
R=$HOME/masked-mandates-95
VLLM_VENV=${VLLM_VENV:-/home/yulameur1/rbfl-store/venv}
W=${WORKERS:-5}
CFGS=${CFGS:-t0,t0_nolat,t07_s1,t07_s2,t07_s3}
LIMIT=${LIMIT:-0}
TAG=${TAG:-$SERVED}
OUT=$R/results/e4v2; LOGS=$R/logs/e4v2; mkdir -p $OUT $LOGS
PORT=$((8000 + SLURM_JOB_ID % 1000))
PORT0=$((20000 + (SLURM_JOB_ID % 200) * 100))
export RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
STARTED=$(date +%Y-%m-%dT%H:%M:%S%z)
lscpu > $OUT/lscpu-$TAG-$SLURM_JOB_ID.txt
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > $OUT/gpu-$TAG-$SLURM_JOB_ID.csv
read VCPU PCPU ACPU SCPU < <(python3 -c "
import os; c=sorted(os.sched_getaffinity(0)); W=$W
assert len(c) >= 5 + 2*W, (len(c), W)
v=c[:len(c)-1-2*W]; p=c[len(v)]; a=c[len(v)+1:len(v)+1+W]; s=c[len(v)+1+W:len(v)+1+2*W]
print(','.join(map(str,v)), p, ','.join(map(str,a)), ','.join(map(str,s)))")
[ -n "$ACPU" ] || { echo "core split failed"; exit 1; }
echo "job $SLURM_JOB_ID node $(hostname) cpus vllm=$VCPU orchestrator=$PCPU agents=$ACPU servers=$SCPU RAYON_NUM_THREADS=$RAYON_NUM_THREADS" | tee $OUT/cores-$TAG-$SLURM_JOB_ID.txt
# 1) model server: vLLM 0.33.0 (read-only shared venv)
VARGS="--served-model-name $SERVED --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser $PARSER --seed 0 --gpu-memory-utilization 0.90 --host 127.0.0.1 --port $PORT"
[ -n "${TEMPLATE:-}" ] && VARGS="$VARGS --chat-template $TEMPLATE"
VARGS="$VARGS ${EXTRA:-}"
echo "vllm serve $R/hf/$MODEL $VARGS" > $OUT/vllm-cmd-$TAG-$SLURM_JOB_ID.txt
( source $VLLM_VENV/bin/activate
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4
  unset RAYON_NUM_THREADS
  exec taskset -c $VCPU vllm serve "$R/hf/$MODEL" $VARGS ) > $LOGS/vllm-$TAG-$SLURM_JOB_ID.log 2>&1 &
VPID=$!
cleanup() { kill $VPID 2>/dev/null; pkill -P $$ 2>/dev/null; wait $VPID 2>/dev/null; }
trap cleanup EXIT
source $R/agentenv/bin/activate
cd $R/code/e4v2
# 2) single-core micro-benchmark of the authorisation primitives while vLLM loads (and, once, the multi-threaded variant)
if [ "${BENCH:-0}" = "1" ]; then
  A0=${ACPU%%,*}
  taskset -c $A0 python e4v2.py bench --out $OUT/bench-1thread-$TAG-$SLURM_JOB_ID.json > $LOGS/bench-$TAG-$SLURM_JOB_ID.log 2>&1
  ( export RAYON_NUM_THREADS=16; taskset -c $ACPU,$SCPU python e4v2.py bench --n 15 --out $OUT/bench-16threads-$TAG-$SLURM_JOB_ID.json >> $LOGS/bench-$TAG-$SLURM_JOB_ID.log 2>&1 )
fi
for i in $(seq 1 180); do curl -sf 127.0.0.1:$PORT/health >/dev/null && break; sleep 10; done
curl -sf 127.0.0.1:$PORT/health >/dev/null || { echo "vLLM not ready"; tail -60 $LOGS/vllm-$TAG-$SLURM_JOB_ID.log; exit 1; }
# 3) campaign
MC=$(python3 -c "import json,sys; print(json.dumps({'hf': '$MODEL', 'served': '$SERVED', 'parser': '$PARSER', 'template': '${TEMPLATE:-model default (tokenizer_config.json)}', 'extra': '${EXTRA:-}', 'vllm': '0.33.0', 'gpu': 'H100 80GB HBM3'}))")
taskset -c $PCPU python e4v2.py run --base-url http://127.0.0.1:$PORT/v1 --model "$SERVED" --out $OUT/e4v2_$TAG.json \
  --workers $W --agent-cores $ACPU --server-cores $SCPU --port0 $PORT0 --cfgs $CFGS --limit $LIMIT \
  --model-config "$MC" --vllm-cmd "$(cat $OUT/vllm-cmd-$TAG-$SLURM_JOB_ID.txt)" --endpoint-kind "vLLM 0.33.0, 1x H100 80GB (Hedy), job $SLURM_JOB_ID" \
  --lscpu $OUT/lscpu-$TAG-$SLURM_JOB_ID.txt --started "$STARTED" ${RERUN:+--rerun-errors $OUT/e4v2_$TAG.json} 2> $LOGS/e4v2-$TAG-$SLURM_JOB_ID.log
RC=$?
mkdir -p $LOGS/parts-$TAG-$SLURM_JOB_ID; mv $OUT/e4v2_$TAG.json.parts/* $LOGS/parts-$TAG-$SLURM_JOB_ID/ 2>/dev/null; rmdir $OUT/e4v2_$TAG.json.parts 2>/dev/null
tail -30 $LOGS/e4v2-$TAG-$SLURM_JOB_ID.log
exit $RC
