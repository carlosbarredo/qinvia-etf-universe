#!/usr/bin/env python3
"""Reapply classification rules to the existing metadata catalog without downloading data."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter

from qinvia_etfs.universe import (
    CLASSIFICATION_VERSION,
    CSV_FIELDS,
    INTERIM_ROOT,
    PROCESSED_ROOT,
    atomic_json,
    atomic_text,
    apply_identity_overrides,
    classify,
    generate_report,
    utc_now,
    write_csv,
)


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def main() -> int:
    started = time.monotonic()
    catalog_path = INTERIM_ROOT / "catalog.csv"
    with catalog_path.open("r", encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))

    for record in records:
        record["current_listing"] = as_bool(record.get("current_listing"))

    apply_identity_overrides(records)
    catalog = [classify(record) for record in records]
    catalog.sort(key=lambda item: (str(item["ticker"]), str(item["product_id"])))

    write_csv(catalog_path, catalog, CSV_FIELDS)
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
    atomic_text(PROCESSED_ROOT / "universe_report.md", generate_report(catalog, [], started))

    manifest_path = PROCESSED_ROOT / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.update(
        {
            "classification_version": CLASSIFICATION_VERSION,
            "records": len(catalog),
            "eligibility": dict(Counter(item["eligibility"] for item in catalog)),
            "reclassified_at": utc_now(),
        }
    )
    atomic_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "classification_version": CLASSIFICATION_VERSION,
                "records": len(catalog),
                "eligibility": manifest["eligibility"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
