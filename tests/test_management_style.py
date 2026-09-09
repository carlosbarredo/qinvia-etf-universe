import csv
from pathlib import Path
import tempfile
import unittest
import zipfile

from qinvia_etfs.management_style import (
    NcenEvidence,
    VALID_MANAGEMENT_STYLES,
    choose_ncen_evidence,
    find_management_override,
    infer_non_index_style,
    load_management_overrides,
    load_ncen_evidence,
)


def evidence(
    *,
    ticker: str,
    series_id: str,
    fund_name: str,
    accession: str,
    filing_date: str,
    is_etf: str,
    is_index: str,
) -> NcenEvidence:
    return NcenEvidence(
        ticker=ticker,
        series_id=series_id,
        fund_name=fund_name,
        accession_number=accession,
        filing_date=filing_date,
        report_ending_period=filing_date,
        is_etf=is_etf,
        is_index=is_index,
        source_zip="fixture.zip",
        source_url="https://www.sec.gov/fixture",
    )


class ManagementStyleEvidenceTests(unittest.TestCase):
    def test_parser_joins_ticker_to_fund_and_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026q1_ncen.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "SUBMISSION.tsv",
                    "ACCESSION_NUMBER\tCIK\tFILING_DATE\tREPORT_ENDING_PERIOD\n"
                    "0000000001-26-000001\t0000123456\t01-Jan-2026\t31-Dec-2025\n",
                )
                archive.writestr(
                    "FUND_REPORTED_INFO.tsv",
                    "ACCESSION_NUMBER\tFUND_ID\tSERIES_ID\tFUND_NAME\tIS_ETF\tIS_INDEX\n"
                    "0000000001-26-000001\tF1\tS000000001\tExample Index ETF\tY\tY\n",
                )
                archive.writestr(
                    "SHARES_OUTSTANDING.tsv",
                    "FUND_ID\tTICKER\nF1\tTEST\n",
                )
            rows = load_ncen_evidence([path])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ticker, "TEST")
        self.assertEqual(rows[0].series_id, "S000000001")
        self.assertEqual(rows[0].is_index, "Y")
        self.assertIn("123456", rows[0].source_url)

    def test_older_complete_row_beats_later_incomplete_row(self) -> None:
        rows = [
            evidence(
                ticker="KEEP",
                series_id="S1",
                fund_name="Keep Index ETF",
                accession="old",
                filing_date="2025-01-01",
                is_etf="Y",
                is_index="Y",
            ),
            evidence(
                ticker="KEEP",
                series_id="S1",
                fund_name="Keep Index ETF",
                accession="new",
                filing_date="2026-01-01",
                is_etf="",
                is_index="",
            ),
        ]
        chosen, _ = choose_ncen_evidence(
            rows, ticker="KEEP", product_name="Keep Index ETF", series_ids=["S1"]
        )
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.accession_number, "old")

    def test_series_identity_outranks_ticker_only_match(self) -> None:
        rows = [
            evidence(
                ticker="OLD",
                series_id="S1",
                fund_name="Durable Equity ETF",
                accession="series",
                filing_date="2025-01-01",
                is_etf="Y",
                is_index="Y",
            ),
            evidence(
                ticker="NEW",
                series_id="S2",
                fund_name="Durable Equity Opportunities ETF",
                accession="ticker",
                filing_date="2026-01-01",
                is_etf="Y",
                is_index="",
            ),
        ]
        chosen, route = choose_ncen_evidence(
            rows, ticker="NEW", product_name="Durable Equity ETF", series_ids=["S1"]
        )
        self.assertEqual(chosen.accession_number, "series")
        self.assertEqual(route, "series_id")

    def test_unrelated_reused_ticker_is_rejected(self) -> None:
        rows = [
            evidence(
                ticker="SAME",
                series_id="OTHER",
                fund_name="Completely Different Commodity Trust",
                accession="reuse",
                filing_date="2026-01-01",
                is_etf="Y",
                is_index="Y",
            )
        ]
        chosen, route = choose_ncen_evidence(
            rows,
            ticker="SAME",
            product_name="Legacy Municipal Bond ETF",
            series_ids=[],
        )
        self.assertIsNone(chosen)
        self.assertEqual(route, "no_ncen_match")

    def test_non_index_is_not_automatically_discretionary_active(self) -> None:
        style, _ = infer_non_index_style("Example Income ETF")
        self.assertEqual(style, "non_index_management_identified")
        systematic, _ = infer_non_index_style("Example Defined Outcome ETF")
        self.assertEqual(systematic, "systematic_or_rules_based")

    def test_override_ledger_is_sourced_and_covers_trigger_cases(self) -> None:
        ledger = Path(__file__).resolve().parents[1] / "docs/evidence/management_style_overrides.csv"
        rows = load_management_overrides(ledger)
        jaaa = find_management_override(rows, ticker="JAAA")
        atmp = find_management_override(rows, ticker="ATMP")
        btal = find_management_override(rows, ticker="BTAL")
        ark = find_management_override(rows, ticker="ARKK")
        self.assertEqual(jaaa["management_style"], "active_identified")
        self.assertEqual(atmp["management_style"], "not_applicable_security")
        self.assertEqual(btal["management_style"], "mixed_or_changed_mandate")
        self.assertEqual(ark["management_style"], "active_identified")

    def test_mixed_mandate_is_an_explicit_valid_category(self) -> None:
        self.assertIn("mixed_or_changed_mandate", VALID_MANAGEMENT_STYLES)

    def test_override_loader_rejects_unsourced_rows(self) -> None:
        fields = [
            "key_type",
            "key",
            "management_style",
            "management_confidence",
            "evidence",
            "source_url",
            "review_note",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "key_type": "ticker",
                        "key": "BAD",
                        "management_style": "active_identified",
                        "management_confidence": "low",
                        "evidence": "unsupported",
                        "source_url": "",
                        "review_note": "",
                    }
                )
            with self.assertRaises(ValueError):
                load_management_overrides(path)


if __name__ == "__main__":
    unittest.main()
