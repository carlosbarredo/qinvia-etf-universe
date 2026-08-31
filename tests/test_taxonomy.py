import unittest

from qinvia_etfs.taxonomy import classify_product


class TaxonomyTests(unittest.TestCase):
    def test_explicit_active(self) -> None:
        row = classify_product("JPMorgan Active Value ETF", "equity")
        self.assertEqual(row["management_style"], "active_identified")

    def test_activebeta_is_systematic(self) -> None:
        row = classify_product("Goldman Sachs ActiveBeta U.S. Large Cap Equity ETF", "equity")
        self.assertEqual(row["management_style"], "systematic_or_rules_based")

    def test_index_semiconductor(self) -> None:
        row = classify_product("iShares Semiconductor Index ETF", "equity")
        self.assertEqual(row["sector_theme"], "semiconductors")
        self.assertEqual(row["management_style"], "index_passive_identified")

    def test_managed_futures_is_active_alternative(self) -> None:
        row = classify_product("iMGP DBi Managed Futures Strategy ETF", "alternatives")
        self.assertEqual(row["primary_strategy"], "managed_futures")
        self.assertEqual(row["management_style"], "active_identified")

    def test_gold_is_commodity(self) -> None:
        row = classify_product("Physical Gold Shares ETF", "commodity")
        self.assertEqual(row["asset_class_refined"], "commodity")
        self.assertEqual(row["exposure_type"], "precious_metals")

    def test_cash_cows_is_equity_factor_not_cash_instrument(self) -> None:
        row = classify_product("Pacer US Cash Cows 100 ETF", "equity")
        self.assertEqual(row["asset_class_refined"], "equity")
        self.assertEqual(row["primary_strategy"], "factor_or_style")

    def test_currency_hedged_equity_is_not_long_short(self) -> None:
        row = classify_product("Xtrackers MSCI EAFE Hedged Equity ETF", "equity")
        self.assertEqual(row["asset_class_refined"], "equity")
        self.assertNotEqual(row["primary_strategy"], "long_short_market_neutral")
        self.assertEqual(row["management_style"], "index_passive_identified")


if __name__ == "__main__":
    unittest.main()
