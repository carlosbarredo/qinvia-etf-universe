"""Return-matched leverage analysis for intentionally managed ETF products.

The primary simulation uses a fixed margin loan established at inception.  It
therefore preserves the buy-and-hold nature of the study: the initial leverage
is stated, but it is allowed to drift with the value of the ETF.  Financing is
accrued on an Actual/360 basis from the daily effective Fed Funds rate plus an
explicit broker spread.
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
from qinvia_etfs.rwm import cash_wealth, relative_wealth_martin
from qinvia_etfs.universe_study import load_full_adjusted_series, raw_price_path, write_frame


LEVERAGE_LEVELS = (1.0, 1.25, 1.5, 1.75, 2.0)
BASE_FINANCING_SPREAD = 0.015
FINANCING_SPREAD_SCENARIOS = (0.01, 0.015, 0.02, 0.025)
DAY_COUNT_BASIS = 360.0
ILLUSTRATIVE_MAINTENANCE_RATIO = 0.25
DYNAMIC_STRATEGIES = {
    "long_short_market_neutral",
    "managed_futures",
    "merger_arbitrage",
    "absolute_return",
    "risk_managed_alternative",
}
PRIMARY_METRICS = ("cagr", "sortino", "calmar", "martin")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_financing_benchmark(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    date_column = "observation_date" if "observation_date" in frame else "DATE"
    if "DFF" not in frame:
        raise ValueError("Fed Funds CSV must contain a DFF column")
    frame[date_column] = pd.to_datetime(frame[date_column])
    values = pd.to_numeric(frame["DFF"], errors="coerce") / 100.0
    return pd.Series(values.to_numpy(), index=frame[date_column], name="fed_funds").sort_index()


def classify_evidence_bucket(row: pd.Series) -> str:
    """Separate manager intent from static or concentrated beta exposure."""

    if row["management_style"] == "mixed_or_changed_mandate":
        return "mixed_mandate_not_attributed"
    if row["management_style"] == "not_applicable_security":
        return "non_fund_security"
    if row["management_style"] == "active_identified":
        return "intentional_management"
    if row["primary_strategy"] in DYNAMIC_STRATEGIES:
        return "intentional_management"
    if row["management_style"] == "systematic_or_rules_based":
        return "systematic_static_beta"
    if row["management_style"] == "non_index_management_identified":
        # SEC N-CEN establishes that the fund is not an index fund, but that
        # fact alone does not prove a discretionary or dynamic process.
        return "non_index_management"
    if row["management_style"] == "static_exposure_or_trust":
        return "static_exposure"
    if row["asset_class_refined"] == "equity" and row["exposure_type"] == "broad_equity":
        return "broad_market_beta"
    if row["asset_class_refined"] == "equity" and row["exposure_type"] in {
        "sector_or_industry",
        "thematic_equity",
        "factor_style_or_income",
    }:
        return "concentrated_equity_beta"
    if row["asset_class_refined"] in {"commodity", "crypto", "currency", "real_estate"}:
        return "other_asset_beta"
    if row["asset_class_refined"] == "fixed_income":
        return "fixed_income_beta"
    return "other_or_unresolved"


def financing_path(
    dates: pd.DatetimeIndex,
    benchmark: pd.Series,
    spread: float = BASE_FINANCING_SPREAD,
) -> pd.DataFrame:
    """Build daily-accrued financing factors on the ETF observation calendar."""

    if len(dates) < 2:
        raise ValueError("At least two dates are required")
    calendar = pd.date_range(dates.min(), dates.max(), freq="D")
    fed = benchmark.reindex(calendar).ffill().bfill().clip(lower=0.0)
    annual_rate = fed + spread
    daily_factor = 1.0 + annual_rate / DAY_COUNT_BASIS
    debt_index = daily_factor.cumprod()
    # The loan exists at the first close, so interest starts after that date.
    debt_index = debt_index / float(debt_index.iloc[0])
    aligned = pd.DataFrame(index=dates)
    aligned["benchmark_rate"] = fed.reindex(dates).to_numpy()
    aligned["financing_rate"] = annual_rate.reindex(dates).to_numpy()
    aligned["debt_index"] = debt_index.reindex(dates).to_numpy()
    return aligned


def fixed_debt_equity(
    fund_wealth: pd.Series,
    financing: pd.DataFrame,
    initial_leverage: float,
) -> tuple[pd.Series, dict[str, Any]]:
    """Simulate an initial margin loan without subsequent rebalancing."""

    if initial_leverage < 1.0:
        raise ValueError("initial_leverage must be at least 1")
    wealth = pd.to_numeric(fund_wealth, errors="coerce").dropna()
    wealth = wealth / float(wealth.iloc[0])
    debt = (initial_leverage - 1.0) * financing.loc[wealth.index, "debt_index"]
    market_value = initial_leverage * wealth
    equity = market_value - debt
    margin_ratio = equity / market_value
    first_non_positive = equity.index[equity <= 0]
    diagnostics = {
        "ruined": bool(len(first_non_positive)),
        "first_non_positive_date": (
            first_non_positive[0].date().isoformat() if len(first_non_positive) else ""
        ),
        "minimum_equity": float(equity.min()),
        "minimum_margin_ratio": float(margin_ratio.min()),
        "illustrative_25pct_maintenance_breach": bool(
            (margin_ratio < ILLUSTRATIVE_MAINTENANCE_RATIO).any()
        ),
        "terminal_debt_index": float(financing.loc[wealth.index[-1], "debt_index"]),
    }
    return equity, diagnostics


def _metric_payload(equity: pd.Series, cash_curve: pd.Series) -> dict[str, float]:
    if (equity <= 0).any():
        return {
            key: math.nan
            for key in (
                *PRIMARY_METRICS,
                "direction",
                "breadth",
                "dbf_signed",
                "dbf",
                "relative_cash_return",
                "relative_cash_cagr",
                "relative_cash_ulcer_index",
                "rwm_score",
            )
        }
    metrics = performance_metrics(equity)
    dbf = dbf_metrics(equity)
    rwm = relative_wealth_martin(equity, cash_curve)
    return {key: float(metrics[key]) for key in PRIMARY_METRICS} | {
        key: float(value) for key, value in dbf.items()
    } | {key: float(value) for key, value in rwm.items()}


def required_leverage_for_terminal_match(
    etf_terminal_wealth: float,
    spy_terminal_wealth: float,
    debt_terminal_index: float,
) -> float:
    """Solve fixed initial leverage that matches SPY terminal wealth after financing."""

    denominator = etf_terminal_wealth - debt_terminal_index
    if denominator <= 0:
        return math.inf
    return float((spy_terminal_wealth - debt_terminal_index) / denominator)


def _aligned_prices(row: pd.Series, market_root: Path, spy: pd.Series) -> pd.DataFrame:
    etf = load_full_adjusted_series(raw_price_path(market_root, str(row["request_symbol"])))
    etf = etf.loc[pd.Timestamp(row["start_date"]) : pd.Timestamp(row["end_date"])]
    joined = pd.concat({"etf": etf, "spy": spy}, axis=1, join="inner").dropna()
    return joined[(joined.etf > 0) & (joined.spy > 0)]


def evidence_summary(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bucket, group in selected.groupby("evidence_bucket"):
        rows.append(
            {
                "evidence_bucket": bucket,
                "n": int(len(group)),
                "beat_spy_cagr": int(group.beat_spy_cagr.sum()),
                "beat_spy_martin": int(group.beat_spy_martin.sum()),
                "beat_spy_rwm_score": int(group.beat_spy_rwm_score.sum()),
                "beat_spy_cagr_and_rwm": int(
                    (group.beat_spy_cagr & group.beat_spy_rwm_score).sum()
                ),
                "beat_spy_cagr_and_martin": int(group.beat_spy_cagr_and_martin.sum()),
                "beat_spy_all_four": int(group.beat_spy_all_four.sum()),
                "rate_all_four": float(group.beat_spy_all_four.mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def rolling_robustness(
    managed_winners: pd.DataFrame,
    market_root: Path,
    spy: pd.Series,
    cash_rates: pd.Series,
    window_observations: int = 756,
    step_observations: int = 21,
) -> pd.DataFrame:
    """Test whether inception winners also win across rolling three-year windows."""

    rows: list[dict[str, Any]] = []
    for _, row in managed_winners.iterrows():
        joined = _aligned_prices(row, market_root, spy)
        outcomes: list[dict[str, float | bool]] = []
        for start in range(0, len(joined) - window_observations + 1, step_observations):
            sample = joined.iloc[start : start + window_observations]
            etf_metrics = performance_metrics(sample.etf)
            spy_metrics = performance_metrics(sample.spy)
            sample_cash = cash_wealth(sample.index, cash_rates)
            etf_rwm = relative_wealth_martin(sample.etf, sample_cash)["rwm_score"]
            spy_rwm = relative_wealth_martin(sample.spy, sample_cash)["rwm_score"]
            excess_cagr = float(etf_metrics["cagr"] - spy_metrics["cagr"])
            excess_martin = float(etf_metrics["martin"] - spy_metrics["martin"])
            excess_rwm = float(etf_rwm - spy_rwm)
            outcomes.append(
                {
                    "excess_cagr": excess_cagr,
                    "excess_martin": excess_martin,
                    "excess_rwm_score": excess_rwm,
                    "beat_cagr": excess_cagr > 0,
                    "beat_martin": excess_martin > 0,
                    "beat_rwm_score": excess_rwm > 0,
                    "beat_cagr_and_rwm": excess_cagr > 0 and excess_rwm > 0,
                    "beat_both": excess_cagr > 0 and excess_martin > 0,
                }
            )
        result = pd.DataFrame(outcomes)
        rows.append(
            {
                "request_symbol": row.request_symbol,
                "name": row["name"],
                "primary_strategy": row.primary_strategy,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "rolling_windows": int(len(result)),
                "rate_beat_cagr": float(result.beat_cagr.mean()) if len(result) else math.nan,
                "rate_beat_martin": float(result.beat_martin.mean()) if len(result) else math.nan,
                "rate_beat_rwm_score": float(result.beat_rwm_score.mean()) if len(result) else math.nan,
                "rate_beat_cagr_and_rwm": float(result.beat_cagr_and_rwm.mean()) if len(result) else math.nan,
                "rate_beat_both": float(result.beat_both.mean()) if len(result) else math.nan,
                "median_excess_cagr": float(result.excess_cagr.median()) if len(result) else math.nan,
                "median_excess_martin": float(result.excess_martin.median()) if len(result) else math.nan,
                "minimum_excess_cagr": float(result.excess_cagr.min()) if len(result) else math.nan,
                "minimum_excess_martin": float(result.excess_martin.min()) if len(result) else math.nan,
                "minimum_excess_rwm_score": float(result.excess_rwm_score.min()) if len(result) else math.nan,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values("rate_beat_rwm_score", ascending=False)
        .reset_index(drop=True)
    )


def run(
    selected_path: Path,
    market_root: Path,
    financing_path_csv: Path,
    output_root: Path,
    spread: float = BASE_FINANCING_SPREAD,
) -> dict[str, Any]:
    selected = pd.read_parquet(selected_path).copy()
    selected["evidence_bucket"] = selected.apply(classify_evidence_bucket, axis=1)
    selected["intentional_management"] = selected.evidence_bucket.eq("intentional_management")
    managed = selected[selected.intentional_management].copy()
    candidates = managed[(~managed.beat_spy_cagr) & managed.beat_spy_rwm_score].copy()
    benchmark = load_financing_benchmark(financing_path_csv)
    spy = load_full_adjusted_series(raw_price_path(market_root, "SPY"))

    grid_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []
    matched_curve_rows: list[pd.DataFrame] = []
    sensitivity_rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        joined = _aligned_prices(row, market_root, spy)
        etf_wealth = joined.etf / float(joined.etf.iloc[0])
        spy_wealth = joined.spy / float(joined.spy.iloc[0])
        cash_curve = cash_wealth(joined.index, benchmark)
        financing = financing_path(joined.index, benchmark, spread)
        spy_metrics = performance_metrics(spy_wealth)
        spy_rwm = relative_wealth_martin(spy_wealth, cash_curve)
        for leverage in LEVERAGE_LEVELS:
            equity, diagnostics = fixed_debt_equity(etf_wealth, financing, leverage)
            values = _metric_payload(equity, cash_curve)
            record: dict[str, Any] = {
                "request_symbol": row.request_symbol,
                "name": row["name"],
                "asset_class_refined": row.asset_class_refined,
                "primary_strategy": row.primary_strategy,
                "management_style": row.management_style,
                "start_date": joined.index[0].date().isoformat(),
                "end_date": joined.index[-1].date().isoformat(),
                "initial_leverage": leverage,
                "terminal_wealth": float(equity.iloc[-1]),
                "spy_terminal_wealth": float(spy_wealth.iloc[-1]),
                **diagnostics,
                **values,
            }
            for metric in PRIMARY_METRICS:
                record[f"spy_{metric}"] = float(spy_metrics[metric])
                record[f"beat_spy_{metric}"] = bool(
                    math.isfinite(record[metric]) and record[metric] > record[f"spy_{metric}"]
                )
            record["beat_spy_cagr_and_martin"] = bool(
                record["beat_spy_cagr"] and record["beat_spy_martin"]
            )
            record["spy_rwm_score"] = float(spy_rwm["rwm_score"])
            record["beat_spy_rwm_score"] = bool(
                math.isfinite(record["rwm_score"])
                and record["rwm_score"] > record["spy_rwm_score"]
            )
            record["beat_spy_cagr_and_rwm"] = bool(
                record["beat_spy_cagr"] and record["beat_spy_rwm_score"]
            )
            record["beat_spy_all_four"] = bool(
                all(record[f"beat_spy_{metric}"] for metric in PRIMARY_METRICS)
            )
            grid_rows.append(record)

        debt_terminal = float(financing.debt_index.iloc[-1])
        required = required_leverage_for_terminal_match(
            float(etf_wealth.iloc[-1]), float(spy_wealth.iloc[-1]), debt_terminal
        )
        matched: dict[str, Any] = {
            "request_symbol": row.request_symbol,
            "name": row["name"],
            "asset_class_refined": row.asset_class_refined,
            "primary_strategy": row.primary_strategy,
            "management_style": row.management_style,
            "start_date": joined.index[0].date().isoformat(),
            "end_date": joined.index[-1].date().isoformat(),
            "unlevered_cagr": float(row.cagr),
            "unlevered_spy_cagr": float(row.spy_cagr),
            "unlevered_martin": float(row.martin),
            "unlevered_spy_martin": float(row.spy_martin),
            "unlevered_rwm_score": float(row.rwm_score),
            "unlevered_spy_rwm_score": float(row.spy_rwm_score),
            "required_initial_leverage": required,
            "feasible_at_or_below_2x": bool(math.isfinite(required) and 1.0 <= required <= 2.0),
        }
        if math.isfinite(required) and required >= 1.0:
            equity, diagnostics = fixed_debt_equity(etf_wealth, financing, required)
            values = _metric_payload(equity, cash_curve)
            matched.update(diagnostics)
            matched.update({f"matched_{key}": value for key, value in values.items()})
            matched["matched_terminal_wealth"] = float(equity.iloc[-1])
            matched["spy_terminal_wealth"] = float(spy_wealth.iloc[-1])
            matched["matched_martin_beats_spy"] = bool(
                math.isfinite(values["martin"]) and values["martin"] > spy_metrics["martin"]
            )
            matched["matched_rwm_beats_spy"] = bool(
                math.isfinite(values["rwm_score"])
                and values["rwm_score"] > spy_rwm["rwm_score"]
            )
            matched["spy_rwm_score"] = float(spy_rwm["rwm_score"])
            matched["matched_all_three_risk_beat_spy"] = bool(
                all(
                    math.isfinite(values[metric]) and values[metric] > spy_metrics[metric]
                    for metric in ("sortino", "calmar", "martin")
                )
            )
            for metric in ("sortino", "calmar", "martin"):
                matched[f"spy_{metric}"] = float(spy_metrics[metric])
            if matched["feasible_at_or_below_2x"]:
                matched_curve_rows.append(
                    pd.DataFrame(
                        {
                            "session_date": joined.index,
                            "request_symbol": str(row.request_symbol),
                            "required_initial_leverage": required,
                            "etf_unlevered": etf_wealth.to_numpy() * 100.0,
                            "etf_return_matched": equity.to_numpy() * 100.0,
                            "spy": spy_wealth.to_numpy() * 100.0,
                        }
                    )
                )
        matched_rows.append(matched)

        for scenario_spread in FINANCING_SPREAD_SCENARIOS:
            scenario_financing = financing_path(joined.index, benchmark, scenario_spread)
            scenario_required = required_leverage_for_terminal_match(
                float(etf_wealth.iloc[-1]),
                float(spy_wealth.iloc[-1]),
                float(scenario_financing.debt_index.iloc[-1]),
            )
            scenario: dict[str, Any] = {
                "request_symbol": row.request_symbol,
                "name": row["name"],
                "financing_spread": scenario_spread,
                "required_initial_leverage": scenario_required,
                "feasible_at_or_below_2x": bool(
                    math.isfinite(scenario_required) and 1.0 <= scenario_required <= 2.0
                ),
                "matched_martin_beats_spy": False,
                "matched_rwm_beats_spy": False,
                "matched_all_three_risk_beat_spy": False,
                "illustrative_25pct_maintenance_breach": False,
            }
            if math.isfinite(scenario_required) and scenario_required >= 1.0:
                scenario_equity, scenario_diagnostics = fixed_debt_equity(
                    etf_wealth, scenario_financing, scenario_required
                )
                scenario_values = _metric_payload(scenario_equity, cash_curve)
                scenario["matched_martin_beats_spy"] = bool(
                    math.isfinite(scenario_values["martin"])
                    and scenario_values["martin"] > spy_metrics["martin"]
                )
                scenario["matched_rwm_beats_spy"] = bool(
                    math.isfinite(scenario_values["rwm_score"])
                    and scenario_values["rwm_score"] > spy_rwm["rwm_score"]
                )
                scenario["matched_all_three_risk_beat_spy"] = bool(
                    all(
                        math.isfinite(scenario_values[metric])
                        and scenario_values[metric] > spy_metrics[metric]
                        for metric in ("sortino", "calmar", "martin")
                    )
                )
                scenario["illustrative_25pct_maintenance_breach"] = scenario_diagnostics[
                    "illustrative_25pct_maintenance_breach"
                ]
            scenario["feasible_and_martin_better"] = bool(
                scenario["feasible_at_or_below_2x"] and scenario["matched_martin_beats_spy"]
            )
            scenario["feasible_and_rwm_better"] = bool(
                scenario["feasible_at_or_below_2x"] and scenario["matched_rwm_beats_spy"]
            )
            scenario["feasible_and_all_three_risk_better"] = bool(
                scenario["feasible_at_or_below_2x"]
                and scenario["matched_all_three_risk_beat_spy"]
            )
            sensitivity_rows.append(scenario)

    grid = pd.DataFrame(grid_rows)
    matched = pd.DataFrame(matched_rows)
    matched_curves = (
        pd.concat(matched_curve_rows, ignore_index=True)
        if matched_curve_rows
        else pd.DataFrame(
            columns=[
                "session_date",
                "request_symbol",
                "required_initial_leverage",
                "etf_unlevered",
                "etf_return_matched",
                "spy",
            ]
        )
    )
    sensitivity = pd.DataFrame(sensitivity_rows)
    grid_summary = (
        grid.groupby("initial_leverage")
        .agg(
            candidates=("request_symbol", "nunique"),
            beat_cagr=("beat_spy_cagr", "sum"),
            beat_martin=("beat_spy_martin", "sum"),
            beat_rwm_score=("beat_spy_rwm_score", "sum"),
            beat_cagr_and_rwm=("beat_spy_cagr_and_rwm", "sum"),
            beat_cagr_and_martin=("beat_spy_cagr_and_martin", "sum"),
            beat_all_four=("beat_spy_all_four", "sum"),
            maintenance_breaches=("illustrative_25pct_maintenance_breach", "sum"),
            ruined=("ruined", "sum"),
        )
        .reset_index()
    )
    evidence = evidence_summary(selected)
    sensitivity_summary = (
        sensitivity.groupby("financing_spread")
        .agg(
            candidates=("request_symbol", "nunique"),
            feasible_at_or_below_2x=("feasible_at_or_below_2x", "sum"),
            matched_martin_better=("feasible_and_martin_better", "sum"),
            matched_rwm_better=("feasible_and_rwm_better", "sum"),
            matched_all_three_risk_better=("feasible_and_all_three_risk_better", "sum"),
            maintenance_breaches=("illustrative_25pct_maintenance_breach", "sum"),
        )
        .reset_index()
    )
    managed_winners = managed[managed.beat_spy_rwm_score].copy()
    rolling = rolling_robustness(managed_winners, market_root, spy, benchmark)

    output_root.mkdir(parents=True, exist_ok=True)
    write_frame(selected, output_root / "selected_with_evidence_buckets.parquet")
    write_frame(evidence, output_root / "evidence_bucket_summary.csv")
    write_frame(managed, output_root / "intentional_management_products.csv")
    write_frame(candidates, output_root / "risk_efficient_candidates.csv")
    write_frame(grid, output_root / "leverage_grid.csv")
    write_frame(grid_summary, output_root / "leverage_grid_summary.csv")
    write_frame(matched, output_root / "return_matched_leverage.csv")
    write_frame(matched_curves, output_root / "return_matched_equity_curves.parquet")
    write_frame(sensitivity, output_root / "financing_sensitivity.csv")
    write_frame(sensitivity_summary, output_root / "financing_sensitivity_summary.csv")
    write_frame(rolling, output_root / "managed_winner_rolling_robustness.csv")
    feasible = matched[matched.feasible_at_or_below_2x]
    summary = {
        "generated_at": utc_now(),
        "method": "Fixed margin loan at inception; no leverage rebalancing",
        "financing_benchmark": "FRED DFF daily effective Fed Funds rate",
        "financing_spread": spread,
        "day_count_basis": int(DAY_COUNT_BASIS),
        "maintenance_ratio_is_illustrative": ILLUSTRATIVE_MAINTENANCE_RATIO,
        "universe_count": int(len(selected)),
        "intentional_management_count": int(len(managed)),
        "intentional_beat_cagr_and_martin": int(managed.beat_spy_cagr_and_martin.sum()),
        "intentional_beat_rwm": int(managed.beat_spy_rwm_score.sum()),
        "intentional_beat_cagr_and_rwm": int(
            (managed.beat_spy_cagr & managed.beat_spy_rwm_score).sum()
        ),
        "intentional_beat_all_four": int(managed.beat_spy_all_four.sum()),
        "risk_efficient_candidate_count": int(len(candidates)),
        "return_match_feasible_at_or_below_2x": int(len(feasible)),
        "return_match_feasible_and_martin_better": int(
            feasible.get("matched_martin_beats_spy", pd.Series(dtype=bool)).fillna(False).sum()
        ),
        "return_match_feasible_and_rwm_better": int(
            feasible.get("matched_rwm_beats_spy", pd.Series(dtype=bool)).fillna(False).sum()
        ),
        "return_match_feasible_and_all_three_risk_better": int(
            feasible.get("matched_all_three_risk_beat_spy", pd.Series(dtype=bool)).fillna(False).sum()
        ),
        "managed_winners_robust_in_majority_rolling_windows": int(
            (rolling.rate_beat_rwm_score >= 0.5).sum()
        ),
        "limitations": [
            "The spread is an IBKR-style scenario, not a complete archive of historical IBKR pricing.",
            "The 25% maintenance threshold is illustrative; house and product requirements vary.",
            "Return-matched leverage is solved ex post and is diagnostic, not an investable rule.",
            "Fixed initial debt avoids fictitious rebalancing but lets leverage drift through time.",
        ],
    }
    (output_root / "leverage_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selected",
        type=Path,
        default=Path("data/processed/studies/etf_universe_1A/selected_etfs.parquet"),
    )
    parser.add_argument(
        "--market-root", type=Path, default=Path(".local-wsl/market")
    )
    parser.add_argument(
        "--financing",
        type=Path,
        default=Path("data/external/macro/fred_dff_daily.csv"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/processed/studies/etf_universe_1A"),
    )
    parser.add_argument("--spread", type=float, default=BASE_FINANCING_SPREAD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run(args.selected, args.market_root, args.financing, args.output_root, args.spread)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
