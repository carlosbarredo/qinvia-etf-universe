"""Auditable management-style evidence for the ETF universe.

The public study initially inferred management style from free product names.
This module adds primary-source evidence from the SEC N-CEN bulk datasets.  It
deliberately keeps SEC's ``is index fund`` answer separate from our taxonomy:
``No`` is not, by itself, proof of discretionary active management.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
import csv
import io
from pathlib import Path
import re
from typing import Iterable
import zipfile


MANAGEMENT_EVIDENCE_VERSION = "management_style_evidence_1.1"
VALID_MANAGEMENT_STYLES = {
    "active_identified",
    "index_passive_identified",
    "systematic_or_rules_based",
    "static_exposure_or_trust",
    "non_index_management_identified",
    "not_applicable_security",
    "mixed_or_changed_mandate",
}

SYSTEMATIC_NAME_PATTERN = re.compile(
    r"\b(buffer|defined (?:outcome|duration|protection)|accelerated|floor|laddered|"
    r"target maturity|term (?:corporate|treasury|municipal)|bulletshares|ibonds|"
    r"systematic|rules[- ]based)\b",
    re.IGNORECASE,
)

ACTIVE_NAME_PATTERN = re.compile(
    r"\b(active|actively managed|discretionary)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NcenEvidence:
    ticker: str
    series_id: str
    fund_name: str
    accession_number: str
    filing_date: str
    report_ending_period: str
    is_etf: str
    is_index: str
    source_zip: str
    source_url: str

    def as_record(self) -> dict[str, str]:
        return asdict(self)


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_ticker(value: object) -> str:
    return clean_text(value).upper().replace(".", "-")


def normalize_name(value: object) -> str:
    text = clean_text(value).lower()
    replacements = {
        "exchange traded fund": "etf",
        "exchange-traded fund": "etf",
        "index fund": "fund",
        "shares": "",
        "the ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9]+", "", text)


def name_similarity(left: object, right: object) -> float:
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def sec_filing_url(cik: str, accession: str) -> str:
    cik_clean = str(cik or "").lstrip("0")
    accession_clean = str(accession or "").replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/"
        f"{accession_clean}/{accession}-index.html"
    )


def _read_tsv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as raw:
        wrapper = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(wrapper, delimiter="\t"))


def _date_key(value: str) -> str:
    text = clean_text(value)
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def load_ncen_evidence(zip_paths: Iterable[Path]) -> list[NcenEvidence]:
    """Load fund-level N-CEN evidence and attach every reported ticker.

    N-CEN uses blank boolean cells for a negative answer in these bulk files.
    Consumers must still avoid translating a negative ``IS_INDEX`` answer
    directly into active management.
    """

    output: list[NcenEvidence] = []
    for zip_path in sorted(Path(path) for path in zip_paths):
        with zipfile.ZipFile(zip_path) as archive:
            submissions = {
                row["ACCESSION_NUMBER"]: row for row in _read_tsv(archive, "SUBMISSION.tsv")
            }
            funds = {row["FUND_ID"]: row for row in _read_tsv(archive, "FUND_REPORTED_INFO.tsv")}
            shares = _read_tsv(archive, "SHARES_OUTSTANDING.tsv")
            for share in shares:
                ticker = normalize_ticker(share.get("TICKER"))
                fund = funds.get(clean_text(share.get("FUND_ID")))
                if not ticker or not fund:
                    continue
                accession = clean_text(fund.get("ACCESSION_NUMBER"))
                submission = submissions.get(accession, {})
                output.append(
                    NcenEvidence(
                        ticker=ticker,
                        series_id=clean_text(fund.get("SERIES_ID")),
                        fund_name=clean_text(fund.get("FUND_NAME")),
                        accession_number=accession,
                        filing_date=_date_key(clean_text(submission.get("FILING_DATE"))),
                        report_ending_period=_date_key(
                            clean_text(submission.get("REPORT_ENDING_PERIOD"))
                        ),
                        is_etf=clean_text(fund.get("IS_ETF")).upper(),
                        is_index=clean_text(fund.get("IS_INDEX")).upper(),
                        source_zip=zip_path.name,
                        source_url=sec_filing_url(clean_text(submission.get("CIK")), accession),
                    )
                )
    return output


def choose_ncen_evidence(
    rows: Iterable[NcenEvidence],
    *,
    ticker: str,
    product_name: str,
    series_ids: Iterable[str] = (),
) -> tuple[NcenEvidence | None, str]:
    """Select the most relevant, most recent N-CEN observation.

    Series-id matches outrank ticker-only matches; within each group, product
    name similarity guards against ticker reuse.  A recent row with missing
    ETF/index fields does not erase an older complete observation.
    """

    ticker_key = normalize_ticker(ticker)
    series_set = {clean_text(value) for value in series_ids if clean_text(value)}
    candidates = [
        row for row in rows if row.ticker == ticker_key or row.series_id in series_set
    ]
    # A series id inherited through a reused ticker can point to an unrelated
    # legal fund.  Require name continuity for every unconfirmed match; a legal
    # series match is the strongest independent identity confirmation.
    candidates = [
        row
        for row in candidates
        if (
            row.series_id in series_set
            or (
                row.ticker == ticker_key
                and name_similarity(product_name, row.fund_name) >= 0.45
            )
        )
    ]
    if not candidates:
        return None, "no_ncen_match"

    def score(row: NcenEvidence) -> tuple[int, int, int, float, str, str]:
        ticker_match = int(row.ticker == ticker_key)
        series_match = int(bool(series_set and row.series_id in series_set))
        # In the SEC bulk datasets a blank IS_INDEX cell is the negative/false
        # representation; IS_ETF=Y is enough to treat it as a usable response.
        usable = int(row.is_etf == "Y")
        return (
            usable,
            series_match,
            ticker_match,
            name_similarity(product_name, row.fund_name),
            row.filing_date,
            row.report_ending_period,
        )

    selected = max(candidates, key=score)
    route = "series_id" if selected.series_id in series_set else "ticker"
    return selected, route


def is_ncen_index(evidence: NcenEvidence) -> bool:
    return evidence.is_index == "Y"


def infer_non_index_style(name: object, primary_strategy: object = "") -> tuple[str, str]:
    """Refine a verified non-index ETF without inventing discretion.

    The result intentionally falls back to ``non_index_management_identified``
    when the product name/strategy does not establish whether implementation is
    discretionary or mechanical.
    """

    text = f"{clean_text(name)} {clean_text(primary_strategy).replace('_', ' ')}"
    if ACTIVE_NAME_PATTERN.search(text):
        return "active_identified", "strategy_name_identifies_active_management"
    if SYSTEMATIC_NAME_PATTERN.search(text):
        return "systematic_or_rules_based", "strategy_name_identifies_rules_or_overlay"
    return "non_index_management_identified", "ncen_non_index_without_discretion_evidence"


def load_management_overrides(path: Path) -> list[dict[str, str]]:
    """Load sourced manual decisions used outside, or to refine, N-CEN."""

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "key_type",
        "key",
        "management_style",
        "management_confidence",
        "evidence",
        "source_url",
        "review_note",
    }
    if not rows:
        raise ValueError(f"Management override file is empty: {path}")
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"Missing override columns: {sorted(missing)}")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key_type = clean_text(row["key_type"])
        key = normalize_ticker(row["key"]) if key_type == "ticker" else clean_text(row["key"])
        style = clean_text(row["management_style"])
        if key_type not in {"ticker", "series_id"}:
            raise ValueError(f"Unsupported override key type: {key_type}")
        if not key or (key_type, key) in seen:
            raise ValueError(f"Missing or duplicate override key: {(key_type, key)}")
        if style not in VALID_MANAGEMENT_STYLES:
            raise ValueError(f"Unsupported management style for {key}: {style}")
        if not clean_text(row["source_url"]).startswith("https://"):
            raise ValueError(f"Override lacks a primary-source URL: {key}")
        seen.add((key_type, key))
        row["key_type"] = key_type
        row["key"] = key
    return rows


def find_management_override(
    overrides: Iterable[dict[str, str]], *, ticker: str, series_ids: Iterable[str] = ()
) -> dict[str, str] | None:
    ticker_key = normalize_ticker(ticker)
    series_set = {clean_text(value) for value in series_ids if clean_text(value)}
    by_ticker = [
        row for row in overrides if row["key_type"] == "ticker" and row["key"] == ticker_key
    ]
    if by_ticker:
        return by_ticker[0]
    by_series = [
        row
        for row in overrides
        if row["key_type"] == "series_id" and row["key"] in series_set
    ]
    return by_series[0] if by_series else None
