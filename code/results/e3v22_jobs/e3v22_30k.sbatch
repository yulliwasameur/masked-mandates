#!/bin/bash
# E3 v2.2: load sweep, N = 30,000 (5 seeds, full attacker set but c / posterior) on one node
#SBATCH --job-name=mm95-e3v22m
#SBATCH --account=m26297
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=logs/30k_%j.out
cd ~/mm95-e3v22
module load miniforge3/24.9.0
export OMP_NUM_THREADS=24 OPENBLAS_NUM_THREADS=24 MKL_NUM_THREADS=24
echo "node $(hostname) start $(date)"
~/mm95-e3/venv/bin/python sim/e3v22.py tasks --cells cells | awk -F'|' '$3 == 30000' > logs/tasks_30k.txt
cat logs/tasks_30k.txt | xargs -P 5 -I{} ~/mm95-e3/venv/bin/python sim/e3v22.py cell {} --cal cal.json --cells cells
echo "done $(date)"
