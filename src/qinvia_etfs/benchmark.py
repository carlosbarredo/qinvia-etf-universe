"""Validate the Yahoo cache and compare eligible ETF histories with SPY."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from qinvia_etfs.market import PRICE_COLUMNS, SCHEMA_VERSION, storage_key


ANALYSIS_VERSION = "benchmark_vs_spy_1.0"
MIN_PRIMARY_RETURNS = 252
MIN_EXPLORATORY_RETURNS = 63


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.suffix == ".csv":
        frame.to_csv(temporary, index=False)
    elif path.suffix == ".parquet":
        frame.to_parquet(temporary, index=False, compression="zstd")
    else:
        raise ValueError(f"Unsupported output format: {path}")
    os.replace(temporary, path)


def load_universe(path: Path) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("eligibility") != "eligible":
                continue
            catalog_symbol = str(row.get("ticker", "")).strip().upper()
            symbol = catalog_symbol.replace(".", "-")
            item = grouped.setdefault(
                symbol,
                {
                    "request_symbol": symbol,
                    "catalog_symbols": set(),
                    "product_ids": [],
                    "names": [],
                    "current_names": [],
                    "asset_classes": set(),
                    "sources": set(),
                    "current_listing": False,
                    "current_first_seen_year": None,
                    "first_seen_year": None,
                    "last_seen_year": None,
                },
            )
            item["catalog_symbols"].add(catalog_symbol)
            item["product_ids"].append(str(row.get("product_id", "")))
            name = str(row.get("name", "")).strip()
            if name:
                item["names"].append(name)
            current = as_bool(row.get("current_listing"))
            if current and name:
                item["current_names"].append(name)
            item["current_listing"] = bool(item["current_listing"] or current)
            asset_class = str(row.get("asset_class", "")).strip()
            if asset_class:
                item["asset_classes"].add(asset_class)
            item["sources"].update(
                source for source in str(row.get("sources", "")).split("|") if source
            )
            first_raw = str(row.get("first_seen_year", "")).strip()
            last_raw = str(row.get("last_seen_year", "")).strip()
            if first_raw.isdigit():
                first = int(first_raw)
                item["first_seen_year"] = (
                    first
                    if item["first_seen_year"] is None
                    else min(int(item["first_seen_year"]), first)
                )
                if current:
                    item["current_first_seen_year"] = (
                        first
                        if item["current_first_seen_year"] is None
                        else min(int(item["current_first_seen_year"]), first)
                    )
            if last_raw.isdigit():
                last = int(last_raw)
                item["last_seen_year"] = (
                    last
                    if item["last_seen_year"] is None
                    else max(int(item["last_seen_year"]), last)
                )
    for item in grouped.values():
        preferred_names = item["current_names"] or item["names"]
        item["name"] = preferred_names[-1] if preferred_names else ""
        item["identity_count"] = len(item["product_ids"])
        item["catalog_symbols"] = "|".join(sorted(item["catalog_symbols"]))
        item["asset_classes"] = "|".join(sorted(item["asset_classes"]))
        item["sources"] = "|".join(sorted(item["sources"]))
    return grouped


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            str(row["request_symbol"]).strip().upper(): row
            for row in csv.DictReader(handle)
            if row.get("request_symbol")
        }


def paths_for(market_root: Path, symbol: str) -> tuple[Path, Path]:
    key = storage_key(symbol)
    bucket = key[0]
    raw = market_root / "data" / "raw" / "market" / "yahoo"
    return raw / "daily" / bucket / f"{key}.parquet", raw / "metadata" / bucket / f"{key}.json"


def analysis_disposition(
    identity: dict[str, Any], metadata: dict[str, Any], override: dict[str, str] | None
) -> tuple[str, str]:
    if override:
        status = str(override.get("analysis_status", "")).strip()
        if status == "usable":
            return "usable", "curated_identity_override"
        if status:
            return status, str(override.get("reason", "curated_identity_override"))

    if metadata.get("status") != "success":
        return str(metadata.get("status") or "missing"), str(
            metadata.get("error_message") or "Yahoo history is unavailable"
        )

    instrument = str((metadata.get("source_metadata") or {}).get("instrumentType", "")).upper()
    if instrument == "ETF":
        return "usable", "yahoo_instrument_type_etf"

    if identity["current_listing"]:
        # Yahoo often labels very recent ETFs as EQUITY until its fund metadata
        # catches up. A current exchange listing is accepted only if the price
        # history does not clearly predate that identity.
        first_date = str(metadata.get("first_date", ""))
        raw_year = int(first_date[:4]) if len(first_date) >= 4 and first_date[:4].isdigit() else None
        observed_year = identity.get("current_first_seen_year")
        if (
            instrument == "EQUITY"
            and raw_year is not None
            and observed_year is not None
            and int(observed_year) > 2010
            and raw_year < int(observed_year) - 1
        ):
            return "identity_mismatch", "Yahoo EQUITY history predates the current ETF identity"
        if "nasdaq" in str(identity.get("sources", "")):
            return "usable", "current_exchange_etf_listing"

    return "identity_mismatch", f"Yahoo instrument type is {instrument or 'missing'}"


def performance_metrics(prices: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(prices, errors="coerce").dropna()
    clean = clean[clean > 0]
    if len(clean) < 2:
        return {}
    days = int((clean.index[-1] - clean.index[0]).days)
    years = days / 365.2425
    if years <= 0:
        return {}
    returns = clean.pct_change().dropna()
    if returns.empty:
        return {}
    cumulative = float(clean.iloc[-1] / clean.iloc[0] - 1.0)
    cagr = float((clean.iloc[-1] / clean.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(returns.std(ddof=1) * math.sqrt(252)) if len(returns) > 1 else math.nan
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * math.sqrt(252))
        if len(returns) > 1 and returns.std(ddof=1) > 0
        else math.nan
    )
    downside_deviation = float(np.sqrt(np.mean(np.minimum(returns, 0.0) ** 2)))
    sortino = (
        float(returns.mean() / downside_deviation * math.sqrt(252))
        if downside_deviation > 0
        else math.nan
    )
    wealth = clean / float(clean.iloc[0])
    drawdown = wealth / wealth.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    ulcer_index = float(np.sqrt(np.mean(np.square(drawdown.to_numpy(dtype=float)))))
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else math.nan
    martin = cagr / ulcer_index if ulcer_index > 0 else math.nan
    return {
        "observations": int(len(clean)),
        "return_observations": int(len(returns)),
        "years": years,
        "cumulative_return": cumulative,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "ulcer_index": ulcer_index,
        "calmar": calmar,
        "martin": martin,
    }


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 15) -> str:
    if frame.empty:
        return "(sin resultados)"
    subset = frame.loc[:, columns].head(limit).copy()
    for column in subset.columns:
        if pd.api.types.is_float_dtype(subset[column]):
            subset[column] = subset[column].map(lambda value: f"{value:.4f}" if finite(value) else "")
    header = "| " + " | ".join(subset.columns) + " |"
    rule = "|" + "|".join("---" for _ in subset.columns) + "|"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in subset.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows])


def metric_summary(frame: pd.DataFrame, metric: str) -> dict[str, Any]:
    benchmark_column = f"spy_{metric}"
    valid = frame[frame[metric].map(finite) & frame[benchmark_column].map(finite)]
    beaten = int((valid[metric] > valid[benchmark_column]).sum())
    denominator = int(len(valid))
    return {
        "denominator": denominator,
        "beat_spy": beaten,
        "did_not_beat_spy": denominator - beaten,
        "percent_beat_spy": beaten / denominator if denominator else None,
    }


def run(market_root: Path, universe_path: Path, overrides_path: Path, export_root: Path) -> dict[str, Any]:
    started_at = utc_now()
    identities = load_universe(universe_path)
    overrides = load_overrides(overrides_path)
    issues: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    parquet_by_symbol: dict[str, Path] = {}
    raw_counts: Counter[str] = Counter()

    for symbol, identity in sorted(identities.items()):
        price_path, metadata_path = paths_for(market_root, symbol)
        metadata = read_json(metadata_path)
        raw_status = str(metadata.get("status") or "missing")
        raw_counts[raw_status] += 1
        instrument = str((metadata.get("source_metadata") or {}).get("instrumentType", ""))
        disposition, reason = analysis_disposition(identity, metadata, overrides.get(symbol))
        row = {
            "request_symbol": symbol,
            "name": identity["name"],
            "identity_count": identity["identity_count"],
            "current_listing": identity["current_listing"],
            "asset_classes": identity["asset_classes"],
            "sources": identity["sources"],
            "raw_status": raw_status,
            "instrument_type": instrument,
            "first_date": metadata.get("first_date", ""),
            "last_date": metadata.get("last_date", ""),
            "rows": int(metadata.get("rows", 0) or 0),
            "analysis_status": disposition,
            "analysis_reason": reason,
        }
        coverage_rows.append(row)
        if raw_status != "success":
            continue
        if not price_path.exists():
            issues.append({"symbol": symbol, "severity": "error", "issue": "missing_parquet"})
            continue
        try:
            parquet = pq.ParquetFile(price_path)
            schema_metadata = parquet.schema_arrow.metadata or {}
            schema_version = schema_metadata.get(b"qinvia_schema_version", b"").decode("utf-8")
            if schema_version != SCHEMA_VERSION:
                issues.append({"symbol": symbol, "severity": "error", "issue": "schema_version_mismatch"})
            missing_columns = sorted(set(PRICE_COLUMNS) - set(parquet.schema_arrow.names))
            if missing_columns:
                issues.append(
                    {
                        "symbol": symbol,
                        "severity": "error",
                        "issue": "missing_columns:" + "|".join(missing_columns),
                    }
                )
            expected_rows = int(metadata.get("rows", 0) or 0)
            if parquet.metadata.num_rows != expected_rows:
                issues.append({"symbol": symbol, "severity": "error", "issue": "row_count_mismatch"})
            expected_hash = str(metadata.get("sha256", ""))
            if expected_hash and sha256_file(price_path) != expected_hash:
                issues.append({"symbol": symbol, "severity": "error", "issue": "sha256_mismatch"})
            parquet_by_symbol[symbol] = price_path
        except Exception as error:
            issues.append(
                {
                    "symbol": symbol,
                    "severity": "error",
                    "issue": f"parquet_read_error:{type(error).__name__}:{error}",
                }
            )

    if "SPY" not in parquet_by_symbol:
        raise RuntimeError("SPY Parquet is unavailable")
    spy_frame = pd.read_parquet(parquet_by_symbol["SPY"], columns=["session_date", "adj_close"])
    spy_frame["session_date"] = pd.to_datetime(spy_frame["session_date"])
    spy = spy_frame.drop_duplicates("session_date").set_index("session_date")["adj_close"].sort_index()

    benchmark_rows: list[dict[str, Any]] = []
    coverage_lookup = {row["request_symbol"]: row for row in coverage_rows}
    for symbol, identity in sorted(identities.items()):
        if symbol == "SPY" or coverage_lookup[symbol]["analysis_status"] != "usable":
            continue
        path = parquet_by_symbol.get(symbol)
        if path is None:
            continue
        try:
            frame = pd.read_parquet(path, columns=["session_date", "adj_close"])
            frame["session_date"] = pd.to_datetime(frame["session_date"])
            duplicate_dates = int(frame["session_date"].duplicated().sum())
            if duplicate_dates:
                issues.append({"symbol": symbol, "severity": "error", "issue": "duplicate_sessions"})
            series = frame.drop_duplicates("session_date").set_index("session_date")["adj_close"].sort_index()
            override = overrides.get(symbol, {})
            if override.get("usable_start"):
                series = series.loc[pd.Timestamp(override["usable_start"]) :]
            if override.get("usable_end"):
                series = series.loc[: pd.Timestamp(override["usable_end"])]
            joined = pd.concat({"etf": series, "spy": spy}, axis=1, join="inner").dropna()
            joined = joined[(joined["etf"] > 0) & (joined["spy"] > 0)]
            etf_metrics = performance_metrics(joined["etf"])
            spy_metrics = performance_metrics(joined["spy"])
            if not etf_metrics or not spy_metrics:
                coverage_lookup[symbol]["analysis_status"] = "insufficient_data"
                coverage_lookup[symbol]["analysis_reason"] = "Fewer than two comparable sessions"
                continue
            returns = joined["etf"].pct_change().dropna()
            row: dict[str, Any] = {
                "request_symbol": symbol,
                "name": identity["name"],
                "current_listing": identity["current_listing"],
                "identity_count": identity["identity_count"],
                "asset_classes": identity["asset_classes"],
                "start_date": joined.index[0].date().isoformat(),
                "end_date": joined.index[-1].date().isoformat(),
                "extreme_return_days_gt_50pct": int((returns.abs() > 0.50).sum()),
            }
            row.update(etf_metrics)
            row.update({f"spy_{key}": value for key, value in spy_metrics.items()})
            for metric in ("cagr", "sharpe", "calmar", "martin"):
                row[f"beat_spy_{metric}"] = bool(
                    finite(row.get(metric))
                    and finite(row.get(f"spy_{metric}"))
                    and float(row[metric]) > float(row[f"spy_{metric}"])
                )
                row[f"excess_{metric}"] = (
                    float(row[metric]) - float(row[f"spy_{metric}"])
                    if finite(row.get(metric)) and finite(row.get(f"spy_{metric}"))
                    else math.nan
                )
            row["beat_spy_all_four"] = all(
                bool(row[f"beat_spy_{metric}"]) for metric in ("cagr", "sharpe", "calmar", "martin")
            )
            row["economic_qc_pass"] = bool(row["extreme_return_days_gt_50pct"] == 0)
            row["statistical_primary_sample"] = bool(
                int(row["return_observations"]) >= MIN_PRIMARY_RETURNS and float(row["years"]) >= 0.9
            )
            row["primary_sample"] = bool(
                row["statistical_primary_sample"] and row["economic_qc_pass"]
            )
            row["exploratory_sample"] = bool(
                int(row["return_observations"]) >= MIN_EXPLORATORY_RETURNS
            )
            benchmark_rows.append(row)
        except Exception as error:
            issues.append(
                {
                    "symbol": symbol,
                    "severity": "error",
                    "issue": f"analysis_read_error:{type(error).__name__}:{error}",
                }
            )

    coverage = pd.DataFrame(coverage_rows).sort_values("request_symbol").reset_index(drop=True)
    benchmark = pd.DataFrame(benchmark_rows).sort_values("request_symbol").reset_index(drop=True)
    issues_frame = pd.DataFrame(issues, columns=["symbol", "severity", "issue"])
    primary = benchmark[benchmark["primary_sample"]].copy()
    statistical_primary = benchmark[benchmark["statistical_primary_sample"]].copy()
    metric_results = {
        metric: metric_summary(primary, metric) for metric in ("cagr", "sharpe", "calmar", "martin")
    }
    all_four = int(primary["beat_spy_all_four"].sum()) if not primary.empty else 0
    lifecycle_results: dict[str, Any] = {}
    for label, current_flag in (("current", True), ("historical_only", False)):
        cohort = primary[primary["current_listing"] == current_flag]
        lifecycle_results[label] = {
            "count": len(cohort),
            "metrics": {
                metric: metric_summary(cohort, metric)
                for metric in ("cagr", "sharpe", "calmar", "martin")
            },
            "beat_spy_all_four": int(cohort["beat_spy_all_four"].sum()),
        }

    processed_root = export_root / "data" / "processed" / "market"
    write_frame(coverage, processed_root / "market_coverage.csv")
    write_frame(benchmark, processed_root / "benchmark_vs_spy.csv")
    write_frame(benchmark, processed_root / "benchmark_vs_spy.parquet")
    write_frame(issues_frame, processed_root / "market_qa_issues.csv")

    orphan_files = 0
    expected_keys = {storage_key(symbol) for symbol in identities}
    daily_root = market_root / "data" / "raw" / "market" / "yahoo" / "daily"
    for path in daily_root.rglob("*.parquet"):
        if path.stem not in expected_keys:
            orphan_files += 1

    summary = {
        "analysis_version": ANALYSIS_VERSION,
        "started_at": started_at,
        "completed_at": utc_now(),
        "universe_identity_count": sum(int(item["identity_count"]) for item in identities.values()),
        "universe_symbol_count": len(identities),
        "raw_status_counts": dict(raw_counts),
        "analysis_status_counts": dict(Counter(row["analysis_status"] for row in coverage_rows)),
        "parquet_files_validated": len(parquet_by_symbol),
        "qa_issue_count": len(issues),
        "orphan_parquet_count": orphan_files,
        "analyzed_symbol_count": len(benchmark),
        "primary_sample_count": len(primary),
        "statistical_primary_before_economic_qc": len(statistical_primary),
        "economic_qc_excluded_from_primary": int(
            len(statistical_primary) - len(primary)
        ),
        "exploratory_sample_count": int(benchmark["exploratory_sample"].sum()) if not benchmark.empty else 0,
        "metric_results": metric_results,
        "lifecycle_results": lifecycle_results,
        "beat_spy_all_four": {
            "denominator": len(primary),
            "beat_spy": all_four,
            "percent_beat_spy": all_four / len(primary) if len(primary) else None,
        },
        "methodology": {
            "return_series": "Yahoo Adj Close total-return proxy",
            "benchmark_alignment": "Exact common sessions from each ETF's first usable Yahoo observation",
            "annualization": 252,
            "risk_free_rate": 0.0,
            "primary_minimum_return_observations": MIN_PRIMARY_RETURNS,
            "cost_model": "QINVIA Historical Adaptive Cost and Slippage Model v1.0",
            "cost_treatment": "Buy & Hold; no fictitious switching cost under section 7",
        },
    }
    atomic_json(processed_root / "benchmark_summary.json", summary)

    top_cagr = primary.sort_values("excess_cagr", ascending=False)
    lines = [
        "# ETFs frente a SPY desde el inicio comparable",
        "",
        f"Generado: {summary['completed_at']}",
        "",
        "## Resultado principal",
        "",
        f"La muestra principal contiene **{len(primary)}** series con al menos {MIN_PRIMARY_RETURNS} retornos diarios comparables y sin saltos ajustados superiores al 50 %.",
        "Cada ETF se compara con SPY sobre exactamente sus mismas sesiones disponibles, desde el primer cierre ajustado utilizable hasta el último.",
        "",
        "| Métrica | Superan SPY | Comparables | Porcentaje |",
        "|---|---:|---:|---:|",
    ]
    labels = {"cagr": "CAGR", "sharpe": "Sharpe", "calmar": "Calmar", "martin": "Martin"}
    for metric, result in metric_results.items():
        percentage = result["percent_beat_spy"]
        lines.append(
            f"| {labels[metric]} | {result['beat_spy']} | {result['denominator']} | "
            f"{percentage:.2%} |" if percentage is not None else f"| {labels[metric]} | 0 | 0 | — |"
        )
    all_percentage = summary["beat_spy_all_four"]["percent_beat_spy"]
    lines.extend(
        [
            f"| Las cuatro | {all_four} | {len(primary)} | {all_percentage:.2%} |"
            if all_percentage is not None
            else "| Las cuatro | 0 | 0 | — |",
            "",
            "## Resultado por ciclo de vida",
            "",
            "| Cohorte | Series | CAGR | Sharpe | Calmar | Martin | Las cuatro |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, lifecycle in lifecycle_results.items():
        cohort_label = "Actuales" if label == "current" else "Solo históricas"
        metric_cells = [
            f"{lifecycle['metrics'][metric]['beat_spy']} ({lifecycle['metrics'][metric]['percent_beat_spy']:.2%})"
            for metric in ("cagr", "sharpe", "calmar", "martin")
        ]
        all_cell = (
            f"{lifecycle['beat_spy_all_four']} "
            f"({lifecycle['beat_spy_all_four'] / lifecycle['count']:.2%})"
            if lifecycle["count"]
            else "0 (—)"
        )
        lines.append(
            f"| {cohort_label} | {lifecycle['count']} | "
            + " | ".join(metric_cells)
            + f" | {all_cell} |"
        )
    lines.extend(
        [
            "",
            "## Cobertura y calidad",
            "",
            f"- Identidades elegibles: {summary['universe_identity_count']}.",
            f"- Símbolos Yahoo deduplicados: {summary['universe_symbol_count']}.",
            f"- Parquet validados: {summary['parquet_files_validated']}.",
            f"- Sin historia diaria en Yahoo: {raw_counts.get('no_data', 0)}.",
            f"- Con historia insuficiente para calcular retornos: {summary['analysis_status_counts'].get('insufficient_data', 0)}.",
            f"- Excluidas por conflicto de identidad del ticker: {summary['analysis_status_counts'].get('identity_mismatch', 0)}.",
            f"- Series analizadas: {summary['analyzed_symbol_count']}.",
            f"- Series apartadas de la muestra principal por anomalías económicas: {summary['economic_qc_excluded_from_primary']}.",
            f"- Incidencias de integridad: {summary['qa_issue_count']}.",
            f"- Parquet conservados fuera del universo final: {summary['orphan_parquet_count']}.",
            "",
            "Las series cuyo ticker de Yahoo corresponde hoy a una acción u otro instrumento se conservan en bruto, pero se excluyen del estudio como `identity_mismatch`.",
            "Esto evita atribuir a un ETF histórico la rentabilidad posterior de un ticker reutilizado.",
            "El universo sí conserva productos desaparecidos, pero la cobertura histórica gratuita de Yahoo es mucho menor que la de los productos actuales; por ello el desglose de ciclo de vida es obligatorio y las cifras agregadas no se presentan como una eliminación completa del sesgo de supervivencia.",
            "",
            "## Definiciones",
            "",
            "- Rentabilidad total: variación del `Adj Close` de Yahoo, antes de impuestos.",
            "- Sharpe: retornos diarios anualizados con 252 sesiones y tipo libre de riesgo del 0 %.",
            "- Calmar: CAGR dividido por el valor absoluto del máximo drawdown.",
            "- Martin: CAGR dividido por el Ulcer Index.",
            "- Esta comparación es Buy & Hold. Según la sección 7 del modelo canónico de costes y deslizamientos, no se imputa un coste ficticio de rotación.",
            "",
            "## Mayor exceso de CAGR frente a SPY",
            "",
            markdown_table(
                top_cagr,
                ["request_symbol", "name", "start_date", "end_date", "cagr", "spy_cagr", "excess_cagr"],
            ),
            "",
            "## Archivos",
            "",
            "- `benchmark_vs_spy.parquet`: resultados completos por símbolo.",
            "- `benchmark_vs_spy.csv`: copia para inspección manual.",
            "- `market_coverage.csv`: decisión de cobertura e identidad para cada símbolo.",
            "- `market_qa_issues.csv`: incidencias automáticas.",
            "- `benchmark_summary.json`: resumen legible por máquina.",
            "",
        ]
    )
    report_path = processed_root / "benchmark_vs_spy_report.md"
    temporary = report_path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temporary, report_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--export-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run(
        args.market_root.resolve(),
        args.universe.resolve(),
        args.overrides.resolve(),
        args.export_root.resolve(),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["qa_issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
