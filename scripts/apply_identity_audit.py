#!/usr/bin/env python3
"""Promote strong audit evidence to the curated identity override table."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from qinvia_etfs.universe import IDENTITY_OVERRIDE_FIELDS, IDENTITY_OVERRIDES_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = PROJECT_ROOT / "data" / "processed" / "universe" / "historical_identity_audit.csv"
VALIDATED_DECISIONS = {"validated_sec_operational", "validated_yahoo_history"}
NEVER_LAUNCHED_DECISIONS = {"never_launched_sec_statement"}
UNRESOLVED_DECISIONS = {
    "unresolved_listing_without_trading_evidence",
    "unresolved_no_trading_evidence",
}
ADRH_DIRECTORY = "https://adrhedged.com/directory/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=IDENTITY_OVERRIDES_PATH)
    parser.add_argument("--expected-records", type=int, default=114)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.audit.open("r", encoding="utf-8", newline="") as handle:
        audit = list(csv.DictReader(handle))
    if len(audit) != args.expected_records:
        raise RuntimeError(
            f"Audit incomplete: expected {args.expected_records}, found {len(audit)}"
        )

    existing: dict[str, dict[str, str]] = {}
    if args.output.exists():
        with args.output.open("r", encoding="utf-8", newline="") as handle:
            existing = {
                row["product_id"]: row
                for row in csv.DictReader(handle)
                if row.get("product_id")
            }

    promoted = 0
    for row in audit:
        decision = row.get("validation_decision", "")
        if decision not in VALIDATED_DECISIONS | NEVER_LAUNCHED_DECISIONS | UNRESOLVED_DECISIONS:
            continue
        evidence_url = row.get("sec_evidence_url", "")
        if decision == "validated_yahoo_history":
            evidence_url = f"https://finance.yahoo.com/quote/{row['ticker']}/history"
        evidence = decision
        note = row.get("validation_note", "")
        if decision in NEVER_LAUNCHED_DECISIONS:
            identity_status = "never_launched"
        elif decision in VALIDATED_DECISIONS:
            identity_status = "validated"
        elif "adrhedged" in row.get("name", "").lower():
            identity_status = "registered_not_trading"
            evidence = "issuer_directory_coming_soon"
            evidence_url = ADRH_DIRECTORY
            note = "El directorio del emisor lo identifica como Coming Soon y no disponible para negociación."
        else:
            identity_status = "registered_only_no_trading_evidence"
            evidence = "sec_registration_without_operational_or_yahoo_history"
            note = (
                "Consta la serie registral, pero no hay informe operativo, precio de Yahoo ni anuncio de lanzamiento; "
                "se conserva fuera de la descarga hasta que aparezca evidencia positiva."
            )
        existing[row["product_id"]] = {
            "product_id": row["product_id"],
            "identity_status": identity_status,
            "identity_evidence": evidence,
            "identity_evidence_url": evidence_url,
            "identity_validation_note": note,
            "validated_at": row.get("audited_at", ""),
        }
        promoted += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=IDENTITY_OVERRIDE_FIELDS)
        writer.writeheader()
        writer.writerows(existing[key] for key in sorted(existing))
    os.replace(temporary, args.output)
    print(f"Curated {promoted} identity decisions in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
