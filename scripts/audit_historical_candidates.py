#!/usr/bin/env python3
"""Validate historical ETF candidates with free SEC and Yahoo evidence.

The audit is deliberately conservative: registration/prospectus filings alone do
not prove that a fund traded.  A candidate is auto-validated only when an
operational/listing filing names it or Yahoo returns prices in the SEC-observed
time window with a compatible identity.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW = PROJECT_ROOT / "data" / "processed" / "universe" / "review_queue.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "universe" / "historical_identity_audit.csv"
DEFAULT_STATUS = PROJECT_ROOT / "runtime" / "historical_identity_status.json"
DEFAULT_CACHE = Path(
    os.environ.get(
        "QINVIA_VALIDATION_CACHE_ROOT",
        str(PROJECT_ROOT / "data" / "raw" / "universe" / "validation"),
    )
).expanduser()
USER_AGENT = os.environ.get(
    "QINVIA_USER_AGENT",
    "QinviaETFResearch/0.1 local-noncommercial-research research-contact@example.invalid",
)
OPERATIONAL_FORMS = (
    "N-CEN,NPORT-P,N-Q,N-CSR,N-CSRS,NSAR-A,NSAR-B,N-30D,N-30B-2,"
    "8-A12B,25-NSE"
)
REPORT_FORMS = {
    "N-CEN",
    "NPORT-P",
    "N-Q",
    "N-CSR",
    "N-CSRS",
    "NSAR-A",
    "NSAR-B",
    "N-30D",
    "N-30B-2",
}
LISTING_FORMS = {"8-A12B", "25-NSE"}
AUDIT_FIELDS = [
    "product_id",
    "ticker",
    "name",
    "first_seen_year",
    "last_seen_year",
    "sec_series_id",
    "sec_class_id",
    "sec_result",
    "sec_form",
    "sec_filing_date",
    "sec_evidence_url",
    "sec_hit_count",
    "yahoo_result",
    "yahoo_first_price_date",
    "yahoo_last_price_date",
    "yahoo_chart_name",
    "yahoo_instrument_type",
    "yahoo_name_similarity",
    "validation_decision",
    "validation_note",
    "audited_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_audit(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def get_json(url: str, cache_path: Path, attempts: int = 5) -> dict[str, Any]:
    if cache_path.exists() and cache_path.stat().st_size > 20:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        request = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            atomic_json(cache_path, payload)
            return payload
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == attempts:
                raise
        except (URLError, TimeoutError, json.JSONDecodeError):
            if attempt == attempts:
                raise
        time.sleep(min(60, 3 * (2 ** (attempt - 1))))
    raise RuntimeError(f"No response from {url}")


def get_text(url: str, cache_path: Path, attempts: int = 5) -> str:
    if cache_path.exists() and cache_path.stat().st_size > 20:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
        try:
            with urlopen(request, timeout=45) as response:
                content = response.read().decode("utf-8", errors="replace")
            temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, cache_path)
            return content
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == attempts:
                raise
        except (URLError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(min(60, 3 * (2 ** (attempt - 1))))
    raise RuntimeError(f"No response from {url}")


def cleaned_name(value: str) -> str:
    value = re.sub(r"\((?:tm|sm)\)", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def normalized_tokens(value: str) -> set[str]:
    stop = {
        "the",
        "and",
        "fund",
        "portfolio",
        "etf",
        "shares",
        "index",
        "strategy",
        "trust",
        "tm",
        "sm",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in stop
    }


def name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_clean = " ".join(sorted(normalized_tokens(left)))
    right_clean = " ".join(sorted(normalized_tokens(right)))
    if not left_clean or not right_clean:
        return 0.0
    left_tokens = set(left_clean.split())
    right_tokens = set(right_clean.split())
    jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence = SequenceMatcher(None, left_clean, right_clean).ratio()
    return max(jaccard, sequence)


def filing_url(hit: dict[str, Any]) -> str:
    source = hit.get("_source", {})
    hit_id = str(hit.get("_id", ""))
    if ":" not in hit_id:
        return ""
    accession, filename = hit_id.split(":", 1)
    ciks = source.get("ciks") or []
    if not ciks:
        return ""
    cik = str(ciks[0]).lstrip("0") or "0"
    accession_compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_compact}/{filename}"


def normalized_plain_text(content: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", content)
    decoded = html.unescape(without_tags)
    return re.sub(r"[^a-z0-9]+", " ", decoded.lower()).strip()


def explicit_non_launch_statement(content: str, product_name: str) -> bool:
    plain = normalized_plain_text(content)
    name_plain = normalized_plain_text(cleaned_name(product_name))
    positions: list[int] = []
    start = 0
    while name_plain and (position := plain.find(name_plain, start)) >= 0:
        positions.append(position)
        start = position + len(name_plain)
    if not positions:
        return False
    negative_patterns = (
        r"(?:has|have|had|funds)? ?not commenced operations",
        r"not offered shares to the public",
        r"no operations to date other than",
        r"not yet registered with the sec",
        r"will not commence operations",
    )
    for position in positions:
        window = plain[max(0, position - 2500) : position + len(name_plain) + 2500]
        if any(re.search(pattern, window) for pattern in negative_patterns):
            return True
    return False


def audit_sec(record: dict[str, str], cache_root: Path) -> dict[str, Any]:
    query_name = cleaned_name(record["name"])
    parameters = urlencode(
        {
            "q": f'"{query_name}"',
            "forms": OPERATIONAL_FORMS,
            "from": 0,
            "size": 25,
        }
    )
    url = f"https://efts.sec.gov/LATEST/search-index?{parameters}"
    payload = get_json(
        url,
        cache_root / "sec_efts" / f"{record['product_id']}.json",
    )
    hits_block = payload.get("hits", {})
    hits = hits_block.get("hits", []) if isinstance(hits_block, dict) else []
    total_block = hits_block.get("total", {}) if isinstance(hits_block, dict) else {}
    total = int(total_block.get("value", 0) if isinstance(total_block, dict) else total_block or 0)
    if not hits:
        return {"sec_result": "no_operational_filing", "sec_hit_count": total}

    def rank(hit: dict[str, Any]) -> tuple[int, str]:
        form = str(hit.get("_source", {}).get("form", ""))
        strongest = {
            "N-CEN": 0,
            "NPORT-P": 1,
            "N-Q": 2,
            "N-CSR": 3,
            "N-CSRS": 4,
            "NSAR-A": 5,
            "NSAR-B": 6,
            "N-30D": 7,
            "N-30B-2": 8,
            "25-NSE": 20,
            "8-A12B": 21,
        }
        return strongest.get(form, 20), str(hit.get("_source", {}).get("file_date", ""))

    selected = sorted(hits, key=rank)[0]
    source = selected.get("_source", {})
    form = str(source.get("form", ""))
    evidence_url = filing_url(selected)
    if form in REPORT_FORMS and evidence_url:
        document = get_text(
            evidence_url,
            cache_root / "sec_filings" / f"{record['product_id']}.html",
        )
        if explicit_non_launch_statement(document, record["name"]):
            return {
                "sec_result": "explicit_never_launched_statement",
                "sec_form": form,
                "sec_filing_date": source.get("file_date", ""),
                "sec_evidence_url": evidence_url,
                "sec_hit_count": total,
            }
    result = "operational_filing_found" if form in REPORT_FORMS else "listing_filing_only"
    return {
        "sec_result": result,
        "sec_form": form,
        "sec_filing_date": source.get("file_date", ""),
        "sec_evidence_url": evidence_url,
        "sec_hit_count": total,
    }


def audit_yahoo(record: dict[str, str], cache_root: Path) -> dict[str, Any]:
    first_year = int(record["first_seen_year"] or 1970)
    last_year = int(record["last_seen_year"] or first_year)
    period1 = int(datetime(first_year - 1, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime(last_year + 2, 1, 1, tzinfo=timezone.utc).timestamp())
    ticker = record["ticker"]
    parameters = urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1mo",
            "events": "history",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?{parameters}"
    try:
        payload = get_json(
            url,
            cache_root / "yahoo_chart" / f"{record['product_id']}.json",
            attempts=4,
        )
    except HTTPError as error:
        return {"yahoo_result": f"http_{error.code}"}
    except (URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as error:
        return {"yahoo_result": f"request_error:{type(error).__name__}"}

    chart = payload.get("chart", {})
    error = chart.get("error") if isinstance(chart, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if error or not results:
        code = error.get("code", "no_data") if isinstance(error, dict) else "no_data"
        return {"yahoo_result": str(code)}

    result = results[0]
    meta = result.get("meta", {})
    timestamps = [int(value) for value in result.get("timestamp", []) if value]
    chart_name = str(meta.get("longName") or meta.get("shortName") or "")
    similarity = name_similarity(record["name"], chart_name)
    output: dict[str, Any] = {
        "yahoo_result": "prices_found" if timestamps else "no_prices",
        "yahoo_chart_name": chart_name,
        "yahoo_instrument_type": str(meta.get("instrumentType") or ""),
        "yahoo_name_similarity": f"{similarity:.3f}",
    }
    if timestamps:
        output["yahoo_first_price_date"] = datetime.fromtimestamp(
            min(timestamps), timezone.utc
        ).date().isoformat()
        output["yahoo_last_price_date"] = datetime.fromtimestamp(
            max(timestamps), timezone.utc
        ).date().isoformat()
    return output


def decide(row: dict[str, Any]) -> tuple[str, str]:
    if row.get("sec_result") == "explicit_never_launched_statement":
        return (
            "never_launched_sec_statement",
            "Un informe oficial de la SEC indica expresamente que el fondo no había comenzado operaciones.",
        )
    if row.get("sec_result") == "operational_filing_found":
        return (
            "validated_sec_operational",
            f"El formulario SEC {row.get('sec_form', '')} aporta evidencia operativa o de cotización.",
        )
    similarity = float(row.get("yahoo_name_similarity") or 0)
    instrument = str(row.get("yahoo_instrument_type") or "").upper()
    if row.get("yahoo_result") == "prices_found" and similarity >= 0.45 and instrument in {
        "ETF",
        "MUTUALFUND",
    }:
        return (
            "validated_yahoo_history",
            "Yahoo conserva precios en la ventana histórica y el nombre es compatible.",
        )
    if row.get("yahoo_result") == "prices_found":
        return (
            "possible_ticker_reuse",
            "Hay precios para el símbolo, pero la identidad no coincide con suficiente confianza.",
        )
    if row.get("sec_result") == "listing_filing_only":
        return (
            "unresolved_listing_without_trading_evidence",
            "Existe un formulario de alta o baja registral, pero no prueba de primera negociación.",
        )
    return (
        "unresolved_no_trading_evidence",
        "Solo consta el registro de la serie; no se encontró todavía evidencia de negociación.",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--delay", type=float, default=0.35)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.review.open("r", encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))

    completed: list[dict[str, Any]] = []
    atomic_json(
        args.status,
        {
            "phase": "running",
            "total": len(candidates),
            "completed": 0,
            "started_at": utc_now(),
        },
    )

    try:
        for position, candidate in enumerate(candidates, start=1):
            row: dict[str, Any] = {field: candidate.get(field, "") for field in AUDIT_FIELDS}
            try:
                row.update(audit_sec(candidate, args.cache_root))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as error:
                row["sec_result"] = f"request_error:{type(error).__name__}"
            time.sleep(args.delay)
            row.update(audit_yahoo(candidate, args.cache_root))
            decision, note = decide(row)
            row["validation_decision"] = decision
            row["validation_note"] = note
            row["audited_at"] = utc_now()
            completed.append(row)
            write_audit(args.output, completed)
            atomic_json(
                args.status,
                {
                    "phase": "running",
                    "total": len(candidates),
                    "completed": position,
                    "current_ticker": candidate["ticker"],
                    "updated_at": utc_now(),
                },
            )
            time.sleep(args.delay)
    except Exception as error:
        atomic_json(
            args.status,
            {
                "phase": "failed",
                "total": len(candidates),
                "completed": len(completed),
                "error": f"{type(error).__name__}: {error}",
                "updated_at": utc_now(),
            },
        )
        raise

    counts: dict[str, int] = {}
    for row in completed:
        decision = str(row["validation_decision"])
        counts[decision] = counts.get(decision, 0) + 1
    atomic_json(
        args.status,
        {
            "phase": "completed",
            "total": len(candidates),
            "completed": len(completed),
            "decisions": counts,
            "completed_at": utc_now(),
        },
    )
    print(json.dumps({"records": len(completed), "decisions": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
