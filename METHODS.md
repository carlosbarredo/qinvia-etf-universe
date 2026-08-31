# Methods

## Research question

The study asks how often mature ETFs beat SPY in realised compound growth and cash-relative path efficiency, and how much of that apparent success survives after separating exposure from intentional management.

SPY is a common and deliberately demanding reference. It is not asserted to be the correct mandate benchmark for every product.

## Universe construction

1. Collect low-cost metadata before acquiring every price history.
2. Classify each candidate as `eligible`, `ineligible` or `review` without using subsequent performance.
3. Exclude inverse, leveraged, volatility-linked and structurally path-dependent products from the primary long-investment universe.
4. Preserve exclusion reasons and unresolved identities.
5. Consolidate confirmed historical ticker aliases into one economic product.
6. Require launch no later than 1 March 2022 for the primary mature cohort.

The detailed eligibility contract is in [docs/SCOPE.md](docs/SCOPE.md).

## Return construction and alignment

Yahoo Finance adjusted close is used as the free total-return proxy. Each product is aligned with SPY on exact shared sessions and evaluated from its own first comparable date. Missing observations are not forward-filled into artificial returns.

The report keeps CAGR, Sortino, Calmar and traditional Martin as descriptive measures. Relative-Wealth Martin (RWM) is the primary comparison criterion:

```text
relative wealth = fund wealth / cash wealth
RWM = CAGR(relative wealth) / Ulcer Index(relative wealth)
```

Cash is FRED DFF accrued daily under Actual/360 with no spread. Both RWM's growth and drawdown are measured on the same fund-to-cash relative wealth object. CAGR remains visible as the economic-magnitude companion.

## Taxonomy and attribution boundary

The taxonomy separates asset class, exposure structure, strategy, sector, theme, geography and management style. For attribution, the study distinguishes:

- broad-market beta;
- concentrated sector or thematic beta;
- systematic or rules-based exposure;
- intentional management, including identified active, long/short, market-neutral and alternative processes;
- unresolved or other cases.

A semiconductor or gold-miner ETF can beat SPY because its narrower exposure was favoured during the sample. That is a valid realised result, but it is not treated as demonstrated manager skill.

## Stability and leverage diagnostics

Entry-point robustness measures three-year windows starting at different months. The windows overlap and are therefore a temporal sensitivity analysis, not independent proof of persistence.

The leverage ladder fixes debt at inception and does not rebalance. Financing accrues DFF plus the declared spread under Actual/360. Return matching solves ex post for the leverage required to reach SPY's terminal wealth, subject to the study's leverage and maintenance constraints. It is diagnostic, not an executable rule.

The project's adaptive cost-and-slippage model applies when a strategy changes exposure. Buy-and-hold comparisons and the descriptive cross-sectional mean do not invent turnover that did not occur.

## Capacity and scale

The report discusses finite alpha capacity as a plausible mechanism: successful products attract assets, and larger positions can increase impact, liquidity constraints, costs and competition. It also presents counterevidence showing that liquid universes and cost-aware execution can support substantially greater capacity than simple estimates imply.

The ETF dataset does not causally identify flows or estimate each process's capacity. The mechanism is framed as a literature-consistent hypothesis, not a demonstrated finding.

## Reproducibility boundary

The public repository makes code, tests, reports, notebooks and derived research tables inspectable. Raw Yahoo histories and the original FRED file are not redistributed. Reacquiring provider data is required for a full source-to-report rebuild; see [DATA.md](DATA.md).
