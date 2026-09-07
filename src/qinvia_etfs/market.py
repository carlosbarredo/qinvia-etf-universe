"""Download Yahoo daily market history to an immutable Parquet cache."""

from __future__ import annotations

import argparse
import csv
try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows
    fcntl = None
import hashlib
import json
import logging
import os
import random
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORK_ROOT = Path(os.environ.get("QINVIA_MARKET_WORK_ROOT", str(PROJECT_ROOT))).expanduser().resolve()
INPUT_PATH = Path(
    os.environ.get(
        "QINVIA_MARKET_UNIVERSE",
        str(PROJECT_ROOT / "data" / "processed" / "universe" / "eligible_universe.csv"),
    )
).expanduser().resolve()
STATUS_MIRROR_VALUE = os.environ.get("QINVIA_MARKET_STATUS_MIRROR", "").strip()
STATUS_MIRROR_PATH = Path(STATUS_MIRROR_VALUE).expanduser().resolve() if STATUS_MIRROR_VALUE else None

RAW_ROOT = WORK_ROOT / "data" / "raw" / "market" / "yahoo"
PRICE_ROOT = RAW_ROOT / "daily"
METADATA_ROOT = RAW_ROOT / "metadata"
MANIFEST_PATH = WORK_ROOT / "data" / "interim" / "market" / "download_manifest.csv"
RUNTIME_ROOT = WORK_ROOT / "runtime"
STATUS_PATH = RUNTIME_ROOT / "market_collector_status.json"
LOCK_PATH = RUNTIME_ROOT / "market_collector.lock"
LOG_PATH = RUNTIME_ROOT / "market_collector.log"

SCHEMA_VERSION = "yahoo_daily_1.0"
MANIFEST_FIELDS = [
    "request_symbol",
    "storage_key",
    "status",
    "rows",
    "first_date",
    "last_date",
    "file_bytes",
    "sha256",
    "duration_seconds",
    "attempts",
    "product_count",
    "current_identity_count",
    "historical_identity_count",
    "error_type",
    "error_message",
    "downloaded_at",
]
PRICE_COLUMNS = [
    "symbol",
    "session_date",
    "session_timestamp",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "capital_gains",
]


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
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    atomic_text(path, content)


def update_status(payload: dict[str, Any]) -> None:
    atomic_json(STATUS_PATH, payload)
    if STATUS_MIRROR_PATH and STATUS_MIRROR_PATH != STATUS_PATH:
        atomic_json(STATUS_MIRROR_PATH, payload)


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def valid_yahoo_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,11}", value))


def load_targets(path: Path = INPUT_PATH) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("eligibility") and row["eligibility"] != "eligible":
                continue
            symbol = str(row.get("ticker", "")).strip().upper()
            if not valid_yahoo_symbol(symbol):
                logging.warning("Skipping unsupported Yahoo symbol: %r", symbol)
                continue
            target = grouped.setdefault(
                symbol,
                {
                    "request_symbol": symbol.replace(".", "-"),
                    "catalog_symbol": symbol,
                    "product_ids": [],
                    "current_identity_count": 0,
                    "historical_identity_count": 0,
                    "first_seen_year": None,
                    "last_seen_year": None,
                },
            )
            target["product_ids"].append(row.get("product_id", ""))
            if as_bool(row.get("current_listing")):
                target["current_identity_count"] += 1
            else:
                target["historical_identity_count"] += 1
            for field, chooser in (("first_seen_year", min), ("last_seen_year", max)):
                raw = str(row.get(field, "")).strip()
                if not raw.isdigit():
                    continue
                year = int(raw)
                target[field] = year if target[field] is None else chooser(target[field], year)
    return list(grouped.values())


