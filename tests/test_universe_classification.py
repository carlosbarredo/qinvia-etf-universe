import unittest

from qinvia_etfs.universe import classify


def product(
    name: str,
    confidence: str = "high",
    current: bool = False,
    ticker: str = "TEST",
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "category": "",
        "fund_family": "",
        "candidate_confidence": confidence,
        "current_listing": current,
    }


class ClassificationTests(unittest.TestCase):
    def test_plain_equity_is_eligible(self) -> None:
        result = classify(product("Broad US Equity ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_inverse_is_ineligible(self) -> None:
        result = classify(product("Daily Inverse S&P 500 ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "inverse_exposure")

    def test_ultrashort_brand_is_ineligible(self) -> None:
        result = classify(product("ProShares UltraShort S&P 500 ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_ultrashort_fixed_income_is_eligible(self) -> None:
        result = classify(product("DoubleLine Ultrashort Income ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_ultra_proshares_is_leveraged(self) -> None:
        result = classify(product("ProShares Ultra S&P 500 ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_leveraged_is_ineligible(self) -> None:
        result = classify(product("Daily Semiconductor Bull 3X ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "leveraged_exposure")

    def test_fractional_leverage_is_ineligible(self) -> None:
        result = classify(product("GraniteShares 1.25x Long TSLA Daily ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_fractional_short_is_inverse(self) -> None:
        result = classify(product("Tradr 1.75X Short SPY Quarterly ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "inverse_exposure")

    def test_short_term_bond_is_not_inverse(self) -> None:
        result = classify(product("Short-Term Treasury Bond ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_minimum_volatility_is_not_vix_product(self) -> None:
        result = classify(product("MSCI USA Minimum Volatility ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_vix_futures_is_ineligible(self) -> None:
        result = classify(product("VIX Short-Term Futures ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "volatility_trading")

    def test_microsectors_short_is_inverse(self) -> None:
        result = classify(product("MicroSectors -3? Short Artificial Intelligence ETN"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_ultra_short_municipal_is_not_inverse(self) -> None:
        result = classify(product("Ultra Short Municipal Income Active ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_buffer_strategy_is_ineligible(self) -> None:
        result = classify(product("S&P 500 Defined Outcome Buffer ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "structured_path_dependent_payoff")

    def test_numbered_buffer_strategy_is_ineligible(self) -> None:
        result = classify(product("U.S. Equity Buffer15 Uncapped ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_autocallable_is_ineligible(self) -> None:
        result = classify(product("Index Autocallable Income Strategy ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_managed_futures_is_eligible_alternative_strategy(self) -> None:
        result = classify(product("Managed Futures Strategy ETF"))
        self.assertEqual(result["eligibility"], "eligible")
        self.assertIn("alternative_strategy", result["strategy_tags"])

    def test_return_stacked_is_ineligible_embedded_leverage(self) -> None:
        result = classify(product("Return Stacked Bonds & Managed Futures ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "embedded_leverage")

    def test_tail_risk_is_ineligible(self) -> None:
        result = classify(product("Equity Tail Risk ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_directional_short_is_ineligible(self) -> None:
        result = classify(product("Short Innovation ETF"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "inverse_exposure")

    def test_short_high_yield_muni_is_fixed_income_not_inverse(self) -> None:
        result = classify(product("Short High Yield Muni ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_ultra_short_government_is_fixed_income_not_inverse(self) -> None:
        result = classify(product("Ultra Short Government ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_ultra_short_option_income_is_inverse(self) -> None:
        result = classify(product("Ultra Short Option Income Strategy ETF"))
        self.assertEqual(result["eligibility"], "ineligible")

    def test_long_short_is_eligible_alternative_strategy(self) -> None:
        result = classify(product("First Trust Long/Short Equity ETF"))
        self.assertEqual(result["eligibility"], "eligible")
        self.assertIn("alternative_strategy", result["strategy_tags"])

    def test_market_neutral_is_eligible_alternative_strategy(self) -> None:
        result = classify(product("Equity Market Neutral ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_absolute_return_with_short_horizon_is_eligible(self) -> None:
        result = classify(product("Short Horizon Absolute Return ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_bull_rider_bear_fighter_is_not_inverse(self) -> None:
        result = classify(product("Merlyn.AI Bull-Rider Bear-Fighter ETF"))
        self.assertEqual(result["eligibility"], "eligible")

    def test_clo_is_fixed_income(self) -> None:
        result = classify(product("AAA CLO ETF"))
        self.assertEqual(result["asset_class"], "fixed_income")

    def test_large_cap_is_equity(self) -> None:
        result = classify(product("US Large Cap Growth ETF"))
        self.assertEqual(result["asset_class"], "equity")

    def test_low_confidence_requires_review(self) -> None:
        result = classify(product("Unclear Historical Fund", confidence="low"))
        self.assertEqual(result["eligibility"], "review")

    def test_validated_historical_identity_can_be_eligible(self) -> None:
        candidate = product("Historical Equity ETF", confidence="low")
        candidate["identity_status_override"] = "validated"
        result = classify(candidate)
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["identity_status"], "validated")

    def test_never_launched_identity_is_ineligible(self) -> None:
        candidate = product("Proposed Equity ETF", confidence="low")
        candidate["identity_status_override"] = "never_launched"
        result = classify(candidate)
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "never_launched")

    def test_registered_not_trading_identity_is_ineligible(self) -> None:
        candidate = product("Coming Soon Equity ETF", confidence="low")
        candidate["identity_status_override"] = "registered_not_trading"
        result = classify(candidate)
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "registered_not_trading")

    def test_registered_only_without_trading_evidence_is_ineligible(self) -> None:
        candidate = product("Registered Historical Fund", confidence="low")
        candidate["identity_status_override"] = "registered_only_no_trading_evidence"
        result = classify(candidate)
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(
            result["eligibility_reason"], "registered_only_no_trading_evidence"
        )

    def test_low_confidence_mutual_fund_share_class_is_ineligible(self) -> None:
        result = classify(
            product("Avantis Equity Fund", confidence="low", ticker="AVUSX")
        )
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "mutual_fund_share_class")
        self.assertEqual(result["identity_status"], "not_etp")

    def test_sec_etf_allocation_mutual_fund_is_ineligible_even_if_high_confidence(self) -> None:
        result = classify(
            product(
                "MainStay Growth ETF Allocation Fund",
                confidence="high",
                ticker="MOEIX",
                current=False,
            )
        )
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "mutual_fund_share_class")
        self.assertEqual(result["identity_status"], "not_etp")

    def test_low_confidence_invalid_listing_symbol_is_ineligible(self) -> None:
        result = classify(
            product("Not a quoted ETP", confidence="low", ticker="JEFFERIES")
        )
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "invalid_listing_symbol")
        self.assertEqual(result["identity_status"], "invalid_listing_symbol")

    def test_yahoo_caret_symbol_is_not_a_tradable_etf_listing(self) -> None:
        result = classify(product("Vanguard Bond Index Fund", ticker="^BND"))
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["eligibility_reason"], "yahoo_non_tradable_symbol")
        self.assertEqual(result["identity_status"], "non_tradable_symbol")

    def test_excluded_historical_candidate_does_not_enter_review_queue(self) -> None:
        result = classify(
            product("Daily Sector Bull 3X ETF", confidence="low", ticker="BULL")
        )
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["identity_status"], "excluded_candidate_unvalidated")

    def test_current_low_confidence_uses_separate_identity_status(self) -> None:
        result = classify(product("Current Normal Equity ETF", confidence="low", current=True))
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["identity_status"], "current_listing_unlinked")


if __name__ == "__main__":
    unittest.main()
