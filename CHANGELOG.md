# Changelog

All notable public changes to this project are documented here.

## 0.2.1 — 2026-09-09

- Corrected the bilingual candidate wording so the singular inferred strategy agrees with the 11 identified-active cases.
- Renamed the combined legacy score as the four traditional metrics.
- Localised notebook boolean tables as `Sí/No` in Spanish and `Yes/No` in English.
- Added regression checks so these editorial defects cannot silently return.

## 0.2.0 — 2026-09-09

- Updated the market close through 4 September 2026 and published a strict 2,005-product analytical cohort.
- Added a row-level management-style audit based on SEC N-CEN and documented primary-source overrides.
- Removed 17 ETNs and other non-ETF securities from performance claims while preserving them in the audit trail.
- Recomputed the bilingual notebooks and derived evidence: 156 products beat SPY's RWM and 89 beat both RWM and CAGR.
- Expanded the intentional-management block to 217 products: 25 beat RWM and 12 do so from a majority of tested entry points.
- Updated the moderate-leverage diagnostic: 11 candidates can match SPY at or below 2× and 8 preserve higher RWM after financing.
- Externalized all notebook figures into language-specific repository assets.
- Added publication-integrity tests and a SHA-256 manifest for the notebooks, figures and frozen evidence.
- Kept the market module importable for local inspection and testing on Windows while retaining the documented WSL acquisition workflow.

## 0.1.0 — 2026-08-31

- Published the bilingual ETF Universe report and paired notebooks.
- Froze the 2,023-product mature cohort after historical ticker consolidation.
- Added exposure and management-intent taxonomies.
- Adopted RWM as the primary SPY comparison criterion, with CAGR as economic context.
- Added entry-point stability, fixed-debt leverage, return matching and financing sensitivity.
- Published derived evidence tables without redistributing raw Yahoo Finance or FRED source histories.
