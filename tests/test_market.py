import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from qinvia_etfs.benchmark import performance_metrics
from qinvia_etfs.market import (
    load_targets,
    normalize_history,
    order_targets,
    projected_completion,
    storage_key,
)


class MarketCollectorTests(unittest.TestCase):
    def test_load_targets_deduplicates_ticker_but_keeps_identities(self) -> None:
        content = (
            "product_id,ticker,eligibility,current_listing,first_seen_year,last_seen_year\n"
            "p1,AAA,eligible,True,2020,2026\n"
            "p2,AAA,eligible,False,2010,2015\n"
            "p3,BBB,ineligible,True,2020,2026\n"
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eligible.csv"
            path.write_text(content, encoding="utf-8")
            targets = load_targets(path)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["request_symbol"], "AAA")
        self.assertEqual(len(targets[0]["product_ids"]), 2)
        self.assertEqual(targets[0]["current_identity_count"], 1)
        self.assertEqual(targets[0]["historical_identity_count"], 1)

    def test_yahoo_dot_symbol_is_mapped_to_dash(self) -> None:
        content = (
            "product_id,ticker,eligibility,current_listing,first_seen_year,last_seen_year\n"
            "p1,ABC.D,eligible,True,2020,2026\n"
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eligible.csv"
            path.write_text(content, encoding="utf-8")
            targets = load_targets(path)
        self.assertEqual(targets[0]["request_symbol"], "ABC-D")
        self.assertEqual(targets[0]["catalog_symbol"], "ABC.D")

    def test_pilot_order_starts_with_spy_and_mixes_lifecycle(self) -> None:
        targets = [
            {
                "request_symbol": symbol,
                "current_identity_count": current,
                "first_seen_year": year,
            }
            for symbol, current, year in (
                ("SPY", 1, 1993),
                ("AAA", 1, 2020),
                ("BBB", 1, 2021),
                ("OLD", 0, 2010),
                ("DED", 0, 2012),
            )
        ]
        ordered = order_targets(targets, pilot_size=4)
        pilot = ordered[:4]
        self.assertEqual(pilot[0]["request_symbol"], "SPY")
        self.assertTrue(any(item["current_identity_count"] == 0 for item in pilot))
        self.assertTrue(any(item["current_identity_count"] > 0 for item in pilot))

    def test_normalize_history_preserves_adjusted_and_actions(self) -> None:
        index = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="America/New_York")
        frame = pd.DataFrame(
            {
                "Open": [10.0, 10.5],
                "High": [11.0, 11.0],
                "Low": [9.5, 10.0],
                "Close": [10.5, 10.8],
                "Adj Close": [10.4, 10.8],
                "Volume": [1000, 1200],
                "Dividends": [0.0, 0.2],
                "Stock Splits": [0.0, 0.0],
            },
            index=index,
        )
        result = normalize_history(frame, "TEST")
        self.assertEqual(list(result["symbol"]), ["TEST", "TEST"])
        self.assertEqual(float(result["adj_close"].iloc[0]), 10.4)
        self.assertEqual(float(result["dividends"].iloc[1]), 0.2)
        self.assertIn("capital_gains", result.columns)

    def test_storage_key_is_stable_and_filesystem_safe(self) -> None:
        self.assertEqual(storage_key("ABC-D"), storage_key("ABC-D"))
        self.assertRegex(storage_key("ABC-D"), r"^[A-Z0-9_]+$")

    def test_eta_uses_fresh_requests_when_resuming(self) -> None:
        projected, completion = projected_completion(
            elapsed=10.0,
            completed=60,
            total=100,
            request_durations=[1.0, 2.0, 3.0],
            delay=0.5,
        )
        self.assertEqual(projected, 110.0)
        self.assertTrue(completion.endswith("+00:00"))

    def test_performance_metrics_include_drawdown_ratios(self) -> None:
        index = pd.date_range("2020-01-01", periods=504, freq="B")
        prices = pd.Series([100 * (1.0005**day) for day in range(504)], index=index)
        prices.iloc[200:220] *= 0.90
        result = performance_metrics(prices)
        self.assertEqual(result["return_observations"], 503)
        self.assertGreater(result["cagr"], 0)
        self.assertLess(result["max_drawdown"], 0)
        self.assertGreater(result["calmar"], 0)
        self.assertGreater(result["martin"], 0)
        self.assertGreater(result["sortino"], 0)


if __name__ == "__main__":
    unittest.main()
