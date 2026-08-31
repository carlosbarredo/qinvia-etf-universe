#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${QINVIA_PYTHON_BIN:-$project_root/.venv/bin/python}"
market_root="${QINVIA_MARKET_WORK_ROOT:-$project_root/.local-wsl/market}"

cd "$project_root"
exec env PYTHONPATH="$project_root/src" "$python_bin" -m qinvia_etfs.benchmark \
    --market-root "$market_root" \
    --universe "$project_root/data/processed/universe/eligible_universe.csv" \
    --overrides "$project_root/data/curated/market/identity_overrides.csv" \
    --export-root "$project_root"
