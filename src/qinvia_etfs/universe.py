"""Build and classify a free, metadata-only universe of US-listed ETPs."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORK_ROOT = Path(os.environ.get("QINVIA_WORK_ROOT", str(PROJECT_ROOT))).expanduser().resolve()
EXPORT_ROOT_VALUE = os.environ.get("QINVIA_EXPORT_ROOT", "").strip()
EXPORT_ROOT = Path(EXPORT_ROOT_VALUE).expanduser().resolve() if EXPORT_ROOT_VALUE else None
RAW_ROOT = WORK_ROOT / "data" / "raw" / "universe"
INTERIM_ROOT = WORK_ROOT / "data" / "interim" / "universe"
PROCESSED_ROOT = WORK_ROOT / "data" / "processed" / "universe"
RUNTIME_ROOT = WORK_ROOT / "runtime"

STATUS_PATH = RUNTIME_ROOT / "universe_status.json"
LOCK_PATH = RUNTIME_ROOT / "universe.lock"
LOG_PATH = RUNTIME_ROOT / "universe_collector.log"

CLASSIFICATION_VERSION = "2026-08-28.9"
USER_AGENT = os.environ.get(
    "QINVIA_USER_AGENT",
    "QinviaETFResearch/0.1 local-noncommercial-research",
)
SEC_COOLDOWN_SECONDS = int(os.environ.get("QINVIA_SEC_COOLDOWN_SECONDS", "620"))

NASDAQ_URLS = {
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}

SEC_URLS = {
    2010: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investmentcompanyseriesclass2010.csv",
    2011: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2011.csv",
    2012: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2012.csv",
    2013: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2013.csv",
    2014: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2014.csv",
    2015: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2015.csv",
    2016: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class.csv",
    2017: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2017.csv",
    2018: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2018.csv",
    2019: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2019.csv",
    2020: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2020.csv",
    2021: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2021.csv",
    2022: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment_company_series_class_2022.csv",
    2023: "https://www.sec.gov/files/investment/data/other/investment-company-series-class-information/investment_company_series_class_2023.csv",
    2024: "https://www.sec.gov/files/investment/data/other/investment-company-series-and-class-information/investment-company-series-class-2024.csv",
    2025: "https://www.sec.gov/files/investment/data/other/investment-company-series-class-information/investment-company-series-class-2025.csv",
    2026: "https://www.sec.gov/files/investment/data/other/investment-company-series-class-information/investment-company-series-class-2026.csv",
}

CSV_FIELDS = [
    "product_id",
    "ticker",
    "name",
    "product_type",
    "exchange",
    "currency",
    "category",
    "fund_family",
    "status",
    "current_listing",
    "first_seen_year",
    "last_seen_year",
    "sec_series_id",
    "sec_class_id",
    "sources",
    "candidate_confidence",
    "identity_status",
    "identity_evidence",
    "identity_evidence_url",
    "identity_validation_note",
    "asset_class",
    "strategy_tags",
    "eligibility",
    "eligibility_reason",
    "matched_rules",
    "classification_version",
]

IDENTITY_OVERRIDE_FIELDS = [
    "product_id",
    "identity_status",
    "identity_evidence",
    "identity_evidence_url",
    "identity_validation_note",
    "validated_at",
]
IDENTITY_OVERRIDES_PATH = Path(
    os.environ.get(
        "QINVIA_IDENTITY_OVERRIDES",
        str(PROJECT_ROOT / "data" / "curated" / "universe" / "identity_overrides.csv"),
    )
).expanduser()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_logging() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
        force=True,
    )
    logging.Formatter.converter = time.gmtime


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def update_status(phase: str, message: str, **extra: Any) -> None:
    previous: dict[str, Any] = {}
    if phase != "starting" and STATUS_PATH.exists():
        try:
            previous = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    payload = {
        **previous,
        "phase": phase,
        "message": message,
        "updated_at": utc_now(),
        **extra,
    }
    payload.setdefault("started_at", utc_now())
    atomic_json(STATUS_PATH, payload)
    logging.info("%s: %s", phase, message)


def download_file(url: str, destination: Path, source: str, max_attempts: int = 4) -> Path:
    if destination.exists() and destination.stat().st_size > 100:
        logging.info("Reusing %s", destination)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, max_attempts + 1):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/csv,text/plain,*/*",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size <= 100:
                raise OSError(f"Response too small: {temporary.stat().st_size} bytes")
            os.replace(temporary, destination)
            logging.info("Downloaded %s (%s bytes)", destination.name, destination.stat().st_size)
            return destination
        except HTTPError as error:
            body = error.read(4096).decode("utf-8", errors="ignore")
            rate_limited = error.code == 403 and "Rate Threshold Exceeded" in body
            if source == "sec" and rate_limited and attempt < max_attempts:
                wait_seconds = SEC_COOLDOWN_SECONDS + (attempt - 1) * 300
                update_status(
                    "waiting_sec_cooldown",
                    f"La SEC ha limitado temporalmente el acceso; reintento en {wait_seconds // 60} minutos.",
                    current_url=url,
                    retry_attempt=attempt,
                    retry_in_seconds=wait_seconds,
                )
                time.sleep(wait_seconds)
                continue
            logging.warning("Download failed (%s) %s attempt %s/%s", error.code, url, attempt, max_attempts)
        except (URLError, TimeoutError, OSError) as error:
            logging.warning("Download failed %s attempt %s/%s: %s", url, attempt, max_attempts, error)

        if attempt < max_attempts:
            time.sleep(min(60, 2**attempt * 3))

    temporary.unlink(missing_ok=True)
    raise RuntimeError(f"Could not download {url}")


def parse_pipe_file(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="|"))
    return [row for row in rows if not any(str(value).startswith("File Creation Time") for value in row.values())]


def collect_nasdaq(run_id: str) -> dict[str, dict[str, Any]]:
    run_root = RAW_ROOT / "nasdaq" / run_id
    records: dict[str, dict[str, Any]] = {}
    for source_name, url in NASDAQ_URLS.items():
        path = download_file(url, run_root / f"{source_name}.txt", "nasdaq")
        for row in parse_pipe_file(path):
            if row.get("ETF", "").upper() != "Y" or row.get("Test Issue", "").upper() == "Y":
                continue
            ticker = (row.get("Symbol") or row.get("ACT Symbol") or "").strip().upper()
            if not ticker:
                continue
            records[ticker] = {
                "ticker": ticker,
                "name": (row.get("Security Name") or "").strip(),
                "exchange": (row.get("Exchange") or "NASDAQ").strip(),
                "sources": {"nasdaq"},
                "current_listing": True,
            }
    logging.info("Nasdaq directories supplied %s current ETF listings", len(records))
    return records


def raw_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("raw", value.get("fmt", ""))
    return value if value is not None else ""


def collect_yahoo(run_id: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    warnings: list[str] = []
    try:
        import yfinance as yf
        from yfinance import ETFQuery
    except ImportError:
        return {}, ["yfinance no está instalado; se omitió el enriquecimiento de Yahoo."]

    output_root = RAW_ROOT / "yahoo" / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    query = ETFQuery("eq", ["region", "us"])
    records: dict[str, dict[str, Any]] = {}
    seen_pages: set[tuple[str, ...]] = set()
    offset = 0

    for page_number in range(1, 25):
        try:
            response = yf.screen(query, offset=offset, size=250, sortField="ticker", sortAsc=True)
        except Exception as error:  # Yahoo failures vary by backend version.
            warnings.append(f"Yahoo screener falló en offset {offset}: {type(error).__name__}: {error}")
            break
        quotes = response.get("quotes", []) if isinstance(response, dict) else []
        symbols = tuple(str(item.get("symbol", "")).upper() for item in quotes)
        if not quotes or symbols in seen_pages:
            break
        seen_pages.add(symbols)
        atomic_json(output_root / f"page_{page_number:02d}.json", response)

        for quote in quotes:
            ticker = str(quote.get("symbol", "")).strip().upper()
            if not ticker:
                continue
            records[ticker] = {
                "ticker": ticker,
                "name": str(raw_value(quote.get("longName")) or raw_value(quote.get("shortName")) or "").strip(),
                "exchange": str(raw_value(quote.get("exchange")) or "").strip(),
                "currency": str(raw_value(quote.get("currency")) or "").strip(),
                "category": str(raw_value(quote.get("categoryName")) or raw_value(quote.get("category")) or "").strip(),
                "fund_family": str(raw_value(quote.get("fundFamily")) or "").strip(),
                "sources": {"yahoo"},
                "current_listing": True,
            }

        offset += len(quotes)
        total = int(response.get("total", 0) or 0)
        update_status(
            "collecting_yahoo",
            f"Yahoo: {len(records)} ETFs actuales recopilados.",
            yahoo_records=len(records),
            yahoo_total_reported=total,
        )
        if len(quotes) < 250 or (total and offset >= total):
            break
        time.sleep(1.0)

    logging.info("Yahoo supplied %s current ETF records", len(records))
    return records, warnings


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def row_value(row: dict[str, str], *possible_names: str) -> str:
    normalized = {normalized_header(key): (value or "").strip() for key, value in row.items()}
    for name in possible_names:
        value = normalized.get(normalized_header(name), "")
        if value:
            return value
    return ""


def looks_like_ticker(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{0,11}", value.upper()))


def has_etf_marker(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\betfs?\b|exchange[ -]traded|\betps?\b", lowered))


def collect_sec(current_tickers: set[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    records: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    total_years = len(SEC_URLS)

    for completed, (year, url) in enumerate(SEC_URLS.items(), start=1):
        update_status(
            "collecting_sec",
            f"SEC: snapshot {year} ({completed}/{total_years}).",
            sec_year=year,
            sec_years_completed=completed - 1,
            sec_years_total=total_years,
        )
        path = RAW_ROOT / "sec" / f"series_class_{year}.csv"
        try:
            download_file(url, path, "sec", max_attempts=2)
        except RuntimeError as error:
            warnings.append(str(error))
            warnings.append(
                "Se omitieron los snapshots SEC restantes en esta ejecución porque el endpoint oficial continúa limitado."
            )
            break

        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = row_value(row, "Class Ticker", "Class Ticker Symbol", "Ticker").upper()
                if not looks_like_ticker(ticker):
                    continue
                entity_name = row_value(row, "Name of Investment Company", "Entity Name")
                series_name = row_value(row, "Series Name")
                class_name = row_value(row, "Class Name")
                combined_name = " ".join(part for part in (series_name, class_name, entity_name) if part)
                explicit_marker = has_etf_marker(" ".join((series_name, class_name)))
                entity_marker = has_etf_marker(entity_name)
                current_match = ticker in current_tickers
                if not (explicit_marker or entity_marker or current_match):
                    continue

                series_id = row_value(row, "Series ID")
                class_id = row_value(row, "Class ID")
                identity_seed = f"{series_id}|{class_id}|{ticker}|{series_name}|{class_name}"
                identity_hash = hashlib.sha1(identity_seed.encode("utf-8")).hexdigest()[:12]
                product_id = f"SEC-{series_id or 'NA'}-{class_id or identity_hash}"
                record = records.setdefault(
                    product_id,
                    {
                        "product_id": product_id,
                        "ticker": ticker,
                        "name": series_name or class_name or entity_name,
                        "sec_series_id": series_id,
                        "sec_class_id": class_id,
                        "sources": set(),
                        "snapshot_years": set(),
                        "candidate_confidence": "high" if explicit_marker or current_match else "low",
                    },
                )
                record["sources"].add("sec")
                record["snapshot_years"].add(year)
                if not record.get("name"):
                    record["name"] = combined_name
                if record["candidate_confidence"] != "high" and (explicit_marker or current_match):
                    record["candidate_confidence"] = "high"

        time.sleep(1.05)

    logging.info("SEC snapshots supplied %s ETF candidates", len(records))
    return records, warnings


def merge_catalog(
    sec_records: dict[str, dict[str, Any]],
    nasdaq_records: dict[str, dict[str, Any]],
    yahoo_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records = list(sec_records.values())
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_ticker.setdefault(record["ticker"], []).append(record)

    current_tickers = sorted(set(nasdaq_records) | set(yahoo_records))
    for ticker in current_tickers:
        metadata = {**yahoo_records.get(ticker, {}), **nasdaq_records.get(ticker, {})}
        metadata["sources"] = set(yahoo_records.get(ticker, {}).get("sources", set())) | set(
            nasdaq_records.get(ticker, {}).get("sources", set())
        )
        candidates = by_ticker.get(ticker, [])
        latest_candidates = [
            item for item in candidates if item.get("snapshot_years") and max(item["snapshot_years"]) == max(SEC_URLS)
        ]
        if len(latest_candidates) == 1:
            target = latest_candidates[0]
        elif not candidates:
            seed = f"{metadata.get('exchange', '')}|{ticker}|{metadata.get('name', '')}"
            product_id = "LISTING-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]
            target = {
                "product_id": product_id,
                "ticker": ticker,
                "sources": set(),
                "snapshot_years": set(),
                "candidate_confidence": "high",
            }
            records.append(target)
            by_ticker.setdefault(ticker, []).append(target)
        else:
            target = {
                "product_id": "LISTING-" + hashlib.sha1(f"current|{ticker}".encode("utf-8")).hexdigest()[:14],
                "ticker": ticker,
                "sources": set(),
                "snapshot_years": set(),
                "candidate_confidence": "low",
            }
            records.append(target)
            by_ticker.setdefault(ticker, []).append(target)

        for key in ("name", "exchange", "currency", "category", "fund_family"):
            if metadata.get(key):
                target[key] = metadata[key]
        target["sources"].update(metadata.get("sources", set()))
        target["current_listing"] = True

    for record in records:
        years = sorted(record.pop("snapshot_years", set()))
        record["first_seen_year"] = years[0] if years else ""
        record["last_seen_year"] = years[-1] if years else ""
        record.setdefault("current_listing", False)
        record["status"] = "active" if record["current_listing"] else "historical_candidate"
        record["sources"] = "|".join(sorted(record.get("sources", set())))
        record.setdefault("candidate_confidence", "high")
        record.setdefault("name", "")
        record.setdefault("exchange", "")
        record.setdefault("currency", "")
        record.setdefault("category", "")
        record.setdefault("fund_family", "")
        record.setdefault("sec_series_id", "")
        record.setdefault("sec_class_id", "")
    return records


def infer_product_type(text: str) -> str:
    if re.search(r"\betn\b|exchange[ -]traded notes?", text):
        return "ETN"
    if re.search(r"\betc\b", text):
        return "ETC"
    if re.search(r"\betp\b", text):
        return "ETP"
    return "ETF"


def infer_asset_class(text: str) -> str:
    if re.search(r"bitcoin|ether|ethereum|solana|crypto|digital asset", text):
        return "crypto"
    if re.search(
        r"treasury|bond|fixed income|municipal|\bmuni\b|mortgage|high yield|floating rate|duration|\bclo\b|credit|senior loan|bank loan|preferred securit|securitized debt|money market",
        text,
    ):
        return "fixed_income"
    if re.search(r"gold|silver|copper|uranium|oil|crude|natural gas|commodity|commodities|agriculture|wheat|corn", text):
        return "commodity"
    if re.search(r"real estate|\breit\b|property", text):
        return "real_estate"
    if re.search(r"currency|\busd\b|dollar|euro|yen|sterling|forex", text):
        return "currency"
    if re.search(r"multi[ -]asset|balanced|allocation", text):
        return "multi_asset"
    if re.search(r"managed futures|market neutral|long/short|absolute return|merger arbitrage", text):
        return "alternatives"
    if re.search(
        r"equity|stock|shares|s&p|nasdaq|russell|msci|dow jones|sector|dividend|large[ -]cap|mid[ -]cap|small[ -]cap|micro[ -]cap|growth|value|quality|momentum|leaders|consumer|industrials?|health ?care|financials?|technology|semiconductor|infrastructure|clean energy|artificial intelligence|innovation|covered call|option income|weeklypay|buy[ -]?write",
        text,
    ):
        return "equity"
    return "unknown"


def classify(record: dict[str, Any]) -> dict[str, Any]:
    ticker = str(record.get("ticker", "")).strip().upper()
    name_text = str(record.get("name", "")).lower()
    category_text = str(record.get("category", "")).lower()
    text = " ".join(
        str(record.get(field, "")) for field in ("name", "category", "fund_family")
    ).lower()
    rules: list[str] = []
    tags: list[str] = []

    alternative_strategy = bool(
        re.search(
            r"\blong\b[^,;]{0,50}\bshort\b|market neutral|absolute return",
            text,
        )
    )
    short_maturity_fixed_income = bool(
        re.search(
            r"short[ -](?:term|duration|maturity|dated)|short[ -]bond|"
            r"short (?:government|fixed income|municipal|muni|high[ -]yield (?:municipal|muni))|"
            r"ultra[ -]short (?:government|investment grade|fixed income|municipal|muni|income|bond|treasury|duration|term|t-bill)",
            text,
        )
    )
    directional_short = bool(
        re.search(r"\bshort\b", text)
        and not alternative_strategy
        and not short_maturity_fixed_income
    )
    inverse = bool(
        re.search(
            r"\binverse\b|\b-1x\b|\bbear\b|daily short|short .*daily|proshares.*\bultrashort\b|microsectors.*short|(?<![0-9])\d+(?:\.\d+)?(?:x|\?) short|short (s&p|nasdaq|qqq|dow|russell|msci|bitcoin|ether|oil|gold)",
            name_text,
        )
        or "trading--inverse" in category_text
        or directional_short
    ) and not re.search(r"bull-rider bear-fighter", name_text)
    leveraged = bool(
        re.search(
            r"(?<![0-9.])(?:[2-9]|[1-9]\d+|1\.(?!0+(?:x|\?))\d+)(?:x|\?)(?![a-z0-9])|\bleveraged\b|ultrapro|proshares.*\bultra\b|daily .*(bull|long).*[234]x|double long|triple long",
            name_text,
        )
        or "trading--leveraged" in category_text
    )
    volatility = bool(
        re.search(r"\bvix\b|volatility futures|volatility index", name_text)
        and not re.search(r"minimum volatility|low volatility|min vol", name_text)
    )
    structured_path_dependent = bool(
        re.search(
            r"defined outcome|structured outcome|\bbuffer(?:ed)?\d*\b|accelerated outcome|target outcome|autocallable|\bbarrier\b|\bcollared\b|lightning.?spread",
            text,
        )
    )
    tail_risk = bool(re.search(r"tail risk", text))
    managed_futures = bool(re.search(r"managed futures", text))
    embedded_leverage = bool(
        re.search(r"return stacked|capital efficient|efficient core", text)
    )
    mutual_fund_share_class = bool(
        not record.get("current_listing")
        and re.fullmatch(r"[A-Z]{4}X", ticker)
    )
    invalid_listing_symbol = bool(
        record.get("candidate_confidence") == "low"
        and not record.get("current_listing")
        and not re.fullmatch(r"[A-Z0-9]{1,5}(?:[.-][A-Z0-9]{1,2})?", ticker)
    )
    yahoo_non_tradable_symbol = ticker.startswith("^")
    identity_override = str(record.get("identity_status_override", "")).strip()

    if inverse:
        tags.append("inverse")
        rules.append("inverse_pattern")
    if leveraged:
        tags.append("leveraged")
        rules.append("leverage_pattern")
    if volatility:
        tags.append("volatility")
        rules.append("volatility_trading_pattern")
    if re.search(r"covered call|buywrite|buy-write|option income", text):
        tags.append("options_income")
    if alternative_strategy or managed_futures:
        tags.append("alternative_strategy")
    if structured_path_dependent:
        tags.append("complex_strategy")
        rules.append("structured_path_dependent_pattern")
    if tail_risk:
        tags.extend(("complex_strategy", "tail_risk"))
        rules.append("tail_risk_pattern")
    if managed_futures:
        tags.append("managed_futures")
        rules.append("managed_futures_pattern")
    if embedded_leverage:
        tags.extend(("complex_strategy", "embedded_leverage", "leveraged"))
        rules.append("embedded_leverage_pattern")
    if mutual_fund_share_class:
        tags.append("non_etp")
        rules.append("mutual_fund_share_class_pattern")
    if invalid_listing_symbol:
        tags.append("non_etp")
        rules.append("invalid_listing_symbol_pattern")
    if yahoo_non_tradable_symbol:
        tags.append("non_tradable_symbol")
        rules.append("yahoo_non_tradable_symbol_pattern")
    if identity_override:
        rules.append(f"identity_override_{identity_override}")

    if inverse:
        eligibility, reason = "ineligible", "inverse_exposure"
    elif leveraged:
        eligibility, reason = "ineligible", "leveraged_exposure"
    elif volatility:
        eligibility, reason = "ineligible", "volatility_trading"
    elif embedded_leverage:
        eligibility, reason = "ineligible", "embedded_leverage"
    elif structured_path_dependent:
        eligibility, reason = "ineligible", "structured_path_dependent_payoff"
    elif tail_risk:
        eligibility, reason = "ineligible", "protective_tail_risk_strategy"
    elif mutual_fund_share_class:
        eligibility, reason = "ineligible", "mutual_fund_share_class"
    elif invalid_listing_symbol:
        eligibility, reason = "ineligible", "invalid_listing_symbol"
    elif yahoo_non_tradable_symbol:
        eligibility, reason = "ineligible", "yahoo_non_tradable_symbol"
    elif identity_override == "never_launched":
        eligibility, reason = "ineligible", "never_launched"
    elif identity_override == "registered_not_trading":
        eligibility, reason = "ineligible", "registered_not_trading"
    elif identity_override == "registered_only_no_trading_evidence":
        eligibility, reason = "ineligible", "registered_only_no_trading_evidence"
    elif (
        record.get("candidate_confidence") == "low"
        and not record.get("current_listing")
        and identity_override != "validated"
    ):
        eligibility, reason = "review", "candidate_identity_needs_validation"
        rules.append("low_candidate_confidence")
    else:
        eligibility, reason = "eligible", "no_exclusion_rule_matched"

    record["product_type"] = infer_product_type(text)
    record["asset_class"] = infer_asset_class(text)
    record["strategy_tags"] = "|".join(sorted(set(tags)))
    if identity_override:
        record["identity_status"] = identity_override
    elif mutual_fund_share_class:
        record["identity_status"] = "not_etp"
    elif invalid_listing_symbol:
        record["identity_status"] = "invalid_listing_symbol"
    elif yahoo_non_tradable_symbol:
        record["identity_status"] = "non_tradable_symbol"
    elif record.get("candidate_confidence") == "low":
        if record.get("current_listing"):
            record["identity_status"] = "current_listing_unlinked"
        elif eligibility == "ineligible":
            record["identity_status"] = "excluded_candidate_unvalidated"
        else:
            record["identity_status"] = "historical_candidate_unvalidated"
    else:
        record["identity_status"] = "validated"
    record["eligibility"] = eligibility
    record["eligibility_reason"] = reason
    record["matched_rules"] = "|".join(sorted(set(rules)))
    record["classification_version"] = CLASSIFICATION_VERSION
    return record


def apply_identity_overrides(records: list[dict[str, Any]]) -> int:
    """Attach curated identity evidence without changing source confidence."""
    if not IDENTITY_OVERRIDES_PATH.exists():
        return 0
    with IDENTITY_OVERRIDES_PATH.open("r", encoding="utf-8", newline="") as handle:
        overrides = {
            row["product_id"]: row
            for row in csv.DictReader(handle)
            if row.get("product_id") and row.get("identity_status")
        }
    applied = 0
    for record in records:
        override = overrides.get(str(record.get("product_id", "")))
        if not override:
            continue
        record["identity_status_override"] = override["identity_status"]
        for field in (
            "identity_evidence",
            "identity_evidence_url",
            "identity_validation_note",
        ):
            if override.get(field):
                record[field] = override[field]
        applied += 1
    return applied


def write_csv(path: Path, records: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})
    os.replace(temporary, path)


def counter_table(counter: Counter[str], first_column: str) -> str:
    lines = [f"| {first_column} | Productos |", "|---|---:|"]
    lines.extend(f"| {key or '(vacío)'} | {value} |" for key, value in counter.most_common())
    return "\n".join(lines)


def generate_report(records: list[dict[str, Any]], warnings: list[str], started: float) -> str:
    eligibility = Counter(str(item["eligibility"]) for item in records)
    asset_classes = Counter(str(item["asset_class"]) for item in records)
    statuses = Counter(str(item["status"]) for item in records)
    product_types = Counter(str(item["product_type"]) for item in records)
    sources = Counter(source for item in records for source in str(item["sources"]).split("|") if source)
    reasons = Counter(str(item["eligibility_reason"]) for item in records)
    review_examples = [item for item in records if item["eligibility"] == "review"][:30]

    warning_block = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- Ninguna advertencia de ejecución."
    review_block = "\n".join(
        f"- `{item['ticker']}` — {item['name']} ({item['eligibility_reason']})" for item in review_examples
    ) or "- No hay casos pendientes."

    return f"""# Informe del universo de ETFs

