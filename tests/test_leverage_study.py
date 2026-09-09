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

    def test_non_index_filing_does_not_prove_intentional_management(self) -> None:
        row = pd.Series(
            {
                "management_style": "non_index_management_identified",
                "primary_strategy": "other_fixed_income",
                "asset_class_refined": "fixed_income",
                "exposure_type": "other_fixed_income",
            }
        )
        self.assertEqual(classify_evidence_bucket(row), "non_index_management")

    def test_non_portfolio_security_is_separated(self) -> None:
        row = pd.Series(
            {
                "management_style": "not_applicable_security",
                "primary_strategy": "other_equity",
                "asset_class_refined": "equity",
                "exposure_type": "other_equity",
            }
        )
        self.assertEqual(classify_evidence_bucket(row), "non_fund_security")

    def test_changed_mandate_is_not_attributed_over_the_full_history(self) -> None:
        row = pd.Series(
            {
                "management_style": "mixed_or_changed_mandate",
                "primary_strategy": "factor_or_style",
                "asset_class_refined": "equity",
                "exposure_type": "factor_style_or_income",
            }
        )
        self.assertEqual(classify_evidence_bucket(row), "mixed_mandate_not_attributed")


if __name__ == "__main__":
    unittest.main()
