#!/bin/bash
# E3 v2.2 decoupling, reviewer follow-up: adapted attacker X and value-free variant (group decA, 40 cells), 3 whole nodes
#SBATCH --job-name=mm95-e3v22a
#SBATCH --account=m26297
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --array=0-2
#SBATCH --output=logs/decA_%A_%a.out
cd ~/mm95-e3v22
module load miniforge3/24.9.0
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8
echo "node $(hostname) shard $SLURM_ARRAY_TASK_ID start $(date)"
~/mm95-e3/venv/bin/python sim/e3v22.py tasks --cells cells | awk -F'|' '$1 == "decA"' | awk -v s=$SLURM_ARRAY_TASK_ID 'NR % 3 == s' > logs/tasks_decA_$SLURM_ARRAY_TASK_ID.txt
wc -l logs/tasks_decA_$SLURM_ARRAY_TASK_ID.txt
cat logs/tasks_decA_$SLURM_ARRAY_TASK_ID.txt | xargs -P 16 -I{} ~/mm95-e3/venv/bin/python sim/e3v22.py cell {} --cal cal.json --cells cells
echo "done $(date)"
