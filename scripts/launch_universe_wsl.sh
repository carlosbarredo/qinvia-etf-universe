#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
work_root="${QINVIA_UNIVERSE_WORK_ROOT:-$project_root/.local-wsl/universe}"
mkdir -p "$work_root/runtime"

pid_file="$work_root/runtime/universe_collector.pid"
if [[ -f "$pid_file" ]]; then
    existing_pid="$(tr -dc '0-9' < "$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "already_running pid=$existing_pid"
        exit 0
    fi
fi

python_bin="${QINVIA_PYTHON_BIN:-$project_root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
    echo "missing_wsl_venv=$python_bin" >&2
    exit 1
fi

echo "$$" > "$pid_file"
exec env \
    PYTHONPATH="$project_root/src" \
    QINVIA_WORK_ROOT="$work_root" \
    QINVIA_EXPORT_ROOT="$project_root" \
    "$python_bin" -m qinvia_etfs.universe \
    >> "$work_root/runtime/universe_collector.log" 2>&1 < /dev/null
