"""Build the frozen 1A ETF-universe study dataset.

The study keeps the full downloaded catalogue intact and creates a research
cohort using an inception cutoff.  ETF performance remains inception-to-own-end
and SPY is aligned to the exact same sessions, as in ``benchmark.py``.  The
common-period curves are a separate descriptive lens beginning at the cutoff.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from qinvia_etfs.benchmark import performance_metrics
from qinvia_etfs.dbf import dbf_metrics
from qinvia_etfs.management_style import MANAGEMENT_EVIDENCE_VERSION
from qinvia_etfs.market import storage_key
from qinvia_etfs.rwm import cash_wealth, load_cash_rates, relative_wealth_martin
from qinvia_etfs.taxonomy import TAXONOMY_VERSION, classify_product


STUDY_VERSION = "etf_universe_1A"
DEFAULT_CUTOFF = "2022-03-01"
MIN_RETURN_OBSERVATIONS = 1008
MIN_END_DATE = "2022-12-30"
METRICS = ("cagr", "sortino", "calmar", "martin")
SUPPLEMENTARY_METRICS = ("dbf_signed", "rwm_score")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def raw_price_path(market_root: Path, symbol: str) -> Path:
    key = storage_key(symbol)
    return market_root / "data" / "raw" / "market" / "yahoo" / "daily" / key[0] / f"{key}.parquet"


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False, compression="zstd")
    elif path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output: {path}")


def add_taxonomy(frame: pd.DataFrame) -> pd.DataFrame:
    taxonomy = pd.DataFrame(
        [classify_product(row.name, row.asset_classes) for row in frame.itertuples(index=False)]
    )
    return pd.concat([frame.reset_index(drop=True), taxonomy], axis=1)


def apply_management_style_audit(frame: pd.DataFrame, audit_path: Path) -> pd.DataFrame:
    """Overlay the complete, sourced management-style audit on the study cohort.

    The audit is keyed to the canonical economic product. Historical ticker
    aliases inherit the canonical decision, so every qualifying row receives
    the same evidence-backed management label without duplicating research.
    """

    audit = pd.read_csv(audit_path, keep_default_na=False)
    required = {
        "request_symbol",
        "management_style",
        "management_confidence",
        "management_source",
        "management_evidence_version",
        "evidence",
        "source_url",
        "review_note",
    }
    missing_columns = required.difference(audit.columns)
    if missing_columns:
        raise ValueError(f"Management audit lacks columns: {sorted(missing_columns)}")
    if audit["request_symbol"].duplicated().any():
        raise ValueError("Management audit contains duplicate request symbols")

    expected = set(frame.loc[frame["analysis_primary"], "request_symbol"].astype(str))
    observed = set(audit["request_symbol"].astype(str))
    missing_symbols = sorted(expected.difference(observed))
    extra_symbols = sorted(observed.difference(expected))
    if missing_symbols or extra_symbols:
        raise ValueError(
            "Management audit must cover the canonical cohort exactly; "
            f"missing={missing_symbols[:10]}, extra={extra_symbols[:10]}"
        )
    if audit["management_style"].eq("not_determined").any():
        raise ValueError("Management audit still contains not_determined rows")

    result = frame.copy()
    result["management_style_name_based"] = result["management_style"]
    result["management_confidence_name_based"] = result["management_confidence"]
    result["management_audit_symbol"] = result["canonical_symbol"].astype(str)
    rename = {
        "request_symbol": "management_audit_symbol",
        "evidence": "management_evidence",
        "source_url": "management_source_url",
        "review_note": "management_review_note",
        "source_zip": "management_source_zip",
    }
    keep = [column for column in audit.columns if column != "name"]
    evidence = audit[keep].rename(columns=rename)
    result = result.drop(columns=["management_style", "management_confidence"]).merge(
        evidence,
        on="management_audit_symbol",
        how="left",
        validate="many_to_one",
    )
    if result["management_style"].isna().any():
        missing = result.loc[result["management_style"].isna(), "request_symbol"].tolist()
        raise ValueError(f"Management audit did not resolve qualifying rows: {missing[:10]}")
    result["taxonomy_evidence"] = (
        result["taxonomy_evidence"].astype(str)
        + "|management_audit:"
        + result["management_style"].astype(str)
    )
    return result


def add_decision_flags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for metric in (*METRICS, *SUPPLEMENTARY_METRICS):
        result[f"beat_spy_{metric}"] = (
            pd.to_numeric(result[metric], errors="coerce")
            > pd.to_numeric(result[f"spy_{metric}"], errors="coerce")
        )
        result[f"excess_{metric}"] = result[metric] - result[f"spy_{metric}"]
    result["beat_spy_cagr_and_martin"] = result["beat_spy_cagr"] & result["beat_spy_martin"]
    result["beat_spy_cagr_and_rwm"] = result["beat_spy_cagr"] & result["beat_spy_rwm_score"]
    result["beat_spy_all_four"] = result[[f"beat_spy_{metric}" for metric in METRICS]].all(axis=1)
    result["beats_count"] = result[[f"beat_spy_{metric}" for metric in METRICS]].sum(axis=1).astype(int)
    return result


def select_cohort(benchmark: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    start = pd.to_datetime(benchmark["start_date"], errors="coerce")
    end = pd.to_datetime(benchmark["end_date"], errors="coerce")
    mask = (
        (start <= pd.Timestamp(cutoff))
        & (end >= pd.Timestamp(MIN_END_DATE))
        & (benchmark["return_observations"] >= MIN_RETURN_OBSERVATIONS)
        & benchmark["economic_qc_pass"].astype(bool)
    )
    selected = benchmark.loc[mask].copy().sort_values("request_symbol").reset_index(drop=True)
    selected["study_cutoff"] = cutoff
    selected["selection_reason"] = (
        f"first_usable_session_on_or_before_{cutoff}|"
        f"at_least_{MIN_RETURN_OBSERVATIONS}_daily_returns|economic_qc_pass"
    )
    return add_taxonomy(selected)


def mark_economic_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    """Consolidate exact-name historical/current ticker aliases without deleting rows."""

    result = frame.copy()
    result["analysis_primary"] = True
    result["canonical_symbol"] = result["request_symbol"]
    result["alias_consolidation_reason"] = ""
    name_key = result["normalized_name"].str.lower().str.replace(r"[^a-z0-9]+", "", regex=True)
    result["economic_name_key"] = name_key
    for _, group in result.groupby("economic_name_key"):
        if len(group) <= 1 or int(group["current_listing"].sum()) != 1:
            continue
        current = group[group["current_listing"]].sort_values("end_date", ascending=False).iloc[0]
        canonical = str(current["request_symbol"])
        result.loc[group.index, "canonical_symbol"] = canonical
        aliases = group.index[group["request_symbol"] != canonical]
        result.loc[aliases, "analysis_primary"] = False
        result.loc[aliases, "alias_consolidation_reason"] = "exact_name_historical_alias_of_current_ticker"
        result.loc[current.name, "alias_consolidation_reason"] = "canonical_current_ticker_for_exact_name_alias_group"
    return result


def group_summary(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, group in frame.groupby(column, dropna=False):
        row: dict[str, Any] = {
            "dimension": column,
            "group": str(label),
            "n": int(len(group)),
            "current_listings": int(group["current_listing"].sum()),
            "historical_identities": int((~group["current_listing"]).sum()),
            "median_excess_cagr": float(group["excess_cagr"].median()),
            "median_excess_martin": float(group["excess_martin"].median()),
        }
        for metric in METRICS:
            count = int(group[f"beat_spy_{metric}"].sum())
            row[f"beat_spy_{metric}"] = count
            row[f"rate_beat_spy_{metric}"] = count / len(group)
        rwm_count = int(group["beat_spy_rwm_score"].sum())
        row["beat_spy_rwm_score"] = rwm_count
        row["rate_beat_spy_rwm_score"] = rwm_count / len(group)
        cagr_rwm = int(group["beat_spy_cagr_and_rwm"].sum())
        row["beat_spy_cagr_and_rwm"] = cagr_rwm
        row["rate_beat_spy_cagr_and_rwm"] = cagr_rwm / len(group)
        both = int(group["beat_spy_cagr_and_martin"].sum())
        all_four = int(group["beat_spy_all_four"].sum())
        row["beat_spy_cagr_and_martin"] = both
        row["rate_beat_spy_cagr_and_martin"] = both / len(group)
        row["beat_spy_all_four"] = all_four
        row["rate_beat_spy_all_four"] = all_four / len(group)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["n", "group"], ascending=[False, True]).reset_index(drop=True)


def build_group_summaries(frame: pd.DataFrame) -> pd.DataFrame:
    dimensions = (
        "asset_class_refined",
        "management_style",
        "exposure_type",
        "primary_strategy",
        "sector_theme",
        "theme",
        "geography",
        "taxonomy_confidence",
    )
    return pd.concat([group_summary(frame, column) for column in dimensions], ignore_index=True)


def load_adjusted_series(path: Path, cutoff: pd.Timestamp) -> pd.Series:
    frame = pd.read_parquet(path, columns=["session_date", "adj_close"])
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    series = (
        frame.drop_duplicates("session_date")
        .set_index("session_date")["adj_close"]
        .sort_index()
        .loc[cutoff:]
    )
    series = pd.to_numeric(series, errors="coerce")
    return series.where(series > 0)


def load_full_adjusted_series(path: Path) -> pd.Series:
    frame = pd.read_parquet(path, columns=["session_date", "adj_close"])
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    series = frame.drop_duplicates("session_date").set_index("session_date")["adj_close"].sort_index()
    series = pd.to_numeric(series, errors="coerce")
    return series.where(series > 0)


def enrich_comparable_metrics(
    frame: pd.DataFrame,
    market_root: Path,
    cash_path: Path,
) -> pd.DataFrame:
    """Recompute all document metrics on each ETF's exact SPY-aligned window."""

    spy = load_full_adjusted_series(raw_price_path(market_root, "SPY"))
    cash_rates = load_cash_rates(cash_path)
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in frame.itertuples(index=False):
        symbol = str(row.request_symbol)
        path = raw_price_path(market_root, symbol)
        if not path.exists():
            failures.append(f"{symbol}:missing_price_file")
            continue
        series = load_full_adjusted_series(path).loc[pd.Timestamp(row.start_date) : pd.Timestamp(row.end_date)]
        joined = pd.concat({"etf": series, "spy": spy}, axis=1, join="inner").dropna()
        joined = joined[(joined.etf > 0) & (joined.spy > 0)]
        etf_metrics = performance_metrics(joined.etf)
        spy_metrics = performance_metrics(joined.spy)
        if not etf_metrics or not spy_metrics:
            failures.append(f"{symbol}:insufficient_comparable_data")
            continue
        etf_dbf = dbf_metrics(joined.etf)
        spy_dbf = dbf_metrics(joined.spy)
        cash_curve = cash_wealth(joined.index, cash_rates)
        etf_rwm = relative_wealth_martin(joined.etf, cash_curve)
        spy_rwm = relative_wealth_martin(joined.spy, cash_curve)
        values: dict[str, Any] = {"request_symbol": symbol}
        values.update(etf_metrics)
        values.update({f"spy_{key}": value for key, value in spy_metrics.items()})
        values.update(etf_dbf)
        values.update({f"spy_{key}": value for key, value in spy_dbf.items()})
        values.update(etf_rwm)
        values.update({f"spy_{key}": value for key, value in spy_rwm.items()})
        rows.append(values)
    if failures:
        raise RuntimeError("Comparable metric enrichment failed: " + ", ".join(failures[:20]))
    enriched = frame.set_index("request_symbol").copy()
    updates = pd.DataFrame(rows).set_index("request_symbol")
    for column in updates.columns:
        enriched[column] = updates[column]
    return add_decision_flags(enriched.reset_index())


