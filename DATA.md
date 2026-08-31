# Data note

This repository publishes derived research evidence, not a mirror of the providers' raw market histories.

## Sources

- **ETF catalogue and metadata:** free public issuer, exchange, SEC and Yahoo Finance information assembled by the universe collector.
- **Total-return proxy:** Yahoo Finance daily adjusted close.
- **Cash:** FRED Effective Federal Funds Rate (`DFF`), accrued on calendar days with no spread under Actual/360 and sampled on ETF sessions.
- **Benchmark:** SPY, aligned to each product on exact shared trading dates.

The study endpoint is 27 August 2026. The maturity cutoff admits economic products launched no later than 1 March 2022. Every admitted product is measured from its own first comparable session; the cutoff does not force a common inception date.

## Published evidence

`reports/etf_universe_1A/data/` contains the frozen derived tables used to inspect the report:

- the selected cohort and consolidated ticker aliases;
- taxonomy and evidence buckets;
- group summaries and descriptive wealth curves;
- RWM and DBF leader tables;
- intentional-management and alternative-strategy subsets;
- entry-point robustness;
- fixed-debt leverage, return matching and financing sensitivity;
- the compact study summary and selection funnel.

These files contain classifications, metrics, aggregated curves or transformed research outputs. They are not the original provider responses.

## Not redistributed

The repository intentionally excludes:

- raw Yahoo Finance daily price Parquet files;
- raw or normalized provider metadata snapshots;
- the original FRED DFF CSV;
- collector logs, lock files, status files and local runtime state;
- large intermediate and processed working directories.

To reproduce from source, run the documented collectors in accordance with each provider's terms and rate limits, then generate the study tables. Yahoo Finance availability, symbol identity and adjusted-close conventions can change, so a future acquisition may not reproduce every historical value byte for byte.

## Quality controls

The frozen run validated **5,505** Parquet files without schema or integrity failures. The market manifest records symbol, row count, first and last dates, file size, SHA-256, attempts and error classification. Historical ticker aliases are consolidated before the 2,023-product cohort is formed.

The catalogue contains historical identities, but the 67 non-current series observed in the downloaded universe all reach recent dates. They do not constitute a representative sample of liquidations through time. Survivorship bias therefore remains a material limitation rather than a solved problem.

## Third-party rights

Code and original documentation are covered by the repository license. Yahoo Finance, FRED and all other third-party data remain subject to their respective terms. Inclusion of derived research tables does not grant rights over provider data or product names.
