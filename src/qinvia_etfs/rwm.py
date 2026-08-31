"""Relative-Wealth Martin (RWM) with USD cash fixed as the reference.

The score is the Martin ratio calculated entirely on fund-to-cash relative
wealth.  Cash is accrued from the daily Effective Federal Funds Rate (DFF).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


DAY_COUNT_BASIS = 360.0
ZERO_UI_TOLERANCE = 1e-15


def load_cash_rates(path: Path) -> pd.Series:
    """Load a validated FRED DFF history as decimal annual rates."""

    frame = pd.read_csv(path)
    date_column = "observation_date" if "observation_date" in frame else "DATE"
    if date_column not in frame or "DFF" not in frame:
        raise ValueError("cash-rate CSV must contain a date column and DFF")
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    rates = pd.to_numeric(frame["DFF"], errors="coerce") / 100.0
    if dates.isna().any() or rates.isna().any():
        raise ValueError("cash-rate CSV contains invalid dates or rates")
    result = pd.Series(rates.to_numpy(), index=pd.DatetimeIndex(dates), name="dff")
    result = result.sort_index()
    if result.index.has_duplicates:
        raise ValueError("cash-rate CSV contains duplicate dates")
    return result


def cash_wealth(
    dates: pd.DatetimeIndex,
    annual_rates: pd.Series,
    *,
    day_count_basis: float = DAY_COUNT_BASIS,
) -> pd.Series:
    """Accrue idealised cash on calendar days and sample it on fund sessions."""

    sessions = pd.DatetimeIndex(dates)
    if len(sessions) < 2 or not sessions.is_monotonic_increasing or sessions.has_duplicates:
        raise ValueError("dates must contain at least two unique increasing sessions")
    if day_count_basis <= 0:
        raise ValueError("day_count_basis must be positive")
    calendar = pd.date_range(sessions[0], sessions[-1], freq="D")
    rates = pd.to_numeric(annual_rates, errors="coerce").reindex(calendar).ffill().bfill()
    if rates.isna().any():
        raise ValueError("cash-rate history does not cover the requested dates")
    daily_factor = 1.0 + rates / day_count_basis
    if (daily_factor <= 0).any():
        raise ValueError("cash accrual produced a non-positive daily factor")
    accrued = daily_factor.cumprod()
    accrued = accrued / float(accrued.iloc[0])
    return pd.Series(accrued.reindex(sessions).to_numpy(), index=sessions, name="cash_wealth")


def relative_wealth_martin(
    fund_wealth: pd.Series,
    cash_curve: pd.Series,
) -> dict[str, float]:
    """Calculate RWM entirely on the fund-to-cash wealth ratio."""

    joined = pd.concat(
        {
            "fund": pd.to_numeric(fund_wealth, errors="coerce"),
            "cash": pd.to_numeric(cash_curve, errors="coerce"),
        },
        axis=1,
        join="inner",
    ).dropna()
    joined = joined[(joined.fund > 0) & (joined.cash > 0)]
    if len(joined) < 2:
        raise ValueError("fund and cash must share at least two positive observations")
    days = int((joined.index[-1] - joined.index[0]).days)
    years = days / 365.2425
    if years <= 0:
        raise ValueError("fund and cash must span a positive calendar interval")

    fund = joined.fund / float(joined.fund.iloc[0])
    cash = joined.cash / float(joined.cash.iloc[0])
    relative = fund / cash
    relative_return = float(relative.iloc[-1] - 1.0)
    relative_cagr = float(relative.iloc[-1] ** (1.0 / years) - 1.0)
    drawdown = relative / relative.cummax() - 1.0
    relative_ui = float(np.sqrt(np.mean(np.square(drawdown.to_numpy(dtype=float)))))
    score = (
        relative_cagr / relative_ui
        if relative_ui > ZERO_UI_TOLERANCE
        else math.nan
    )
    return {
        "relative_cash_return": relative_return,
        "relative_cash_cagr": relative_cagr,
        "relative_cash_ulcer_index": relative_ui,
        "rwm_score": float(score),
    }
