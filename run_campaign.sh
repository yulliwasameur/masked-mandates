#!/bin/zsh
# Campagne E1 + E2 sur ce Mac (chantier 95). Usage : ./run_campaign.sh  (depuis corrige/)
set -e
ROOT="${0:A:h}"
cd "$ROOT/code"
V="$ROOT/.venv"
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk RAYON_NUM_THREADS=1
LOG=results/campaign.log; [[ -n $SKIP_E1 ]] || : > $LOG
log() { print -r -- "$(date '+%F %T') $*" | tee -a $LOG; }
cargo build --release --bins 2>>$LOG
log "power: $(pmset -g batt | head -1)"
[[ -n $SKIP_E1 ]] || for part in costs depth msgs rev; do log "start e1 $part"; ./target/release/bench $part 2>>$LOG; log "end e1 $part"; done
log "start e2"; "$V/bin/python" -I e2/e2.py client results/e2.json >>$LOG 2>&1; log "end e2"
log "power: $(pmset -g batt | head -1)"
"$V/bin/python" -I - <<PY
import json, platform, subprocess, importlib.metadata as m
sh=lambda c: subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
env={"cpu": sh("sysctl -n machdep.cpu.brand_string"), "machine": "MacBook (Apple silicon), macOS "+platform.mac_ver()[0],
     "cores": int(sh("sysctl -n hw.ncpu")), "memory_gb": int(sh("sysctl -n hw.memsize"))//2**30,
     "rustc": sh("rustc --version").split()[1], "python": platform.python_version(), "mcp_sdk": m.version("mcp"),
     "threads": 1, "note": "laptop on mains power, single thread, release build"}
json.dump(env, open("results/env.json","w"), indent=1); print(env)
PY
shasum -a 256 target/release/bench target/release/attacks results/*.json > results/SHA256SUMS
log "done"
