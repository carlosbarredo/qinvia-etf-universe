import hashlib
import json
from pathlib import Path
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/etf-universe"
FIGURES = ROOT / "assets/figures/etf-universe"
NOTEBOOKS = {
    "en": ROOT / "notebooks/etf_universe_en.ipynb",
    "es": ROOT / "notebooks/etf_universe_es.ipynb",
}
FIGURE_NAMES = {
    "universe-funnel.png",
    "inception-distribution.png",
    "evidence-buckets.png",
    "management-scorecard.png",
    "management-base-rates.png",
    "leverage-grid.png",
    "return-matched-equity.png",
    "return-matching-sensitivity.png",
    "entry-point-robustness.png",
    "rwm-cagr-scatter.png",
    "universe-fan.png",
    "common-period-curve.png",
}


def _cell_source(cell: dict[str, object]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repository_contains_no_html_publication() -> None:
    assert not list(ROOT.rglob("*.html"))


def test_bilingual_notebooks_are_executed_and_self_consistent() -> None:
    for notebook in NOTEBOOKS.values():
        payload = json.loads(notebook.read_text(encoding="utf-8"))
        code_cells = [cell for cell in payload["cells"] if cell["cell_type"] == "code"]
        assert code_cells
        assert all(cell.get("execution_count") is not None for cell in code_cells)

        source = "\n".join(_cell_source(cell) for cell in payload["cells"])
        assert "data:image/" not in source
        for target in re.findall(r"!\[[^]]*\]\(([^)]+)\)", source):
            if "://" not in target:
                assert (notebook.parent / target).resolve().is_file(), target


def test_bilingual_editorial_labels_are_localised_and_grammatical() -> None:
    sources: dict[str, str] = {}
    for language, notebook in NOTEBOOKS.items():
        payload = json.loads(notebook.read_text(encoding="utf-8"))
        sources[language] = "\n".join(
            _cell_source(cell) for cell in payload["cells"] if cell["cell_type"] == "markdown"
        )

    assert "Las cuatro métricas tradicionales" in sources["es"]
    assert "11 tienen gestión activa identificada y 1 corresponde" in sources["es"]
    assert " | True |" not in sources["es"]
    assert " | False |" not in sources["es"]
    assert " | Sí |" in sources["es"]
    assert " | No |" in sources["es"]

    assert "All four traditional metrics" in sources["en"]
    assert "11 have identified active management and 1 is" in sources["en"]
    assert " | True |" not in sources["en"]
    assert " | False |" not in sources["en"]
    assert " | Yes |" in sources["en"]
    assert " | No |" in sources["en"]


def test_every_figure_has_a_real_language_specific_variant() -> None:
    assert {path.name for path in (FIGURES / "en").glob("*.png")} == FIGURE_NAMES
    assert {path.name for path in (FIGURES / "es").glob("*.png")} == FIGURE_NAMES
    for name in FIGURE_NAMES:
        assert _sha256(FIGURES / "en" / name) != _sha256(FIGURES / "es" / name)


def test_frozen_public_counts_match_the_published_claims() -> None:
    selected = pd.read_csv(ARTIFACTS / "selected_etfs.csv")
    intentional = pd.read_csv(ARTIFACTS / "intentional_management_products.csv")
    candidates = pd.read_csv(ARTIFACTS / "risk_efficient_candidates.csv")
    matched = pd.read_csv(ARTIFACTS / "return_matched_leverage.csv")
    audit = pd.read_csv(ARTIFACTS / "management_style_audit.csv")
    study = json.loads((ARTIFACTS / "study_summary.json").read_text(encoding="utf-8"))

    assert len(selected) == 2_005
    assert int(selected["beat_spy_rwm_score"].sum()) == 156
    assert int(selected["beat_spy_cagr_and_rwm"].sum()) == 89
    assert len(intentional) == 217
    assert int(intentional["beat_spy_rwm_score"].sum()) == 25
    assert len(candidates) == 12
    assert int(matched["feasible_at_or_below_2x"].sum()) == 11
    assert int(
        (matched["feasible_at_or_below_2x"] & matched["matched_rwm_beats_spy"]).sum()
    ) == 8
    assert len(audit) == 2_022
    assert "not_determined" not in set(audit["management_style"])
    assert int((audit["management_style"] == "not_applicable_security").sum()) == 17
    assert study["current_listing_count"] == 1_938
    assert study["historical_identity_count"] == 67
    assert study["curve_diagnostics"]["fixed_complete_constituents"] == 1_935


def test_manifest_covers_and_authenticates_the_public_edition() -> None:
    manifest = json.loads(
        (ARTIFACTS / "publication_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["edition"] == "0.2.1"
    assert manifest["data_close"] == "2026-09-04"
    assert manifest["headline_counts"]["risk_efficient_candidates"] == 12
    for relative, expected_hash in manifest["files"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert _sha256(path) == expected_hash, relative
