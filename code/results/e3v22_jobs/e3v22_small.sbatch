#!/bin/bash
# E3 v2.2: every cell with N <= 10,000 (main, sensitivity, coalitions, load rate sweep, p_deleg = 1 at 10,000)
#SBATCH --job-name=mm95-e3v22s
#SBATCH --account=m26297
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=08:00:00
#SBATCH --array=0-15%16
#SBATCH --output=logs/small_%A_%a.out
cd ~/mm95-e3v22
module load miniforge3/24.9.0
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8
echo "node $(hostname) shard $SLURM_ARRAY_TASK_ID start $(date)"
~/mm95-e3/venv/bin/python sim/e3v22.py tasks --cells cells --shard $SLURM_ARRAY_TASK_ID --nshards 16 | awk -F'|' '$3 <= 10000' > logs/tasks_small_$SLURM_ARRAY_TASK_ID.txt
wc -l logs/tasks_small_$SLURM_ARRAY_TASK_ID.txt
cat logs/tasks_small_$SLURM_ARRAY_TASK_ID.txt | xargs -P 16 -I{} ~/mm95-e3/venv/bin/python sim/e3v22.py cell {} --cal cal.json --cells cells
echo "done $(date)"
