#!/bin/bash
# build mmpy v2.2 on the Hedy login node; target dir on /scratch (home quota), wheel unpacked into code22/pylib
set -e
R=$HOME/masked-mandates-95
source $R/agentenv/bin/activate
cd $R/code22/mmpy
export CARGO_TARGET_DIR=/scratch/yulameur1/masked-mandates-95/build-v22
maturin build --release -i $(which python) --out /scratch/yulameur1/masked-mandates-95/wheels-v22 > $R/code22/build.log 2>&1
W=$(ls -t /scratch/yulameur1/masked-mandates-95/wheels-v22/mmpy-*.whl | head -1)
rm -rf $R/code22/pylib; mkdir -p $R/code22/pylib
cd $R/code22/pylib && python -m zipfile -e $W . && ls -R $R/code22/pylib | head
sha256sum $R/code22/pylib/mmpy/*.so
echo BUILD DONE
