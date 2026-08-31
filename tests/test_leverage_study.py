import math
import unittest

import numpy as np
import pandas as pd

from qinvia_etfs.leverage_study import (
    classify_evidence_bucket,
    financing_path,
    fixed_debt_equity,
    required_leverage_for_terminal_match,
)


class LeverageStudyTests(unittest.TestCase):
    def test_one_x_equals_underlying(self) -> None:
        dates = pd.date_range("2020-01-01", periods=10, freq="B")
        wealth = pd.Series(np.linspace(1.0, 1.2, len(dates)), index=dates)
        benchmark = pd.Series(0.02, index=pd.date_range(dates.min(), dates.max(), freq="D"))
        financing = financing_path(dates, benchmark, spread=0.015)
        equity, diagnostics = fixed_debt_equity(wealth, financing, 1.0)
        np.testing.assert_allclose(equity, wealth)
        self.assertFalse(diagnostics["ruined"])

    def test_terminal_match_solution(self) -> None:
        leverage = required_leverage_for_terminal_match(1.5, 1.8, 1.1)
        terminal = leverage * 1.5 - (leverage - 1.0) * 1.1
        self.assertAlmostEqual(terminal, 1.8)

    def test_unfinanceable_terminal_returns_infinity(self) -> None:
        self.assertTrue(math.isinf(required_leverage_for_terminal_match(1.0, 1.5, 1.1)))

    def test_static_asset_allocation_is_not_intentional_management(self) -> None:
        row = pd.Series(
            {
                "management_style": "index_passive_identified",
                "primary_strategy": "asset_allocation",
                "asset_class_refined": "multi_asset",
                "exposure_type": "multi_asset",
            }
        )
        self.assertEqual(classify_evidence_bucket(row), "other_or_unresolved")


if __name__ == "__main__":
    unittest.main()
