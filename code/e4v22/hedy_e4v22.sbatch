#!/bin/bash
#SBATCH --job-name=95-e4v22
#SBATCH --account=m26297
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --output=/home/%u/masked-mandates-95/logs/e4v22-%j.out
# Masked Mandates -- E4 v2.2 (reviewer requests R2-B1 dishonest wallet, R2-B3 grace window / retry); derived from
# e4v21/hedy_e4v21.sbatch (same node layout: remaining cores for vLLM, 1 orchestrator core, per worker 1 agent core +
# 1 tool-server core; RAYON_NUM_THREADS=1; vLLM 0.33.0 with the v2.1 parsers and chat templates).
# Code: $R/code22 = code/src, code/mmpy, Cargo.toml, Cargo.lock, e2, e4v22 copied from the local tree (commit in
# e4v22/provenance.json); mmpy v2.2 built with maturin into $R/code22/pylib (PYTHONPATH; the v2.1 agentenv is untouched).
# PHASES (run in this order, one result file each):
#   dw           modes mm_dw,mm_dw_cv, templates c,e, t0, 24 tasks per template, per-task issuer (R2-B1)
#   retry0       shared issuer, W=0, wallet retry, revocation every 2 s, 200 dummies, mm, t0, 120 tasks (R2-B3)
#   d1000        shared issuer, W=0, tool time window D=1000 ms, no retry, otherwise as retry0
#   sparse_w2    shared issuer, W=2, revocation every 60 s, dishonest probes, >= MINDUR s, LIMIT_SPARSE tasks per template
#   sparse_d1000 as sparse_w2 with W=0 and D=1000 ms
# One job serves several models in turn (the per-user QOS allows 10 submitted jobs; the account was shared with another
# project's queue): RUNS="MODEL|SERVED|PARSER|TEMPLATE(or -)|PHASES (space-separated);..." ; vLLM is restarted per model.
# Usage: sbatch --export=ALL,RUNS="..." hedy_e4v22.sbatch
set -uo pipefail
R=$HOME/masked-mandates-95
C=${CODE:-$R/code22/e4v22}
VLLM_VENV=${VLLM_VENV:-/home/yulameur1/rbfl-store/venv}
W=${WORKERS:-5}
MINDUR=${MINDUR:-600}
LIMIT_SPARSE=${LIMIT_SPARSE:-6}
# everything is written to the node-local /tmp while the job runs and copied to $HOME in the EXIT trap (NFS quota)
FOUT=$R/results/e4v22; FLOGS=$R/logs/e4v22; mkdir -p $FOUT $FLOGS
WORK=/tmp/yul-e4v22-$SLURM_JOB_ID; OUT=$WORK/results; LOGS=$WORK/logs; mkdir -p $OUT $LOGS
# tool-server ports: [PORT0, PORT0 + 300) per job, 50 per phase (5 workers x 10); below the Linux ephemeral range
PORT0=$((20000 + (SLURM_JOB_ID % 40) * 300))
export RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
export PYTHONPATH=$R/code22/pylib
STARTED=$(date +%Y-%m-%dT%H:%M:%S%z)
lscpu > $OUT/lscpu-$SLURM_JOB_ID.txt
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > $OUT/gpu-$SLURM_JOB_ID.csv
read VCPU PCPU ACPU SCPU < <(python3 -c "
import os; c=sorted(os.sched_getaffinity(0)); W=$W
assert len(c) >= 5 + 2*W, (len(c), W)
v=c[:len(c)-1-2*W]; p=c[len(v)]; a=c[len(v)+1:len(v)+1+W]; s=c[len(v)+1+W:len(v)+1+2*W]
print(','.join(map(str,v)), p, ','.join(map(str,a)), ','.join(map(str,s)))")
[ -n "$ACPU" ] || { echo "core split failed"; exit 1; }
echo "job $SLURM_JOB_ID node $(hostname) cpus vllm=$VCPU orchestrator=$PCPU agents=$ACPU servers=$SCPU RAYON_NUM_THREADS=$RAYON_NUM_THREADS runs=$RUNS" | tee $OUT/cores-$SLURM_JOB_ID.txt
VPID=""
cleanup() { [ -n "$VPID" ] && kill $VPID 2>/dev/null; pkill -P $$ 2>/dev/null; wait 2>/dev/null
  cp -r $OUT/. $FOUT/ 2>/dev/null; cp -r $LOGS/. $FLOGS/ 2>/dev/null; rm -rf $WORK; }
trap cleanup EXIT
source $R/agentenv/bin/activate
cd $C
python -c "import mmpy, sys; assert hasattr(mmpy.Authority, 'present_dishonest'), mmpy.__file__; print('mmpy', mmpy.__file__)" || exit 1
RC=0; i=0; mi=0
IFS=';' read -ra SPECS <<< "$RUNS"
for SPEC in "${SPECS[@]}"; do
  IFS='|' read -r MODEL SERVED PARSER TEMPLATE PHASES <<< "$SPEC"
  [ "$TEMPLATE" = "-" ] && TEMPLATE=""
  # vLLM port: 10 per job (job 51013's second model collided with job 51014's first under 8000 + id % 900 + model index)
  TAG=$SERVED; PORT=$((8000 + (SLURM_JOB_ID % 90) * 10 + mi)); mi=$((mi + 1))
  VARGS="--served-model-name $SERVED --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser $PARSER --seed 0 --gpu-memory-utilization 0.90 --host 127.0.0.1 --port $PORT"
  [ -n "$TEMPLATE" ] && VARGS="$VARGS --chat-template $TEMPLATE"
  echo "vllm serve $R/hf/$MODEL $VARGS" > $OUT/vllm-cmd-$TAG-$SLURM_JOB_ID.txt
  echo "$(date +%T) model $SERVED: starting vLLM (phases: $PHASES)"
  ( source $VLLM_VENV/bin/activate
    export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4
    unset RAYON_NUM_THREADS PYTHONPATH
    exec taskset -c $VCPU vllm serve "$R/hf/$MODEL" $VARGS ) > $LOGS/vllm-$TAG-$SLURM_JOB_ID.log 2>&1 &
  VPID=$!
  # no wait for vLLM here: the workers wait for the endpoint after their setup (the shared issuer's dummy delegations
  # overlap with model loading)
  MC=$(python3 -c "import json,sys; print(json.dumps({'hf': '$MODEL', 'served': '$SERVED', 'parser': '$PARSER', 'template': '${TEMPLATE:-model default (tokenizer_config.json)}', 'vllm': '0.33.0', 'gpu': 'H100 80GB HBM3'}))")
  COMMON=(--base-url http://127.0.0.1:$PORT/v1 --model "$SERVED" --workers $W --agent-cores $ACPU --server-cores $SCPU
          --model-config "$MC" --vllm-cmd "$(cat $OUT/vllm-cmd-$TAG-$SLURM_JOB_ID.txt)" --endpoint-kind "vLLM 0.33.0, 1x H100 80GB (Hedy), job $SLURM_JOB_ID"
          --lscpu $OUT/lscpu-$SLURM_JOB_ID.txt --started "$(date +%Y-%m-%dT%H:%M:%S%z)")
  SH=(--shared-issuer --cfgs t0 --modes mm)
  for PH in $PHASES; do
    case $PH in
      dw)           ARGS=(--cfgs t0 --modes mm_dw,mm_dw_cv --templates ce --limit 0) ;;
      retry0)       ARGS=("${SH[@]}" --limit 0 --grace 0 --retry --revoke-every 2 --dummies 200) ;;
      d1000)        ARGS=("${SH[@]}" --limit 0 --grace 0 --grace-ms 1000 --revoke-every 2 --dummies 200) ;;
      sparse_w2)    ARGS=("${SH[@]}" --limit $LIMIT_SPARSE --grace 2 --revoke-every 60 --dummies 24 --dummy-k 8 --probe --probe-late-ms 1200 --min-duration $MINDUR) ;;
      sparse_d1000) ARGS=("${SH[@]}" --limit $LIMIT_SPARSE --grace 0 --grace-ms 1000 --revoke-every 60 --dummies 24 --dummy-k 8 --probe --probe-late-ms 1200 --min-duration $MINDUR) ;;
      *) echo "unknown phase $PH"; RC=$((RC + 1)); continue ;;
    esac
    F=$OUT/e4v22_${PH}_$TAG.json
    echo "$(date +%T) phase $PH -> $F"
    # sequential phases reuse 6 port blocks of 50 (5 workers x 10) inside the job's range; `run` checks each port's pid
    taskset -c $PCPU python e4v22.py run "${COMMON[@]}" "${ARGS[@]}" --out $F --port0 $((PORT0 + 50 * (i % 6))) 2> $LOGS/e4v22-$PH-$TAG-$SLURM_JOB_ID.log
    RC=$((RC + $?)); i=$((i + 1))
    mkdir -p $LOGS/parts-$PH-$TAG-$SLURM_JOB_ID; mv $F.parts/* $LOGS/parts-$PH-$TAG-$SLURM_JOB_ID/ 2>/dev/null; rmdir $F.parts 2>/dev/null
    tail -3 $LOGS/e4v22-$PH-$TAG-$SLURM_JOB_ID.log
    cp $F $FOUT/ 2>/dev/null   # keep finished phases even if a later phase hits the time limit
  done
  kill $VPID 2>/dev/null; wait $VPID 2>/dev/null; VPID=""; sleep 10
done
exit $RC
