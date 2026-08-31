# QINVIA Historical Adaptive Cost and Slippage Model

**Status:** canonical project specification

**Version:** 1.0
**Frozen:** 28-Aug-2026

## 1. Purpose

This document defines the common transaction-friction model for QINVIA's long-run
S&P 500 studies. Every study that changes market exposure must cite this document,
apply the central specification, and include a dedicated **cost and slippage
sensitivity analysis**.

The model is deliberately **vehicle-agnostic**. It is a practical compromise intended
to approximate an efficient implementation through an S&P 500 ETF, equity-index
futures, or a comparable liquid instrument. It is not an exact reconstruction of a
particular broker, order type, ETF, futures contract, or account size.

## 2. Interpretation

Each rate is a **one-way, all-in cost per unit of exposure traded**. It combines:

- brokerage and exchange costs;
- bid-ask spread;
- execution slippage; and
- a limited allowance for other implementation frictions.

The components are not estimated or charged separately. No additional commission or
slippage may be added unless a study is explicitly designated as a vehicle-specific
implementation study.

This model measures the incremental friction caused by **changing exposure**. It does
not model ETF expense ratios, futures basis or roll yield, collateral mechanics,
financing spreads, taxes, market impact from institutional-size orders, or margin
liquidations. Those items belong in separate, clearly labelled analyses.

## 3. Central historical schedule

| Effective execution date | P10 | Base | P65 | P90 |
|---|---:|---:|---:|---:|
| Through 28-Feb-1997 | 30 bps | **40 bps** | 50 bps | 75 bps |
| 01-Mar-1997 through 31-Dec-2002 | 12 bps | **15 bps** | 20 bps | 30 bps |
| From 01-Jan-2003 | 0.55 bps | **0.65 bps** | 0.90 bps | 1.40 bps |

The first row is used only in studies extending before the principal 1997+ sample.
The date band is selected from the **effective execution date**, not the signal date.

The schedule is a conservative research assumption rather than a claim that these
were the uniquely observable costs of SPY or S&P 500 futures. Its purpose is to avoid
both zero-cost backtests and the implausible use of one constant rate across very
different market-structure eras.

## 4. Volatility-adaptive bucket

The bucket is determined from 20-session realized volatility (`RV20`) known before
execution. The thresholds are the 10th, 65th, and 90th percentiles of an expanding
distribution using only information available by that time.

For an execution on date \(d\):

- **P10:** \(RV20_d^{known}\le Q_{10,d}^{lagged}\);
- **Base:** \(Q_{10,d}^{lagged}<RV20_d^{known}\le Q_{65,d}^{lagged}\);
- **P65:** \(Q_{65,d}^{lagged}<RV20_d^{known}\le Q_{90,d}^{lagged}\);
- **P90:** \(RV20_d^{known}>Q_{90,d}^{lagged}\).

`RV20_known` and every percentile must use data available before the execution. In
the principal 1997+ study, the expanding cost history begins at the preregistered
study start; observations before that date are not used. Until at least 252 valid
daily observations are available, the **Base** bucket is mandatory.

The percentile labels identify volatility regimes. They are not statistical
confidence levels and do not imply that the cost itself was directly observed at
those percentiles.

## 5. Turnover and cost accounting

For strategy exposure \(E_d\), daily traded exposure is:

\[
Turnover_d=\left|E_d-E_{d-1}\right|.
\]

The central cost deducted from the portfolio return is:

\[
Cost_d=Turnover_d\times CostRate_d.
\]

The rate is expressed in decimal form in the calculation: one basis point is
\(0.0001\).

Example: if exposure falls from 100% to 60%, turnover is 40%. With an applicable
one-way rate of 40 bps:

\[
Cost_d=0.40\times0.0040=0.0016,
\]

or **16 bps of portfolio value**.

An entry and a later exit each incur their corresponding one-way cost. A change from
0.5× to 1.5× is turnover of 1.0; leverage does not change the formula. Costs are zero
when exposure does not change.

## 6. Timing and anti-look-ahead

The mandatory sequence is:

1. information and signals are observed at \(t\);
2. desired exposure is fixed using only information known at \(t\);
3. that exposure becomes effective at \(t+1\);
4. the cost uses the historical band and volatility bucket applicable to the
   effective execution date \(t+1\); and
5. the resulting cost is deducted once from the return assigned to that execution.

All volatility inputs and expanding percentiles must be lagged consistently. Future
observations may never influence the cost bucket.

## 7. Cash, financing, and Buy & Hold

- The uninvested fraction receives the contemporaneous risk-free return under the
  portfolio specification.
- Risk-free return and any separately declared financing assumption are not part of
  the cost-and-slippage rate.
- Buy & Hold pays no fictitious switching cost because its exposure remains fixed.
- Dynamic strategies pay for every modeled change, including their initial move from
  zero exposure under the existing QINVIA accounting convention.
- The same convention must be used for all strategies within a comparison.

## 8. Mandatory cost and slippage sensitivity analysis

