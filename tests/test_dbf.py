from __future__ import annotations

import numpy as np

from qinvia_etfs.dbf import dbf_from_log_returns, dbf_metrics


def test_constant_positive_returns_have_maximum_signed_dbf() -> None:
    result = dbf_from_log_returns(np.full(12, 0.01))
    for value in result.values():
        assert np.isclose(value, 1.0)


def test_constant_negative_returns_preserve_the_sign() -> None:
    result = dbf_from_log_returns(np.full(12, -0.01))
    assert np.isclose(result["direction"], -1.0)
    assert np.isclose(result["breadth"], 1.0)
    assert np.isclose(result["dbf_signed"], -1.0)
    assert np.isclose(result["dbf"], 1.0)


def test_single_jump_has_one_over_n_breadth() -> None:
    returns = np.zeros(10)
    returns[3] = 0.10
    result = dbf_from_log_returns(returns)
    assert np.isclose(result["direction"], 1.0)
    assert np.isclose(result["breadth"], 0.1)
    assert np.isclose(result["dbf_signed"], 0.1)


def test_balanced_moves_cancel_direction_but_retain_breadth() -> None:
    result = dbf_from_log_returns(np.array([0.02, -0.02, 0.02, -0.02]))
    assert np.isclose(result["direction"], 0.0)
    assert np.isclose(result["breadth"], 1.0)
    assert np.isclose(result["dbf_signed"], 0.0)


def test_dbf_is_invariant_to_order() -> None:
    returns = np.array([0.04, -0.02, 0.01, 0.03, -0.005])
    forward = dbf_from_log_returns(returns)
    reversed_result = dbf_from_log_returns(returns[::-1])
    for key in forward:
        assert np.isclose(forward[key], reversed_result[key])


def test_wealth_wrapper_uses_log_returns() -> None:
    returns = np.array([0.01, -0.005, 0.02])
    wealth = np.exp(np.r_[0.0, np.cumsum(returns)])
    expected = dbf_from_log_returns(returns)
    actual = dbf_metrics(wealth)
    for key in expected:
        assert np.isclose(actual[key], expected[key])