def evenly_spaced(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    indices = {round(index * (len(items) - 1) / (count - 1)) for index in range(count)}
    return [items[index] for index in sorted(indices)]


def order_targets(targets: list[dict[str, Any]], pilot_size: int = 100) -> list[dict[str, Any]]:
    """Put a deterministic, current/historical sample first, then the remainder."""
    by_symbol = {str(item["request_symbol"]): item for item in targets}
    spy = [by_symbol["SPY"]] if "SPY" in by_symbol else []
    remaining = [item for item in targets if item not in spy]
    current = sorted(
        (item for item in remaining if int(item["current_identity_count"]) > 0),
        key=lambda item: str(item["request_symbol"]),
    )
    historical = sorted(
        (item for item in remaining if int(item["current_identity_count"]) == 0),
        key=lambda item: (
            int(item["first_seen_year"] or 9999),
            str(item["request_symbol"]),
        ),
    )
    available = max(0, pilot_size - len(spy))
    historical_slots = min(len(historical), round(available * 0.40))
    current_slots = min(len(current), available - historical_slots)
    if current_slots + historical_slots < available:
        historical_slots = min(len(historical), available - current_slots)
    pilot = spy + evenly_spaced(current, current_slots) + evenly_spaced(historical, historical_slots)
    pilot_ids = {id(item) for item in pilot}
    tail = sorted(
        (item for item in targets if id(item) not in pilot_ids),
        key=lambda item: str(item["request_symbol"]),
    )
    return pilot + tail


def storage_key(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "_", symbol.upper()).strip("_") or "UNKNOWN"
    digest = hashlib.sha1(symbol.encode("utf-8")).hexdigest()[:8].upper()
    return f"{cleaned}_{digest}"


def paths_for(symbol: str) -> tuple[Path, Path]:
    key = storage_key(symbol)
    bucket = key[0]
    return PRICE_ROOT / bucket / f"{key}.parquet", METADATA_ROOT / bucket / f"{key}.json"


def normalize_history(frame: Any, symbol: str) -> Any:
    import pandas as pd

    if frame is None or frame.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [str(column[0]) for column in normalized.columns]
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
        "Dividends": "dividends",
        "Stock Splits": "stock_splits",
        "Capital Gains": "capital_gains",
    }
    normalized = normalized.rename(columns=rename)
    timestamps = pd.to_datetime(normalized.index)
    normalized.insert(0, "session_timestamp", timestamps)
    normalized.insert(0, "session_date", [value.date() for value in timestamps])
    normalized.insert(0, "symbol", symbol)
    for column in PRICE_COLUMNS:
        if column not in normalized:
            normalized[column] = pd.NA if column in {"adj_close", "capital_gains"} else 0.0
    numeric_columns = PRICE_COLUMNS[3:]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized[PRICE_COLUMNS].sort_values("session_date").reset_index(drop=True)
    if normalized["session_date"].duplicated().any():
        raise ValueError("Yahoo returned duplicate daily sessions")
    if normalized["close"].notna().sum() == 0:
        raise ValueError("Yahoo returned no valid close values")
    return normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_parquet(path: Path, frame: Any) -> tuple[int, str]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"qinvia_schema_version"] = SCHEMA_VERSION.encode("utf-8")
    table = table.replace_schema_metadata(metadata)
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=6,
        use_dictionary=["symbol"],
        write_statistics=True,
    )
    parquet_file = pq.ParquetFile(temporary)
    if parquet_file.metadata.num_rows != len(frame):
        temporary.unlink(missing_ok=True)
        raise OSError("Parquet row-count validation failed")
    os.replace(temporary, path)
    return path.stat().st_size, sha256_file(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reusable_result(target: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(target["request_symbol"])
    price_path, metadata_path = paths_for(symbol)
    metadata = read_json(metadata_path) if metadata_path.exists() else {}
    status = metadata.get("status")
    if status == "success" and price_path.exists() and price_path.stat().st_size > 100:
        return {**metadata, "status": "skipped_existing"}
    if status == "no_data":
        return {**metadata, "status": "skipped_no_data"}
    return None


def compact_source_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "currency",
        "symbol",
        "exchangeName",
        "fullExchangeName",
        "instrumentType",
        "firstTradeDate",
        "regularMarketTime",
        "gmtoffset",
        "timezone",
        "exchangeTimezoneName",
        "dataGranularity",
        "priceHint",
    )
    return {key: metadata.get(key) for key in keep if metadata.get(key) is not None}


def download_one(target: dict[str, Any], max_attempts: int = 3) -> dict[str, Any]:
    import yfinance as yf
    from yfinance.exceptions import (
        YFInvalidPeriodError,
        YFPricesMissingError,
        YFRateLimitError,
        YFTickerMissingError,
        YFTzMissingError,
    )

    try:
        yf.config.debug.hide_exceptions = False
    except AttributeError:
        pass
    symbol = str(target["request_symbol"])
    price_path, metadata_path = paths_for(symbol)
    previous = read_json(metadata_path)
    prior_attempts = int(previous.get("attempts", 0) or 0)
    started = time.monotonic()
    last_error: Exception | None = None

    for local_attempt in range(1, max_attempts + 1):
        try:
            ticker = yf.Ticker(symbol)
            query_period = "max"
            query_method = "Ticker.history"
            source_metadata: dict[str, Any] = {}
            try:
                history = ticker.history(
                    period=query_period,
                    interval="1d",
                    auto_adjust=False,
                    actions=True,
                    repair=False,
                    timeout=45,
                )
                source_metadata = compact_source_metadata(
                    dict(getattr(ticker, "history_metadata", {}) or {})
                )
            except YFInvalidPeriodError:
                # Newly listed funds occasionally advertise only short ranges.
                # Five days is the longest common fallback and avoids discarding
                # an otherwise valid identity while Yahoo builds its history.
                query_period = "5d"
                history = ticker.history(
                    period=query_period,
                    interval="1d",
                    auto_adjust=False,
                    actions=True,
                    repair=False,
                    timeout=45,
                )
                source_metadata = compact_source_metadata(
                    dict(getattr(ticker, "history_metadata", {}) or {})
                )
            except KeyError as error:
                if error.args != ("tradingPeriods",):
                    raise
                # Some valid symbols have price data but malformed chart
                # metadata. The batch endpoint reads the same Yahoo bars while
                # avoiding that metadata field.
                query_method = "yf.download_fallback"
                history = yf.download(
                    symbol,
                    period=query_period,
                    interval="1d",
                    auto_adjust=False,
                    actions=True,
                    repair=False,
                    progress=False,
                    threads=False,
                    timeout=45,
                )
            normalized = normalize_history(history, symbol)
            downloaded_at = utc_now()
            attempts = prior_attempts + local_attempt
            if normalized.empty:
                result = {
                    "request_symbol": symbol,
                    "storage_key": storage_key(symbol),
                    "status": "no_data",
                    "rows": 0,
                    "first_date": "",
                    "last_date": "",
                    "file_bytes": 0,
                    "sha256": "",
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "attempts": attempts,
                    "error_type": "",
                    "error_message": "Yahoo returned an empty history",
                    "downloaded_at": downloaded_at,
                    "source_metadata": source_metadata,
                    "schema_version": SCHEMA_VERSION,
                }
                atomic_json(metadata_path, result)
                return result
            file_bytes, checksum = write_parquet(price_path, normalized)
            result = {
                "request_symbol": symbol,
                "catalog_symbol": target["catalog_symbol"],
                "storage_key": storage_key(symbol),
                "status": "success",
                "rows": len(normalized),
                "first_date": str(normalized["session_date"].iloc[0]),
                "last_date": str(normalized["session_date"].iloc[-1]),
                "file_bytes": file_bytes,
                "sha256": checksum,
                "duration_seconds": round(time.monotonic() - started, 3),
                "attempts": attempts,
                "error_type": "",
                "error_message": "",
                "downloaded_at": downloaded_at,
                "source_metadata": source_metadata,
                "schema_version": SCHEMA_VERSION,
                "query": {
                    "method": query_method,
                    "period": query_period,
                    "interval": "1d",
                    "auto_adjust": False,
                    "actions": True,
                    "repair": False,
                },
            }
            atomic_json(metadata_path, result)
            return result
        except (YFPricesMissingError, YFTzMissingError, YFTickerMissingError) as error:
            # These are Yahoo's terminal responses for delisted/missing symbols.
            # Retrying them immediately only adds several seconds per dead fund.
            result = {
                "request_symbol": symbol,
                "storage_key": storage_key(symbol),
                "status": "no_data",
                "rows": 0,
                "first_date": "",
                "last_date": "",
                "file_bytes": 0,
                "sha256": "",
                "duration_seconds": round(time.monotonic() - started, 3),
                "attempts": prior_attempts + local_attempt,
                "error_type": type(error).__name__,
                "error_message": str(error)[:1000],
                "downloaded_at": utc_now(),
                "schema_version": SCHEMA_VERSION,
            }
            atomic_json(metadata_path, result)
            logging.info("%s has no Yahoo history: %s", symbol, error)
            return result
        except YFRateLimitError as error:
            last_error = error
            logging.warning("%s rate limited on attempt %s/%s", symbol, local_attempt, max_attempts)
            if local_attempt < max_attempts:
                time.sleep(45 + random.random())
        except Exception as error:  # yfinance exposes several backend-specific errors.
            last_error = error
            logging.warning(
                "%s attempt %s/%s failed: %s: %s",
                symbol,
                local_attempt,
                max_attempts,
                type(error).__name__,
                error,
            )
            if local_attempt < max_attempts:
                error_text = str(error).lower()
                cooldown = 45 if "rate" in error_text or "too many" in error_text else min(20, 2**local_attempt)
                time.sleep(cooldown + random.random())

    result = {
        "request_symbol": symbol,
        "storage_key": storage_key(symbol),
        "status": "error",
        "rows": 0,
        "first_date": "",
        "last_date": "",
        "file_bytes": 0,
        "sha256": "",
        "duration_seconds": round(time.monotonic() - started, 3),
        "attempts": prior_attempts + max_attempts,
        "error_type": type(last_error).__name__ if last_error else "UnknownError",
        "error_message": str(last_error or "Unknown error")[:1000],
        "downloaded_at": utc_now(),
        "schema_version": SCHEMA_VERSION,
    }
    atomic_json(metadata_path, result)
    return result


def manifest_row(result: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return {
        field: result.get(field, "")
        for field in MANIFEST_FIELDS
    } | {
        "product_count": len(target["product_ids"]),
        "current_identity_count": target["current_identity_count"],
        "historical_identity_count": target["historical_identity_count"],
    }


def write_manifest(rows: Iterable[dict[str, Any]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(MANIFEST_PATH.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, MANIFEST_PATH)


def projected_completion(
    elapsed: float,
    completed: int,
    total: int,
    request_durations: list[float],
    delay: float,
) -> tuple[float, str]:
    if not request_durations:
        return 0.0, ""
    seconds_per_fresh_symbol = statistics.mean(request_durations) + max(0.0, delay)
    remaining_seconds = max(0, total - completed) * seconds_per_fresh_symbol
    total_seconds = elapsed + remaining_seconds
    completion = datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
    return total_seconds, completion.isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_PATH.open("w", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logging.error("Another market collector is already running")
            return 2

    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        targets = order_targets(load_targets(INPUT_PATH), max(1, args.pilot_size))
        if args.limit > 0:
            targets = targets[: args.limit]
        total = len(targets)
        counts: Counter[str] = Counter()
        rows_total = 0
        bytes_total = 0
        request_durations: list[float] = []
        manifest: list[dict[str, Any]] = []
        pilot_summary: dict[str, Any] = {}
        update_status(
            {
                "phase": "starting",
                "message": "Preparando descarga histórica diaria de Yahoo.",
                "run_id": run_id,
                "pid": os.getpid(),
                "started_at": started_at.isoformat(timespec="seconds"),
                "total_symbols": total,
                "pilot_size": min(args.pilot_size, total),
                "work_root": str(WORK_ROOT),
                "input_path": str(INPUT_PATH),
            }
        )

        for position, target in enumerate(targets, start=1):
            reusable = reusable_result(target)
            result = reusable if reusable is not None else download_one(target, args.max_attempts)
            status = str(result["status"])
            counts[status] += 1
            if reusable is None:
                request_durations.append(float(result.get("duration_seconds", 0) or 0))
            rows_total += int(result.get("rows", 0) or 0)
            bytes_total += int(result.get("file_bytes", 0) or 0)
            manifest.append(manifest_row(result, target))
            write_manifest(manifest)

            elapsed = time.monotonic() - started_monotonic
            projected_seconds, projected_at = projected_completion(
                elapsed, position, total, request_durations, args.delay
            )
            if not pilot_summary and len(request_durations) >= min(args.pilot_size, total):
                pilot_summary = {
                    "completed_at": utc_now(),
                    "symbols": position,
                    "fresh_requests": len(request_durations),
                    "elapsed_seconds": round(elapsed, 3),
                    "median_request_seconds": round(statistics.median(request_durations), 3) if request_durations else 0,
                    "projected_total_seconds": round(projected_seconds, 3),
                    "projected_completion_at": projected_at,
                    "counts": dict(counts),
                    "rows": rows_total,
                    "bytes": bytes_total,
                }
                logging.info("Pilot completed: %s", pilot_summary)

            payload = {
                "phase": "downloading",
                "message": f"Descargados o resueltos {position} de {total} símbolos.",
                "run_id": run_id,
                "pid": os.getpid(),
                "started_at": started_at.isoformat(timespec="seconds"),
                "updated_at": utc_now(),
                "total_symbols": total,
                "completed_symbols": position,
                "current_symbol": target["request_symbol"],
                "counts": dict(counts),
                "rows": rows_total,
                "bytes": bytes_total,
                "elapsed_seconds": round(elapsed, 3),
                "projected_total_seconds": round(projected_seconds, 3),
                "projected_completion_at": projected_at,
                "median_request_seconds": round(statistics.median(request_durations), 3) if request_durations else 0,
                "mean_request_seconds": round(statistics.mean(request_durations), 3) if request_durations else 0,
                "fresh_requests": len(request_durations),
                "pilot": pilot_summary,
                "work_root": str(WORK_ROOT),
            }
            update_status(payload)
            if reusable is None and position < total:
                time.sleep(max(0.0, args.delay))

        elapsed = time.monotonic() - started_monotonic
        failures = counts.get("error", 0)
        final_phase = "completed_with_errors" if failures else "completed"
        update_status(
            {
                "phase": final_phase,
                "message": f"Descarga terminada: {total} símbolos resueltos.",
                "run_id": run_id,
                "pid": os.getpid(),
                "started_at": started_at.isoformat(timespec="seconds"),
                "completed_at": utc_now(),
                "total_symbols": total,
                "completed_symbols": total,
                "counts": dict(counts),
                "rows": rows_total,
                "bytes": bytes_total,
                "elapsed_seconds": round(elapsed, 3),
                "pilot": pilot_summary,
                "work_root": str(WORK_ROOT),
            }
        )
        logging.info("Market collection completed in %.1fs: %s", elapsed, dict(counts))
        return 1 if failures else 0
    except Exception as error:
        logging.exception("Market collection failed")
        update_status(
            {
                "phase": "failed",
                "message": f"{type(error).__name__}: {error}",
                "failed_at": utc_now(),
                "work_root": str(WORK_ROOT),
            }
        )
        return 1
    finally:
        if fcntl is not None:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