The central schedule above remains the primary specification. Robustness is tested by
multiplying every all-in rate—commission, spread, and slippage together—by a common
factor \(k\):

\[
Cost_d(k)=Turnover_d\times CostRate_d\times k.
\]

| Analysis | Multiplier \(k\) | Interpretation |
|---|---:|---|
| Gross diagnostic | 0.00× | Frictionless reference; never the primary result |
| Low-friction sensitivity | 0.50× | Central all-in costs and slippage reduced by 50% |
| **Central specification** | **1.00×** | Historical Adaptive Cost and Slippage Model |
| High-friction sensitivity | 1.50× | Central all-in costs and slippage increased by 50% |
| Severe-friction stress | 2.00× | Central all-in costs and slippage doubled |

The multiplier does **not** represent exposure or leverage. It changes only the
all-in cost-and-slippage rate. Signals, forecasts, exposure paths, rebalance dates,
model parameters, and all non-transaction assumptions must remain frozen across the
sensitivity grid.

The sensitivity analysis must not be used to select the most attractive result. Its
purpose is to show whether the economic conclusion depends on an unusually favorable
or unfavorable friction assumption.

### Required sensitivity outputs

Every applicable study must report, for each multiplier:

- CAGR and cumulative return;
- annualized volatility, Sharpe, and Sortino;
- Maximum Drawdown, Ulcer Index, Calmar, and Martin Ratio;
- average exposure and annualized turnover;
- cumulative and approximate annualized cost and slippage;
- changes in CAGR and risk-adjusted metrics versus the 1.00× central result; and
- the ranking and substantive conclusion versus Buy & Hold.

The study must also state:

1. whether its main conclusion survives at 1.50× and 2.00×;
2. whether weekly results deteriorate faster than monthly results because of greater
   turnover;
3. whether the preferred strategy changes across the grid; and
4. where relevant, the approximate break-even multiplier at which the economic
   conclusion reverses.

At minimum, include a sensitivity table and one compact chart showing CAGR, Sharpe,
and Maximum Drawdown across the multipliers. Gross-versus-net equity curves may be
added when they materially improve interpretation.

## 9. Mandatory QA checks

Each study must verify automatically that:

- effective exposure uses the required one-period lag;
- cost percentiles are expanding and lagged;
- Base is used before the minimum history exists;
- the correct date band is selected from the execution date;
- exposure and turnover contain no silent missing values;
- turnover equals the absolute change in effective exposure;
- cost equals turnover times exactly one all-in rate;
- no separate commission or slippage is double counted;
- no cost appears when turnover is zero;
- Buy & Hold has no switching cost;
- sensitivity costs scale linearly with \(k\); and
- signals and exposures are identical across all sensitivity multipliers.

## 10. Reporting language and citation

Do not describe the model merely as “commissions”. Use **costs and slippage** or
**all-in transaction friction** throughout tables, charts, and conclusions.

Recommended study wording:

> Incremental transaction friction is estimated using the QINVIA Historical Adaptive
> Cost and Slippage Model. The model applies a one-way all-in rate to each absolute
> change in exposure, varies that rate by market-structure era and lagged expanding
> RV20 regime, and charges no fictitious switching cost to Buy & Hold. The 1.00×
> schedule is the central result; 0.50×, 1.50×, and 2.00× are reported as cost and
> slippage sensitivities. The model is vehicle-agnostic and should not be interpreted
> as an exact reconstruction of SPY or S&P 500 futures.

Every notebook, HTML report, executive summary, and manifest must link to this file
and record:

- specification version;
- sensitivity multipliers run;
- cost-history start date;
- minimum percentile history;
- execution lag; and
- any authorized deviation from the canonical model.

## 11. Scope and governance

The 1.00× schedule is frozen as the QINVIA central research convention. It must not be
altered because a completed backtest looks better or worse. Changes require a new
version, an explicit rationale, and parallel reporting under the previous version.

A future study using actual SPY quotes, futures order-book data, broker statements,
contract rolls, or market-impact estimates may supersede this approximation for that
specific implementation. It must be labelled as a separate vehicle-specific study;
it does not silently redefine this common benchmark.

## 12. Empirical context

The schedule is motivated by broad changes in market structure rather than claimed
point estimates. Relevant context includes the September 1997 launch of the electronic
E-mini S&P 500 contract and the 2000–2001 transition to decimal equity pricing, which
helped reduce quoted spreads. Historical research also shows that futures and cash
equity implementation costs can differ substantially, reinforcing the need to call
this schedule a vehicle-agnostic compromise.

- CME Group, *The Origins of the E-mini S&P 500*:
  <https://www.cmegroup.com/education/articles-and-reports/the-origins-of-the-e-mini-s-p-500>
- U.S. SEC, *The Effects of Decimalization on the Securities Markets*:
  <https://www.sec.gov/news/testimony/052401tslu.htm>
- Hasbrouck, *Trading Costs and Returns for U.S. Equities*:
  <https://pages.stern.nyu.edu/~jhasbrou/Research/GibbsCurrent/HasbrouckJF.pdf>