def build_common_period_curves(
    selected: pd.DataFrame, market_root: Path, cutoff: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cutoff_ts = pd.Timestamp(cutoff)
    series_by_symbol: dict[str, pd.Series] = {}
    missing: list[str] = []
    late_at_cutoff: list[str] = []
    for symbol in selected["request_symbol"]:
        path = raw_price_path(market_root, str(symbol))
        if not path.exists():
            missing.append(str(symbol))
            continue
        series = load_adjusted_series(path, cutoff_ts)
        if series.dropna().empty:
            missing.append(str(symbol))
            continue
        if series.first_valid_index() > cutoff_ts + pd.Timedelta(days=7):
            late_at_cutoff.append(str(symbol))
            continue
        series_by_symbol[str(symbol)] = series

    spy_path = raw_price_path(market_root, "SPY")
    spy = load_adjusted_series(spy_path, cutoff_ts).rename("SPY")
    panel = pd.concat(series_by_symbol, axis=1).sort_index()
    panel = panel.reindex(spy.index)
    first = panel.apply(lambda column: column.dropna().iloc[0] if column.notna().any() else np.nan)
    normalized = panel.divide(first, axis=1) * 100.0

    common_end = spy.dropna().index.max()
    start_ok = normalized.apply(lambda column: column.first_valid_index()) <= cutoff_ts + pd.Timedelta(days=7)
    end_ok = normalized.apply(lambda column: column.last_valid_index()) >= common_end - pd.Timedelta(days=3)
    coverage = normalized.notna().mean()
    complete_symbols = normalized.columns[start_ok & end_ok & (coverage >= 0.985)].tolist()

    curve = pd.DataFrame(index=spy.index)
    curve["spy"] = spy / float(spy.dropna().iloc[0]) * 100.0
    curve["etf_mean_all_available"] = normalized.mean(axis=1, skipna=True)
    curve["etf_median_all_available"] = normalized.median(axis=1, skipna=True)
    fixed_complete = normalized[complete_symbols]
    curve["etf_mean_fixed_complete"] = fixed_complete.mean(axis=1, skipna=True)
    for percentile, quantile in ((10, 0.10), (25, 0.25), (50, 0.50), (75, 0.75), (90, 0.90)):
        curve[f"etf_p{percentile}_fixed_complete"] = fixed_complete.quantile(
            quantile, axis=1, interpolation="linear"
        )
    curve["available_members"] = normalized.notna().sum(axis=1)
    curve = curve.dropna(subset=["spy", "etf_mean_all_available"]).reset_index(names="session_date")

    meta = selected.set_index("request_symbol")
    group_curves: list[pd.DataFrame] = []
    for dimension in ("asset_class_refined", "management_style", "primary_strategy"):
        for label, rows in meta.groupby(dimension):
            symbols = [symbol for symbol in rows.index if symbol in normalized.columns]
            if len(symbols) < 5:
                continue
            values = normalized[symbols].mean(axis=1, skipna=True)
            group_curves.append(
                pd.DataFrame(
                    {
                        "session_date": values.index,
                        "dimension": dimension,
                        "group": str(label),
                        "mean_wealth": values.values,
                        "available_members": normalized[symbols].notna().sum(axis=1).values,
                        "group_size": len(symbols),
                    }
                )
            )
    group_curve = pd.concat(group_curves, ignore_index=True)

    curve_metrics: dict[str, Any] = {}
    indexed = curve.set_index("session_date")
    for column in ("spy", "etf_mean_all_available", "etf_median_all_available", "etf_mean_fixed_complete"):
        curve_metrics[column] = performance_metrics(indexed[column].dropna())
    diagnostics = {
        "requested_constituents": int(len(selected)),
        "loaded_at_cutoff": int(len(series_by_symbol)),
        "missing_or_empty": missing,
        "first_observation_more_than_7_days_after_cutoff": late_at_cutoff,
        "fixed_complete_constituents": int(len(complete_symbols)),
        "common_start": curve["session_date"].min().date().isoformat(),
        "common_end": curve["session_date"].max().date().isoformat(),
        "curve_metrics": curve_metrics,
        "interpretation": (
            "Cross-sectional mean/median of buy-and-hold wealth rebased to 100 at the cutoff; "
            "not a daily-rebalanced tradable portfolio. Fixed-complete is the attrition sensitivity."
        ),
    }
    return curve, group_curve, diagnostics


def selection_funnel(benchmark: pd.DataFrame, qualifying: pd.DataFrame, selected: pd.DataFrame, universe_manifest: dict[str, Any], market_summary: dict[str, Any]) -> pd.DataFrame:
    after_aliases = int(qualifying["analysis_primary"].sum())
    return pd.DataFrame(
        [
            {"stage": "catalogue_identities", "count": int(universe_manifest.get("records", 0)), "unit": "identities"},
            {"stage": "economically_eligible_identities", "count": int(universe_manifest.get("eligibility", {}).get("eligible", 0)), "unit": "identities"},
            {"stage": "eligible_unique_symbols", "count": int(market_summary.get("universe_symbol_count", 0)), "unit": "symbols"},
            {"stage": "valid_yahoo_parquets", "count": int(market_summary.get("parquet_files_validated", 0)), "unit": "symbols"},
            {"stage": "comparable_with_spy", "count": int(market_summary.get("analyzed_symbol_count", len(benchmark))), "unit": "symbols"},
            {"stage": "qualifying_price_series_2022_03_01", "count": int(len(qualifying)), "unit": "symbols"},
            {"stage": "economic_products_after_alias_consolidation", "count": after_aliases, "unit": "products"},
            {"stage": "etf_portfolios_after_product_type_review", "count": int(len(selected)), "unit": "products"},
        ]
    )


def top_tables(selected: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ranking = selected.copy()
    ranking["joint_excess_score"] = (
        ranking["excess_cagr"].rank(pct=True) + ranking["excess_martin"].rank(pct=True)
    ) / 2.0
    columns = [
        "request_symbol",
        "name",
        "start_date",
        "asset_class_refined",
        "management_style",
        "primary_strategy",
        "sector_theme",
        "cagr",
        "spy_cagr",
        "excess_cagr",
        "sortino",
        "spy_sortino",
        "excess_sortino",
        "calmar",
        "spy_calmar",
        "excess_calmar",
        "martin",
        "spy_martin",
        "excess_martin",
        "direction",
        "spy_direction",
        "breadth",
        "spy_breadth",
        "dbf_signed",
        "spy_dbf_signed",
        "excess_dbf_signed",
        "dbf",
        "spy_dbf",
        "beat_spy_dbf_signed",
        "relative_cash_return",
        "relative_cash_cagr",
        "relative_cash_ulcer_index",
        "rwm_score",
        "spy_relative_cash_return",
        "spy_relative_cash_cagr",
        "spy_relative_cash_ulcer_index",
        "spy_rwm_score",
        "beat_spy_rwm_score",
        "excess_rwm_score",
        "beat_spy_cagr_and_rwm",
        "beat_spy_cagr_and_martin",
        "beat_spy_all_four",
        "joint_excess_score",
    ]
    both = ranking[ranking["beat_spy_cagr_and_martin"]].sort_values(
        ["joint_excess_score", "excess_cagr"], ascending=False
    )
    four = ranking[ranking["beat_spy_all_four"]].sort_values(
        ["joint_excess_score", "excess_cagr"], ascending=False
    )
    active = ranking[ranking["management_style"] == "active_identified"].sort_values(
        ["beat_spy_cagr_and_martin", "joint_excess_score"], ascending=False
    )
    alternatives = ranking[
        ranking["primary_strategy"].isin(
            ["long_short_market_neutral", "managed_futures", "merger_arbitrage", "absolute_return"]
        )
    ].sort_values(["beat_spy_cagr_and_martin", "joint_excess_score"], ascending=False)
    ranking["dbf_joint_score"] = (
        ranking["excess_cagr"].rank(pct=True) + ranking["excess_dbf_signed"].rank(pct=True)
    ) / 2.0
    dbf = ranking[ranking["beat_spy_cagr"] & ranking["beat_spy_dbf_signed"]].sort_values(
        ["dbf_joint_score", "excess_cagr"], ascending=False
    )
    rwm = ranking[np.isfinite(ranking["rwm_score"])].sort_values(
        ["rwm_score", "relative_cash_cagr"], ascending=False
    )
    return {
        "winners_cagr_and_martin": both[columns],
        "winners_all_four": four[columns],
        "active_identified": active[columns],
        "alternative_strategies": alternatives[columns],
        "dbf_leaders": dbf[columns],
        "rwm_leaders": rwm[columns],
    }


def run(
    benchmark_path: Path,
    market_root: Path,
    output_root: Path,
    universe_manifest_path: Path,
    market_summary_path: Path,
    cash_path: Path,
    management_audit_path: Path,
    cutoff: str = DEFAULT_CUTOFF,
) -> dict[str, Any]:
    benchmark = pd.read_parquet(benchmark_path)
    qualifying = mark_economic_aliases(select_cohort(benchmark, cutoff))
    qualifying = apply_management_style_audit(qualifying, management_audit_path)
    qualifying = enrich_comparable_metrics(qualifying, market_root, cash_path)
    selected = qualifying[
        qualifying["analysis_primary"]
        & qualifying["management_style"].ne("not_applicable_security")
    ].copy().reset_index(drop=True)
    group_summaries = build_group_summaries(selected)
    curve, group_curve, curve_diagnostics = build_common_period_curves(selected, market_root, cutoff)
    universe_manifest = json.loads(universe_manifest_path.read_text(encoding="utf-8"))
    market_summary = json.loads(market_summary_path.read_text(encoding="utf-8"))
    cash_rates = load_cash_rates(cash_path)
    funnel = selection_funnel(benchmark, qualifying, selected, universe_manifest, market_summary)
    tops = top_tables(selected)

    output_root.mkdir(parents=True, exist_ok=True)
    write_frame(qualifying, output_root / "qualifying_series_with_aliases.parquet")
    write_frame(qualifying, output_root / "qualifying_series_with_aliases.csv")
    write_frame(selected, output_root / "selected_etfs.parquet")
    write_frame(selected, output_root / "selected_etfs.csv")
    write_frame(group_summaries, output_root / "group_summaries.parquet")
    write_frame(group_summaries, output_root / "group_summaries.csv")
    write_frame(curve, output_root / "common_period_curves.parquet")
    write_frame(group_curve, output_root / "group_curves.parquet")
    write_frame(funnel, output_root / "selection_funnel.csv")
    for name, frame in tops.items():
        write_frame(frame, output_root / f"{name}.csv")
    both = int(selected["beat_spy_cagr_and_martin"].sum())
    all_four = int(selected["beat_spy_all_four"].sum())
    cagr_rwm = int(selected["beat_spy_cagr_and_rwm"].sum())
    summary = {
        "study_version": STUDY_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "management_evidence_version": MANAGEMENT_EVIDENCE_VERSION,
        "generated_at": utc_now(),
        "cutoff": cutoff,
        "minimum_daily_returns": MIN_RETURN_OBSERVATIONS,
        "qualifying_series_count": int(len(qualifying)),
        "alias_series_consolidated": int((~qualifying["analysis_primary"]).sum()),
        "economic_products_after_alias_consolidation": int(qualifying["analysis_primary"].sum()),
        "non_etf_securities_excluded_after_review": int(
            (
                qualifying["analysis_primary"]
                & qualifying["management_style"].eq("not_applicable_security")
            ).sum()
        ),
        "cohort_count": int(len(selected)),
        "current_listing_count": int(selected["current_listing"].sum()),
        "historical_identity_count": int((~selected["current_listing"]).sum()),
        "beat_spy": {
            metric: {
                "count": int(selected[f"beat_spy_{metric}"].sum()),
                "rate": float(selected[f"beat_spy_{metric}"].mean()),
            }
            for metric in METRICS
        },
        "beat_spy_cagr_and_martin": {"count": both, "rate": both / len(selected)},
        "beat_spy_cagr_and_rwm": {"count": cagr_rwm, "rate": cagr_rwm / len(selected)},
        "beat_spy_all_four": {"count": all_four, "rate": all_four / len(selected)},
        "beat_spy_dbf": {
            "count": int(selected["beat_spy_dbf_signed"].sum()),
            "rate": float(selected["beat_spy_dbf_signed"].mean()),
        },
        "rwm": {
            "cash_reference": "FRED DFF Effective Federal Funds Rate",
            "cash_day_count_basis": "Actual/360",
            "cash_first_date": cash_rates.index.min().date().isoformat(),
            "cash_last_date": cash_rates.index.max().date().isoformat(),
            "finite_score_count": int(np.isfinite(selected["rwm_score"]).sum()),
            "beat_spy_count": int(selected["beat_spy_rwm_score"].sum()),
            "beat_spy_rate": float(selected["beat_spy_rwm_score"].mean()),
        },
        "management_style_counts": selected["management_style"].value_counts().to_dict(),
        "asset_class_counts": selected["asset_class_refined"].value_counts().to_dict(),
        "curve_diagnostics": curve_diagnostics,
        "methodology": {
            "performance_window": "Each ETF inception/first usable Yahoo session to its own last usable session",
            "benchmark_alignment": "SPY on exact common sessions for each ETF",
            "common_curve_window": f"{cutoff} to latest Yahoo session",
            "return_series": "Yahoo Adj Close total-return proxy",
            "risk_free_rate": 0.0,
            "descriptive_metrics": ["CAGR", "Sortino", "Calmar", "Martin", "RWM"],
            "decision_metric": "Relative-Wealth Martin (RWM), with CAGR retained as economic context",
            "supplementary_descriptor": "Signed Direction–Breadth Factor (DBF±) on daily log returns",
            "rwm_definition": "CAGR(W_fund/W_cash) divided by Ulcer Index(W_fund/W_cash)",
            "rwm_cash_reference": "FRED DFF compounded on calendar days with Actual/360 and sampled on fund sessions",
            "cost_model": "QINVIA Historical Adaptive Cost and Slippage Model v1.0",
            "cost_treatment": "Buy & Hold comparison; no fictitious switching cost under section 7",
        },
        "limitations": [
            "Management-style evidence is point-in-time and mandate changes require segmented analysis.",
            "The 67 non-current identities all retain prices into July/August 2026 and are not a representative sample of long-dead products; survivorship bias remains material.",
            "SPY is an intentional hurdle, not the economically correct benchmark for every asset class.",
            "Adj Close is a total-return proxy and may not fully reconstruct every distribution or corporate action.",
            "DBF is order-invariant and scale-invariant; it describes signed direction and breadth, not drawdown risk, economic severity, alpha or future performance.",
            "RWM fixes cash as its reference. Substituting a risky benchmark would require a separate beta-neutral residual procedure.",
            "RWM is undefined when relative-wealth Ulcer Index is zero; no artificial denominator floor is imposed.",
            "FRED DFF is an idealised institutional cash accrual benchmark, not a guaranteed retail investable return after fees or taxes.",
        ],
    }
    (output_root / "study_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=Path("data/processed/market/benchmark_vs_spy.parquet"))
    parser.add_argument("--market-root", type=Path, default=Path(".local-wsl/market"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/studies/etf_universe_1A"))
    parser.add_argument("--universe-manifest", type=Path, default=Path("data/processed/universe/run_manifest.json"))
    parser.add_argument("--market-summary", type=Path, default=Path("data/processed/market/benchmark_summary.json"))
    parser.add_argument(
        "--cash",
        type=Path,
        default=Path("data/external/macro/fred_dff_daily.csv"),
    )
    parser.add_argument(
        "--management-audit",
        type=Path,
        default=Path("data/processed/studies/etf_universe_1A/management_style_audit.csv"),
    )
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run(
        args.benchmark,
        args.market_root,
        args.output_root,
        args.universe_manifest,
        args.market_summary,
        args.cash,
        args.management_audit,
        args.cutoff,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
