#!/bin/bash
#SBATCH --job-name=95-e4
#SBATCH --account=m26297
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
#SBATCH --output=/home/%u/95-e4_%j.out
# Masked Mandates -- E4: a real LLM agent in the loop (Slurm job used for the paper, MesoNET Hedy, 1 H100).
# On one node: vLLM serves the model; the agent, the authorisation (none / jwt / Masked Mandates) and the three
# MCP servers run on the other half of the job's CPU cores.
# Layout: $R/hf/<model> (weights), $R/agentenv (Python 3.12 + mcp 1.30.0 + mmpy), $R/code (this repository's code/).
# Usage: sbatch --export=ALL,MODEL=<hf dir>,SERVED=<name>,PARSER=<tool parser>[,EXTRA="..."][,VLLM_VENV=...] hedy_e4.sbatch
set -uo pipefail
R=$HOME/masked-mandates-95
PORT=$((8000 + SLURM_JOB_ID % 1000))
OUT=$R/results; mkdir -p $OUT
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > $OUT/gpu-$SERVED-$SLURM_JOB_ID.csv
lscpu | grep -E "Model name|^CPU\(s\)" >> $OUT/gpu-$SERVED-$SLURM_JOB_ID.csv
# split the cores allocated by Slurm in two halves: vLLM / agent
read VCPU ACPU < <(python3 -c "import os;c=sorted(os.sched_getaffinity(0));h=len(c)//2;print(','.join(map(str,c[:h])),','.join(map(str,c[h:])))")
echo "cpus vllm=$VCPU agent=$ACPU" >> $OUT/gpu-$SERVED-$SLURM_JOB_ID.csv
# 1) model: vLLM 0.33.0
( source "${VLLM_VENV:-$HOME/vllm-venv}/bin/activate"
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  exec taskset -c $VCPU vllm serve "$R/hf/$MODEL" --served-model-name "$SERVED" --max-model-len 16384 \
    --enable-auto-tool-choice --tool-call-parser "$PARSER" ${EXTRA:-} \
    --seed 0 --gpu-memory-utilization 0.90 --host 127.0.0.1 --port $PORT ) > $R/logs/vllm-$SERVED-$SLURM_JOB_ID.log 2>&1 &
VPID=$!
for i in $(seq 1 120); do curl -sf 127.0.0.1:$PORT/health >/dev/null && break; sleep 10; done
curl -sf 127.0.0.1:$PORT/health >/dev/null || { echo "vLLM not ready"; tail -40 $R/logs/vllm-$SERVED-$SLURM_JOB_ID.log; kill $VPID; exit 1; }
# 2) agent + authorisation + MCP servers, other half of the cores
source $R/agentenv/bin/activate
cd $R/code
taskset -c $ACPU python e4/e4.py run --base-url http://127.0.0.1:$PORT/v1 --model "$SERVED" --endpoint-kind "vllm-0.33.0 on H100" \
  --out $OUT/e4_$SERVED.json --tasks ${TASKS:-24} --reps ${REPS:-1} 2> $R/logs/e4-$SERVED-$SLURM_JOB_ID.log
RC=$?
kill $VPID; wait $VPID 2>/dev/null
tail -45 $R/logs/e4-$SERVED-$SLURM_JOB_ID.log
exit $RC
