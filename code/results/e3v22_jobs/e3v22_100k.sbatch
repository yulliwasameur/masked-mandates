#!/bin/bash
# E3 v2.2: load sweep, N = 100,000: one node per seed; first the timing / naming attackers (loadT, done in ~20 min), then the
# full set (load): cancelled unfinished after 6 h 49 min (job 1679922), so only loadT is reported at N = 100,000
#SBATCH --job-name=mm95-e3v22l
#SBATCH --account=m26297
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=36:00:00
#SBATCH --array=0-4
#SBATCH --output=logs/100k_%A_%a.out
cd ~/mm95-e3v22
module load miniforge3/24.9.0
export OMP_NUM_THREADS=128 OPENBLAS_NUM_THREADS=128 MKL_NUM_THREADS=128
r=$SLURM_ARRAY_TASK_ID
echo "node $(hostname) seed $r start $(date)"
~/mm95-e3/venv/bin/python sim/e3v22.py cell "loadT|base|100000|$r|mm|50" --cal cal.json --cells cells
~/mm95-e3/venv/bin/python sim/e3v22.py cell "load|base|100000|$r|mm|50" --cal cal.json --cells cells
echo "done $(date)"
