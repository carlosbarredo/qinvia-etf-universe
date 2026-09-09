#!/usr/bin/env python3
"""Audit management style for every product in study 1A.

SEC Form N-CEN C.3 is the primary evidence.  The filing answers whether a
registered fund is an index fund; a negative answer is deliberately not
translated into discretionary active management without additional evidence.
Products outside the N-CEN population are covered by the sourced override
ledger in ``docs/evidence/management_style_overrides.csv``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from qinvia_etfs.management_style import (  # noqa: E402
    MANAGEMENT_EVIDENCE_VERSION,
    VALID_MANAGEMENT_STYLES,
    choose_ncen_evidence,
    find_management_override,
    infer_non_index_style,
    load_management_overrides,
    load_ncen_evidence,
    name_similarity,
    normalize_ticker,
)
from qinvia_etfs.universe_study import (  # noqa: E402
    DEFAULT_CUTOFF,
    mark_economic_aliases,
    select_cohort,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def series_candidates(catalog: pd.DataFrame) -> dict[str, list[tuple[str, str]]]:
    """Return all SEC series/name pairs reported for each normalized ticker."""

    output: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in catalog.itertuples(index=False):
        ticker = normalize_ticker(getattr(row, "ticker", ""))
        series_id = str(getattr(row, "sec_series_id", "") or "").strip()
        name = str(getattr(row, "name", "") or "").strip()
        if ticker and series_id and series_id.lower() != "nan":
            output[ticker].append((series_id, name))
    return output


def relevant_series_ids(
    *, ticker: str, product_name: str, lookup: dict[str, list[tuple[str, str]]]
) -> list[str]:
    """Select name-consistent legal series and suppress ticker-reuse aliases."""

    pairs = lookup.get(normalize_ticker(ticker), [])
    scored = [(series_id, name_similarity(product_name, name)) for series_id, name in pairs]
    if not scored:
        return []
    best = max(score for _, score in scored)
    if best < 0.55:
        return []
    return sorted({series_id for series_id, score in scored if score >= max(0.55, best - 0.05)})


def classify(
    *,
    selected: pd.DataFrame,
    catalog: pd.DataFrame,
    ncen_rows: list,
    overrides: list[dict[str, str]],
) -> pd.DataFrame:
    lookup = series_candidates(catalog)
    records: list[dict[str, object]] = []
    for row in selected.itertuples(index=False):
        ticker = normalize_ticker(row.request_symbol)
        ids = relevant_series_ids(ticker=ticker, product_name=row.name, lookup=lookup)
        override = find_management_override(overrides, ticker=ticker, series_ids=ids)
        base = {
            "request_symbol": ticker,
            "name": row.name,
            "previous_management_style": row.management_style,
            "management_evidence_version": MANAGEMENT_EVIDENCE_VERSION,
            "matched_catalog_series_ids": "|".join(ids),
        }
        if override:
            records.append(
                {
                    **base,
                    "management_style": override["management_style"],
                    "management_confidence": override["management_confidence"],
                    "management_source": "primary_source_override",
                    "evidence": override["evidence"],
                    "source_url": override["source_url"],
                    "source_zip": "",
                    "ncen_accession_number": "",
                    "ncen_series_id": "",
                    "ncen_fund_name": "",
                    "ncen_is_etf": "",
                    "ncen_is_index": "",
                    "ncen_match_route": "manual_ticker_override",
                    "identity_name_similarity": "",
                    "review_note": override["review_note"],
                }
            )
            continue

        evidence, route = choose_ncen_evidence(
            ncen_rows,
            ticker=ticker,
            product_name=row.name,
            series_ids=ids,
        )
        if evidence is None:
            raise RuntimeError(f"No N-CEN evidence or sourced override for {ticker}: {row.name}")
        if evidence.is_etf != "Y":
            raise RuntimeError(
                f"Selected N-CEN row does not affirm ETF status for {ticker}: "
                f"{evidence.accession_number}"
            )
        if evidence.is_index == "Y":
            style = "index_passive_identified"
            confidence = "high"
            rationale = "SEC N-CEN C.3 identifies the series as an index fund"
        else:
            style, inference = infer_non_index_style(row.name)
            confidence = "medium" if style != "non_index_management_identified" else "high"
            if style == "non_index_management_identified":
                rationale = (
                    "SEC N-CEN C.3 does not identify the series as an index fund; "
                    "the filing alone does not distinguish discretionary from rules-based management"
                )
            else:
                rationale = (
                    "SEC N-CEN C.3 does not identify the series as an index fund; "
                    f"classification refined by transparent product-name evidence ({inference})"
                )
        records.append(
            {
                **base,
                "management_style": style,
                "management_confidence": confidence,
                "management_source": "sec_ncen_c3",
                "evidence": rationale,
                "source_url": evidence.source_url,
                "source_zip": evidence.source_zip,
                "ncen_accession_number": evidence.accession_number,
                "ncen_series_id": evidence.series_id,
                "ncen_fund_name": evidence.fund_name,
                "ncen_is_etf": evidence.is_etf,
                "ncen_is_index": evidence.is_index,
                "ncen_match_route": route,
                "identity_name_similarity": name_similarity(row.name, evidence.fund_name),
                "review_note": "",
            }
        )
    return pd.DataFrame(records).sort_values("request_symbol").reset_index(drop=True)


def validate(selected: pd.DataFrame, audit: pd.DataFrame) -> None:
    if len(audit) != len(selected):
        raise AssertionError(f"Expected {len(selected)} decisions; generated {len(audit)}")
    if audit["request_symbol"].duplicated().any():
        raise AssertionError("Audit contains duplicate request symbols")
    if set(audit["request_symbol"]) != set(selected["request_symbol"].map(normalize_ticker)):
        raise AssertionError("Audit does not cover exactly the complete study cohort")
    if audit["management_style"].isin({"", "not_determined"}).any():
        raise AssertionError("Audit left an undetermined management style")
    invalid_styles = set(audit["management_style"]).difference(VALID_MANAGEMENT_STYLES)
    if invalid_styles:
        raise AssertionError(f"Audit contains invalid management styles: {sorted(invalid_styles)}")
    if audit[["management_confidence", "evidence", "source_url"]].isna().any().any():
        raise AssertionError("Audit contains missing evidence fields")
    if not audit["source_url"].str.startswith("https://").all():
        raise AssertionError("Every audit decision must have an HTTPS evidence URL")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selected",
        type=Path,
        help="Optional pre-audit canonical cohort; normally rebuilt from --benchmark",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("data/processed/market/benchmark_vs_spy.parquet"),
    )
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("data/interim/universe/catalog.csv"),
    )
    parser.add_argument(
        "--ncen-root",
        type=Path,
        default=Path("data/external/sec/ncen"),
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("docs/evidence/management_style_overrides.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/studies/etf_universe_1A/management_style_audit.csv"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("data/processed/studies/etf_universe_1A/management_style_audit_summary.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selected is not None:
        selected = pd.read_csv(args.selected)
    else:
        benchmark = pd.read_parquet(args.benchmark)
        qualifying = mark_economic_aliases(select_cohort(benchmark, args.cutoff))
        selected = qualifying[qualifying["analysis_primary"]].copy().reset_index(drop=True)
    previously_not_determined = int(selected["management_style"].eq("not_determined").sum())
    catalog = pd.read_csv(args.catalog, low_memory=False)
    ncen_paths = sorted(args.ncen_root.glob("*_ncen.zip"))
    if not ncen_paths:
        raise FileNotFoundError(f"No N-CEN ZIP files under {args.ncen_root}")
    ncen_rows = load_ncen_evidence(ncen_paths)
    overrides = load_management_overrides(args.overrides)
    audit = classify(
        selected=selected,
        catalog=catalog,
        ncen_rows=ncen_rows,
        overrides=overrides,
    )
    audit["changed_from_previous"] = audit["management_style"].ne(
        audit["previous_management_style"]
    )
    validate(selected, audit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output, index=False)
    transitions = (
        audit[audit["changed_from_previous"]]
        .groupby(["previous_management_style", "management_style"])
        .size()
        .sort_values(ascending=False)
    )
    summary = {
        "management_evidence_version": MANAGEMENT_EVIDENCE_VERSION,
        "generated_at": utc_now(),
        "input_rows": int(len(selected)),
        "previously_not_determined": previously_not_determined,
        "resolved_rows": int(len(audit)),
        "remaining_not_determined": int(audit["management_style"].eq("not_determined").sum()),
        "ncen_zip_count": len(ncen_paths),
        "ncen_zip_files": [path.name for path in ncen_paths],
        "counts_by_style": audit["management_style"].value_counts().sort_index().to_dict(),
        "counts_by_source": audit["management_source"].value_counts().sort_index().to_dict(),
        "counts_by_confidence": audit["management_confidence"].value_counts().sort_index().to_dict(),
        "previous_counts_by_style": selected["management_style"].value_counts().sort_index().to_dict(),
        "changed_from_previous": int(
            audit["management_style"].ne(audit["previous_management_style"]).sum()
        ),
        "changed_previously_assigned": int(
            (
                audit["management_style"].ne(audit["previous_management_style"])
                & audit["previous_management_style"].ne("not_determined")
            ).sum()
        ),
        "changed_transitions": {
            f"{previous} -> {current}": int(count)
            for (previous, current), count in transitions.items()
        },
        "manual_override_rows": int(audit["management_source"].eq("primary_source_override").sum()),
        "identity_or_method_review_rows": int(audit["review_note"].fillna("").ne("").sum()),
        "output": str(args.output),
        "override_ledger": str(args.overrides),
        "semantics": {
            "ncen_index_yes": "index_passive_identified",
            "ncen_index_negative": (
                "non-index status only; active versus rules-based is not inferred without evidence"
            ),
            "static_exposure_or_trust": (
                "physical, currency, grantor and single-asset trusts without portfolio management"
            ),
            "not_applicable_security": (
                "ETNs and other non-ETF securities for which ETF management style is not applicable"
            ),
            "mixed_or_changed_mandate": (
                "the downloaded history spans materially different passive/index and active mandates; "
                "it must not be attributed wholesale to either cohort"
            ),
        },
    }
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
