#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
market_root="${QINVIA_MARKET_WORK_ROOT:-$project_root/.local-wsl/market}"
python_bin="${QINVIA_PYTHON_BIN:-$project_root/.venv/bin/python}"
mkdir -p "$market_root/runtime"

pid_file="$market_root/runtime/market_collector.pid"
if [[ -f "$pid_file" ]]; then
    existing_pid="$(tr -dc '0-9' < "$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "already_running pid=$existing_pid"
        exit 0
    fi
fi

if [[ ! -x "$python_bin" ]]; then
    echo "missing_wsl_venv=$python_bin" >&2
    exit 1
fi

echo "$$" > "$pid_file"
cd "$project_root"
exec env \
    PYTHONPATH="$project_root/src" \
    QINVIA_MARKET_WORK_ROOT="$market_root" \
    QINVIA_MARKET_UNIVERSE="$project_root/data/processed/universe/eligible_universe.csv" \
    QINVIA_MARKET_STATUS_MIRROR="$project_root/runtime/market_collector_status.json" \
    "$python_bin" -m qinvia_etfs.market --pilot-size 100 --delay 0.35 --max-attempts 3 \
    >> "$market_root/runtime/market_collector.log" 2>&1 < /dev/null
