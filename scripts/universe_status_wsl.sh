#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work_root="${QINVIA_UNIVERSE_WORK_ROOT:-$project_root/.local-wsl/universe}"
pid_file="$work_root/runtime/universe_collector.pid"
status_file="$work_root/runtime/universe_status.json"

if [[ -f "$pid_file" ]]; then
    collector_pid="$(tr -dc '0-9' < "$pid_file")"
    if [[ -n "$collector_pid" ]] && kill -0 "$collector_pid" 2>/dev/null; then
        echo "process=running pid=$collector_pid"
    else
        echo "process=stopped pid=${collector_pid:-unknown}"
    fi
else
    echo "process=not_started"
fi

if [[ -f "$status_file" ]]; then
    cat "$status_file"
fi
