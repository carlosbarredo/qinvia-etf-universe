#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
market_root="${QINVIA_MARKET_WORK_ROOT:-$project_root/.local-wsl/market}"
pid_file="$market_root/runtime/market_collector.pid"
status_file="$market_root/runtime/market_collector_status.json"

if [[ -f "$pid_file" ]]; then
    pid="$(tr -dc '0-9' < "$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        echo "process=running pid=$pid"
    else
        echo "process=stopped pid=${pid:-unknown}"
    fi
else
    echo "process=not_started"
fi

if [[ -f "$status_file" ]]; then
    cat "$status_file"
fi