Generado: {utc_now()}

Versión de clasificación: `{CLASSIFICATION_VERSION}`
Duración: {time.monotonic() - started:.1f} segundos

## Resumen

- Productos/identidades en el catálogo: **{len(records):,}**
- Elegibles para descarga posterior: **{eligibility.get('eligible', 0):,}**
- No elegibles: **{eligibility.get('ineligible', 0):,}**
- Pendientes de revisión: **{eligibility.get('review', 0):,}**

## Elegibilidad

{counter_table(eligibility, 'Estado')}

## Motivos de clasificación

{counter_table(reasons, 'Motivo')}

## Clases de activo inferidas

{counter_table(asset_classes, 'Clase')}

## Estado del producto

{counter_table(statuses, 'Estado')}

## Tipo jurídico inferido

{counter_table(product_types, 'Tipo')}

## Cobertura por fuente

{counter_table(sources, 'Fuente')}

## Primeros casos en revisión

{review_block}

## Advertencias

{warning_block}

## Interpretación

Este catálogo se ha construido solo con metadatos. `historical_candidate` significa que el producto apareció en una fuente histórica pero no se confirmó como cotización actual; no equivale todavía a una liquidación verificada. Ningún producto marcado `review` se descartará automáticamente.
"""


def export_results() -> None:
    if EXPORT_ROOT is None or EXPORT_ROOT == WORK_ROOT:
        return
    export_interim = EXPORT_ROOT / "data" / "interim" / "universe"
    export_processed = EXPORT_ROOT / "data" / "processed" / "universe"
    export_runtime = EXPORT_ROOT / "runtime"
    export_interim.mkdir(parents=True, exist_ok=True)
    export_processed.mkdir(parents=True, exist_ok=True)
    export_runtime.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INTERIM_ROOT / "catalog.csv", export_interim / "catalog.csv")
    for filename in ("review_queue.csv", "eligible_universe.csv", "universe_report.md", "run_manifest.json"):
        shutil.copy2(PROCESSED_ROOT / filename, export_processed / filename)
    shutil.copy2(STATUS_PATH, export_runtime / "universe_status.json")
    logging.info("Exported final catalog and report to %s", EXPORT_ROOT)


def main() -> int:
    configure_logging()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logging.error("Another universe collector is already running")
        return 2

    started = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    warnings: list[str] = []
    update_status(
        "starting",
        "Iniciando catálogo de metadatos.",
        run_id=run_id,
        pid=os.getpid(),
        started_at=utc_now(),
        work_root=str(WORK_ROOT),
        export_root=str(EXPORT_ROOT) if EXPORT_ROOT else "",
    )

    try:
        update_status("collecting_nasdaq", "Recopilando listados actuales de las bolsas.")
        nasdaq = collect_nasdaq(run_id)

        update_status("collecting_yahoo", "Enriqueciendo el catálogo actual con Yahoo.")
        yahoo, yahoo_warnings = collect_yahoo(run_id)
        warnings.extend(yahoo_warnings)

        current_tickers = set(nasdaq) | set(yahoo)
        update_status("collecting_sec", "Buscando identidades históricas en snapshots de la SEC.")
        sec, sec_warnings = collect_sec(current_tickers)
        warnings.extend(sec_warnings)

        update_status("classifying", "Fusionando identidades y aplicando reglas de elegibilidad.")
        merged = merge_catalog(sec, nasdaq, yahoo)
        apply_identity_overrides(merged)
        catalog = [classify(item) for item in merged]
        catalog.sort(key=lambda item: (str(item["ticker"]), str(item["product_id"])))

        INTERIM_ROOT.mkdir(parents=True, exist_ok=True)
        PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
        write_csv(INTERIM_ROOT / "catalog.csv", catalog, CSV_FIELDS)
        write_csv(
            PROCESSED_ROOT / "review_queue.csv",
            (item for item in catalog if item["eligibility"] == "review"),
            CSV_FIELDS,
        )
        write_csv(
            PROCESSED_ROOT / "eligible_universe.csv",
            (item for item in catalog if item["eligibility"] == "eligible"),
            CSV_FIELDS,
        )

        report = generate_report(catalog, warnings, started)
        atomic_text(PROCESSED_ROOT / "universe_report.md", report)
        manifest = {
            "run_id": run_id,
            "started_at": json.loads(STATUS_PATH.read_text(encoding="utf-8")).get("started_at"),
            "completed_at": utc_now(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "classification_version": CLASSIFICATION_VERSION,
            "records": len(catalog),
            "eligibility": dict(Counter(item["eligibility"] for item in catalog)),
            "warnings": warnings,
            "source_counts": {"nasdaq": len(nasdaq), "yahoo": len(yahoo), "sec": len(sec)},
        }
        atomic_json(PROCESSED_ROOT / "run_manifest.json", manifest)

        final_phase = "completed_with_warnings" if warnings else "completed"
        update_status(
            final_phase,
            f"Catálogo terminado: {len(catalog)} productos/identidades.",
            completed_at=utc_now(),
            duration_seconds=manifest["duration_seconds"],
            records=len(catalog),
            eligibility=manifest["eligibility"],
            warnings=warnings,
        )
        export_results()
        return 0
    except Exception as error:
        logging.exception("Universe collection failed")
        update_status("failed", f"Error: {type(error).__name__}: {error}", failed_at=utc_now())
        return 1
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
