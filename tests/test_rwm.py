from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qinvia_etfs.rwm import cash_wealth, relative_wealth_martin


def test_cash_wealth_accrues_every_calendar_day() -> None:
    sessions = pd.DatetimeIndex(["2026-01-02", "2026-01-05"])
    calendar = pd.date_range(sessions[0], sessions[-1], freq="D")
    rates = pd.Series(0.036, index=calendar)
    result = cash_wealth(sessions, rates)
    assert np.isclose(result.iloc[0], 1.0)
    assert np.isclose(result.iloc[1], (1.0 + 0.036 / 360.0) ** 3)


def test_rwm_matches_direct_relative_wealth_calculation() -> None:
    dates = pd.date_range("2020-01-01", periods=5, freq="365D")
    fund = pd.Series([100.0, 120.0, 108.0, 130.0, 150.0], index=dates)
    cash = pd.Series([1.0, 1.02, 1.04, 1.06, 1.08], index=dates)
    result = relative_wealth_martin(fund, cash)
    relative = (fund / fund.iloc[0]) / (cash / cash.iloc[0])
    years = (dates[-1] - dates[0]).days / 365.2425
    expected_cagr = relative.iloc[-1] ** (1.0 / years) - 1.0
    drawdown = relative / relative.cummax() - 1.0
    expected_ui = np.sqrt(np.mean(np.square(drawdown)))
    assert np.isclose(result["relative_cash_cagr"], expected_cagr)
    assert np.isclose(result["relative_cash_ulcer_index"], expected_ui)
    assert np.isclose(result["rwm_score"], expected_cagr / expected_ui)


def test_rwm_is_invariant_to_initial_wealth_scales() -> None:
    dates = pd.date_range("2020-01-01", periods=4, freq="365D")
    fund = pd.Series([1.0, 1.2, 1.1, 1.4], index=dates)
    cash = pd.Series([1.0, 1.02, 1.04, 1.06], index=dates)
    first = relative_wealth_martin(fund, cash)
    second = relative_wealth_martin(fund * 1000.0, cash * 7.0)
    for key in first:
        assert np.isclose(first[key], second[key])


def test_rwm_is_undefined_when_relative_wealth_never_draws_down() -> None:
    dates = pd.date_range("2020-01-01", periods=4, freq="365D")
    fund = pd.Series([1.0, 1.1, 1.2, 1.3], index=dates)
    cash = pd.Series([1.0, 1.0, 1.0, 1.0], index=dates)
    result = relative_wealth_martin(fund, cash)
    assert result["relative_cash_ulcer_index"] == 0.0
    assert math.isnan(result["rwm_score"])


def test_cash_itself_has_zero_relative_return_and_undefined_score() -> None:
    dates = pd.date_range("2020-01-01", periods=4, freq="365D")
    cash = pd.Series([1.0, 1.01, 1.02, 1.03], index=dates)
    result = relative_wealth_martin(cash, cash)
    assert np.isclose(result["relative_cash_return"], 0.0)
    assert np.isclose(result["relative_cash_cagr"], 0.0)
    assert result["relative_cash_ulcer_index"] == 0.0
    assert math.isnan(result["rwm_score"])
