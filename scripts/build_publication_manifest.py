"""Build a deterministic checksum manifest for the public research edition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "artifacts/etf-universe/publication_manifest.json"
PUBLIC_ROOTS = (
    ROOT / "artifacts/etf-universe",
    ROOT / "assets/figures/etf-universe",
    ROOT / "notebooks",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def public_files() -> list[Path]:
    files: list[Path] = []
    for root in PUBLIC_ROOTS:
        files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(
        (path for path in files if path != MANIFEST_PATH),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def build_manifest() -> dict[str, object]:
    study = json.loads(
        (ROOT / "artifacts/etf-universe/study_summary.json").read_text(encoding="utf-8")
    )
    leverage = json.loads(
        (ROOT / "artifacts/etf-universe/leverage_summary.json").read_text(encoding="utf-8")
    )
    return {
        "edition": "0.2.1",
        "published_on": "2026-09-09",
        "data_close": study["curve_diagnostics"]["common_end"],
        "languages": ["en", "es"],
        "headline_counts": {
            "analytical_cohort": study["cohort_count"],
            "rwm_winners": study["rwm"]["beat_spy_count"],
            "rwm_and_cagr_winners": study["beat_spy_cagr_and_rwm"]["count"],
            "intentional_management": leverage["intentional_management_count"],
            "intentional_rwm_winners": leverage["intentional_beat_rwm"],
            "entry_robust_winners": leverage[
                "managed_winners_robust_in_majority_rolling_windows"
            ],
            "risk_efficient_candidates": leverage["risk_efficient_candidate_count"],
            "return_match_feasible_at_or_below_2x": leverage[
                "return_match_feasible_at_or_below_2x"
            ],
            "return_match_rwm_winners": leverage[
                "return_match_feasible_and_rwm_better"
            ],
        },
        "files": {
            path.relative_to(ROOT).as_posix(): sha256(path) for path in public_files()
        },
    }


if __name__ == "__main__":
    MANIFEST_PATH.write_text(
        json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(MANIFEST_PATH.relative_to(ROOT).as_posix())
