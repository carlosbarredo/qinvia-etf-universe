# ETF Universe

**A bilingual, reproducible study of ETF exposure, intentional management, and why SPY is so hard to beat.** The project builds an auditable universe from free data, separates narrow beta from products that intentionally manage risk or selection, and compares every mature product with SPY over its own exact common history.

[Study](https://qinvia.com/research/etf-universe-exposure-skill) · [English notebook](notebooks/etf_universe_en.ipynb) · [Spanish notebook](notebooks/etf_universe_es.ipynb) · [Español](README_ES.md) · [Method](METHODS.md) · [Data provenance](DATA.md) · [Publication manifest](artifacts/etf-universe/publication_manifest.json)

## Evidence at a glance

The primary cohort contains **2,005 ETF portfolios and accepted exchange-traded trusts** launched no later than 1 March 2022. Historical ticker aliases are consolidated and 17 ETNs or other non-ETF securities are retained in the audit trail but removed from performance claims. Each product is evaluated from its own first exact common session with SPY through the study endpoint. The data close is **4 September 2026**.

- **7.8%** beat SPY on Relative-Wealth Martin (RWM), the study's primary path-efficiency criterion.
- **4.4%** beat SPY on both RWM and CAGR.
- Among **217** products classified as intentional management, **25** beat SPY's RWM and **12** do so from a majority of tested entry points.
- After matching SPY's terminal return and charging financing, **8 of 11** feasible candidates preserve a higher RWM.

These results do not establish that every narrow exposure is useless or that every active process lacks skill. They show that exposure, path efficiency, capacity and management intent must be separated before attributing outperformance to skill.

## What the study adds

1. **An auditable funnel.** Products are classified as `eligible`, `ineligible` or `review`, with explicit exclusion reasons for leverage, inverse exposure, volatility trading and path-dependent structures.
2. **Identity controls.** Historical ticker aliases are consolidated so that a symbol change is not counted as a new economic product.
3. **A full taxonomy.** Asset class, exposure, strategy, sector, theme, geography and management style are kept separate.
4. **A single primary decision criterion.** CAGR, Sortino, Calmar, Martin and RWM remain visible, but the comparison with SPY is decided principally by RWM, with CAGR as economic context.
5. **Exposure versus intent.** Broad beta, concentrated sector or thematic beta, systematic rules and intentional management are analysed separately.
6. **Stress tests.** The study includes entry-point stability, a fixed-debt leverage ladder, return matching and financing-spread sensitivity.

## Notebooks and reproducible evidence

The bilingual notebooks are the primary GitHub publication format. They preserve the narrative, formulas, tables and frozen derived evidence while loading figures from normal, language-specific repository assets.

| Language | Notebook | Qinvia web edition |
|---|---|---|
| English | [Open notebook](notebooks/etf_universe_en.ipynb) | [Read online](https://qinvia.com/research/etf-universe-exposure-skill) |
| Español | [Abrir notebook](notebooks/etf_universe_es.ipynb) | [Leer en la web](https://qinvia.com/es/research/etf-universe-exposure-skill) |

The repository includes derived research tables required to inspect the published counts. It does **not** redistribute raw Yahoo Finance price histories or the original FRED DFF source file. See [DATA.md](DATA.md).

## Install and test

The acquisition pipeline is designed for Linux or WSL because its autonomous collectors use POSIX file locking.

```bash
git clone https://github.com/carlosbarredo/qinvia-etf-universe.git
cd qinvia-etf-universe
python -m pip install -e ".[dev,research]"
python -m pytest
```

The tests cover classification, taxonomy, adjusted-history validation, benchmark metrics, DBF descriptors, leverage mechanics, RWM cash-relative calculations and the integrity of the bilingual public edition.

## Rebuild the publication

After acquiring the provider data and producing the study tables described in [DATA.md](DATA.md):

```bash
python scripts/audit_management_styles.py
PYTHONPATH=src python -m qinvia_etfs.universe_study
PYTHONPATH=src python -m qinvia_etfs.leverage_study
python scripts/build_etf_universe_study.py
```

The management audit first assigns every product from SEC N-CEN or a documented primary source. The research builder regenerates both languages from one source. This public repository promotes the notebooks and derived evidence; the web edition is maintained separately by Qinvia Web.

## Scope and limitations

- SPY is a deliberately demanding common reference, not the natural benchmark for every mandate.
- Yahoo Finance is free and useful, but symbols, classifications and adjusted histories can change.
- The catalogue preserves historical identities, yet the available dead-fund sample is not representative; survivorship bias remains material.
- RWM describes realised cash-relative growth and drawdown. It does not reveal leverage, liquidity, capacity, option payoffs or unseen tail risk.
- The capacity mechanism discussed in the report is a literature-consistent hypothesis, not a causal result identified by this dataset.
- Return-matched leverage is an ex-post diagnostic, not an executable strategy.

## Citation, license and disclaimer

Citation metadata is available in [CITATION.cff](CITATION.cff). Code and original documentation are released under the [MIT License](LICENSE). Third-party data remain subject to their providers' terms.

Qinvia · Carlos Barredo Lago · Methodological research, not financial advice.
