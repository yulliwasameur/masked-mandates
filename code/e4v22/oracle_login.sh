#!/bin/bash
# E4 v2.2 with the scripted policy (--base-url oracle, no LLM) on the Hedy login node, niced; outputs to /tmp, copied at the end
source ~/masked-mandates-95/agentenv/bin/activate
cd ~/masked-mandates-95/code22/e4v22
export PYTHONPATH=~/masked-mandates-95/code22/pylib RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
O=/tmp/yul-e4v22-oracle; mkdir -p $O; FOUT=~/masked-mandates-95/results/e4v22; mkdir -p $FOUT
lscpu > $O/lscpu-oracle-login.txt
C=(--base-url oracle --model oracle --workers 5 --agent-cores 20,21,22,23,24 --server-cores 25,26,27,28,29 --endpoint-kind "scripted policy (oracle), Hedy login node $(hostname), niced" --lscpu $O/lscpu-oracle-login.txt)
SH=(--shared-issuer --cfgs t0 --modes mm)
run() { PH=$1; P=$2; shift 2; echo "$(date +%T) $PH"; nice -n 10 python e4v22.py run "${C[@]}" --started "$(date +%Y-%m-%dT%H:%M:%S%z)" --out $O/e4v22_${PH}_oracle.json --port0 $P "$@" 2> $O/e4v22-$PH-oracle.log; echo "$PH rc=$?"; cp $O/e4v22_${PH}_oracle.json $FOUT/; }
python e4v22.py dwprobe --out $O/dwprobe-login.json 2> $O/dwprobe-login.log; cp $O/dwprobe-login.json $FOUT/
run dw 29600 --cfgs t0 --modes mm_dw,mm_dw_cv --templates ce --limit 0
run w0 29650 "${SH[@]}" --limit 0 --grace 0 --revoke-every 2 --dummies 200
run retry0 29700 "${SH[@]}" --limit 0 --grace 0 --retry --revoke-every 2 --dummies 200
run w2 29750 "${SH[@]}" --limit 0 --grace 2 --revoke-every 2 --dummies 200
run d1000 29800 "${SH[@]}" --limit 0 --grace 0 --grace-ms 1000 --revoke-every 2 --dummies 200
run sparse_w2 29850 "${SH[@]}" --limit 6 --grace 2 --revoke-every 60 --dummies 24 --dummy-k 8 --probe --probe-late-ms 1200 --min-duration 600
run sparse_d1000 29900 "${SH[@]}" --limit 6 --grace 0 --grace-ms 1000 --revoke-every 60 --dummies 24 --dummy-k 8 --probe --probe-late-ms 1200 --min-duration 600
mkdir -p ~/masked-mandates-95/logs/e4v22/oracle; cp $O/*.log $O/lscpu* ~/masked-mandates-95/logs/e4v22/oracle/; for d in $O/*.parts; do cp -r $d ~/masked-mandates-95/logs/e4v22/oracle/; done
echo ORACLE DONE
