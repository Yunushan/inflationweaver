# Calculation methodology

This document describes the mathematical contract of InflationWeaver 0.1.0. Output is conditional on the supplied asset, CPI, currency, observation timing, and adjustment policy. It is not a claim that two inflation providers measure the same basket or that every input is an investable total-return series.

## 1. Series contracts and units

`Series` identifies a Polars table with `date,value` plus optional `available_date` and provenance columns. Metadata includes `series_id`, `kind`, `currency`, `source`, and `synthetic`.

| Kind | `value` means | Allowed values |
| --- | --- | --- |
| `price` | Asset price or index level | Strictly positive, finite |
| `wealth` | Net equity, total-return wealth, or portfolio value | Strictly positive, finite |
| `cpi` | Consumer price index level | Strictly positive, finite |
| `monthly_rate` | Month-on-month percentage change; `2.5` means 2.5% | Finite and greater than −100 |
| `fx` | Units of the metadata numerator currency per denominator currency | Strictly positive, finite |

Prices, wealth, and CPI levels are never interchangeable with annual headline inflation or bond yields. A `monthly_rate` series must be chained into CPI levels before analysis. CPI metadata uses the relevant monetary/purchasing-power currency; its numeric value remains an index, not a cash amount.

Direct Python validation requires unique, strictly increasing dates. CSV ingestion sorts observations and rejects duplicates. Dates are calendar dates. Mixed timestamp/time-zone data must be prepared explicitly before import. Different days in one observation month are not interchangeable merely because they share a month label.

CSV export sidecars bind metadata to bytes using SHA-256. Store the actual source URL, retrieval date, provider identifier, base definition, transformations, and release/vintage policy alongside real input files. A checksum establishes file integrity, not economic correctness or source authenticity.

## 2. Exact inflation adjustment

Let `P(t)` be a same-currency asset/equity value and `C(t)` the selected positive CPI level. Let `b` be the actual chosen baseline observation.

```text
nominal_index(t) = 100 × P(t) / P(b)
inflation_index(t) = 100 × C(t) / C(b)
real_index(t) = 100 × [P(t) / P(b)] / [C(t) / C(b)]
real_value(t) = P(t) × C(b) / C(t)
nominal_return_pct = nominal_index(end) - 100
inflation_return_pct = inflation_index(end) - 100
real_return_pct = real_index(end) - 100
```

`real_index` is a normalized growth index. `real_value` is the supplied price/value expressed at base-date purchasing power; for a price index, the units are real index points, not the cash value of an actual investment. The metadata label identifies the purchasing-power currency.

Example: a value moves from 100 to 150 and CPI from 100 to 125. The exact real gain is `(150/100)/(125/100)-1 = 20%`. Subtracting the 25% inflation gain from the 50% nominal gain is an approximation and produces a different answer.

This CPI-ratio approach follows [BLS guidance on constant dollars](https://www.bls.gov/cpi/factsheets/purchasing-power-constant-dollars.htm). [BLS percent-change guidance](https://www.bls.gov/cpi/factsheets/calculating-percent-changes.htm) also distinguishes a change in index points from a percentage change.

## 3. Compounding monthly rates

For a verified month-on-month rate `m(t)` expressed in percent:

```text
C(t) = C(t-1) × [1 + m(t)/100]
cumulative inflation = product[1 + m(t)/100] - 1
```

The anchor belongs to the month immediately before the first supplied monthly rate. `chain_monthly_rates` rejects missing months, duplicate/order errors, factors that are not positive, and arithmetic overflow/underflow. The arbitrary anchor level, commonly 100, cancels when computing ratios.

```python
from inflationweaver.engine import chain_monthly_rates
from inflationweaver.providers import read_csv

rates = read_csv(
    "my_verified_enag_mom.csv", "ENAG_MOM",
    kind="monthly_rate", currency="TRY", source="verified ENAG bulletin",
)
cpi = chain_monthly_rates(rates, anchor_date="2020-08-01", anchor_value=100)
```

The anchor date above illustrates the calling convention; it does not certify that your file covers a particular historical month. Read the file's first observation and verify its prior-month anchor.

**Do not compound year-on-year rates as monthly rates.** A YoY value describes a ratio across 12 months, not the one-month step. It does not determine the monthly path. The adapter does not automatically transform preserved `published_yoy` columns into levels.

If monthly-rate inputs carry availability dates, each generated CPI observation can only be available after every preceding rate on which its cumulative level depends. Availability propagates the latest known prior release; an unknown preceding release keeps derived availability unknown. The artificial anchor has unknown availability and must be supplied explicitly before publication-aware analysis. An arbitrary anchor must not be assumed to have been public on its observation date.

## 4. Rebasing and selected dates

Multiplying every CPI observation by the same positive constant leaves inflation ratios unchanged. Re-referencing a CPI from one base period to another is therefore different from selecting the analysis baseline.

The requested `base_date` selects the **first actual asset point on or after it**. No synthetic price is created for a weekend, public holiday, or absent observation. A requested base more than `max_staleness_days` before that point fails; requesting 1986 against a 2023 demonstration cannot masquerade as long historical coverage. Metadata records `requested_base_date`, `actual_base_date`, and the matched baseline CPI observation. If no base is supplied, `start_date` acts as the baseline request; otherwise the first supplied asset point is used.

`start_date` may be later than an explicit base. In this case it limits displayed points, while normalization, summary returns, CAGR, and drawdowns still cover **base to end**. Reports expose both the actual base and actual display start. An end-date filter uses the latest eligible supplied point on or before the requested date; it never extrapolates the endpoint. Inspect actual dates and staleness before describing a result as covering a calendar interval.

## 5. Observation versus released alignment

| Mode | Matching rule | Appropriate interpretation |
| --- | --- | --- |
| `observation` | On each asset observation date, use the latest CPI observation dated on or before it | Retrospective description using the supplied vintage |
| `released` | Evaluate an asset observation at its explicit availability date; use the newest observation among CPI records available by then | A publication-aware view of the supplied data |

Observation matching uses backward as-of lookup. It never uses a CPI observation dated after the asset point. This alone does not prevent release-date lookahead: January CPI may have a January observation label but be published in February.

Released mode requires complete `available_date` columns for **both** asset and CPI. It does not silently substitute a presumed one-month lag. An asset timeline must have unique availability dates. A late publication of an older CPI observation does not displace a newer known observation.

`max_staleness_days` defaults to **62** for CPI and counts age from the **CPI observation date**, including in released mode. Older matches fail. Choose the tolerance deliberately for the supplied frequency and release schedule; increasing it permits stale information, not new coverage. Monthly-rate chaining separately checks every required month. A stale limit does not prove that every CPI observation month is present in a source file.

**Vintage limitation:** release dates prevent premature access to the supplied observations. They do not reproduce values before later revisions. The default provider adapters download latest-vintage data without invented availability dates. A rigorous historical decision backtest needs the exact vintage known at each decision point, source release records, and a vintage selection process. See [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html). This release does not implement an ALFRED vintage archive or multi-vintage event replay.

## 6. TÜİK–ENAG hybrid

`splice_cpi(left, right, splice_date)` accepts two same-currency CPI **level** series with an exact shared observation on the switch date `s`.

```text
scale = left(s) / right(s)
hybrid(t) = left(t),                 t <= s
hybrid(t) = right(t) × scale,        t > s
```

The procedure keeps the left-hand levels through the switch and preserves subsequent percentage changes from the right-hand series. If ENAG is supplied as monthly changes, chain it into levels first. No arbitrary switch without common data is permitted.

```python
from inflationweaver.engine import splice_cpi

hybrid = splice_cpi(tuik_levels, enag_levels, splice_date="2020-09-01")
```

That date is an example; your actual same-date verified overlap governs the switch. A level normalization enforces numerical continuity. It does not establish methodological equivalence, calibrate provider bias, or prove that the baskets are interchangeable.

The output is identified as `hybrid:<left_id>+<right_id>`, records providers, switch and scale in provenance, and is flagged `synthetic=True` because it is a constructed analytical series. Derived publication dates must account for both overlap observations and the subsequent right-side observation. In this context **constructed** does not mean the upstream observations are fake. Bundled demonstrations are separately labeled with synthetic-demo sources. Never advertise a 1986 hybrid as ENAG data observed since 1986.

Report separate TÜİK and ENAG/hybrid outcomes when judging sensitivity to inflation choice. A hybrid makes an assumption about switching measurement systems; no mathematics can remove that assumption.

## 7. CAGR and drawdown

For a positive terminal growth factor `G`, elapsed calendar days `d > 0`, and `Y = d/365.2425`:

```text
CAGR_pct = 100 × [G^(1/Y) - 1]
drawdown_pct(t) = 100 × [index(t) / running_max(index up to t) - 1]
max_drawdown_pct = minimum(drawdown_pct(t))
```

CAGR uses actual elapsed days, not the number of sampled rows. A zero-day interval has undefined CAGR, represented as `null`. Nonfinite annualization also produces `null`; raw positive arithmetic failures are rejected. Nominal and real drawdowns use their respective growth indices and begin at the baseline.

Drawdowns are **negative percentages**: −20 means a 20% fall from a previous peak. Sampling controls what the measure observes. Monthly prices can miss intramonth drawdowns. Mixed calendars and common-date comparisons can change the observed extrema; do not interpret the result as a tick-level risk measure.

## 8. Currency conversion and comparisons

Before deflation, convert a foreign-currency asset into the CPI currency. For a USD asset and a TRY-per-USD quote:

```text
P_TRY(t) = P_USD(t) × FX_TRY_per_USD(t)
```

For `convert_currency(..., operation="multiply")`, `fx.currency` must be `TARGET/SOURCE`; for `divide`, it must be `SOURCE/TARGET`. The direction is checked from metadata, never guessed from a ticker string. This convention describes units per unit; market display notation such as “USD/TRY” is often used differently, so set metadata deliberately.

Conversion uses a backward as-of FX observation with default maximum staleness **7 days**. Future FX is never used. When both input availability columns exist, converted points are available only after both component observations; if either date is unknown, availability remains unknown. This routine does not supply intraday venue alignment or simulate currency execution spreads.

Python `compare_assets` uses exact common observation dates, requires one currency and unique asset identifiers, and applies the same baseline and CPI to every series. Released comparisons additionally require same-day availability for the common asset dates. No constituent is forward-filled. Empty overlap is an error. The dashboard's two-series comparison shares baseline/end decision dates but retains intermediate observation frequencies, so its drawdown samples may differ from an exact-common-date Python comparison. A comparison cannot show an asset before its own inception, and a benchmark price index is not equivalent to a net total-return fund.

## 9. Portfolios

`portfolio_curve(assets, weights, initial_value=100)` buys fixed units at the first common observation:

```text
units_i = initial_value × initial_weight_i / price_i(base)
portfolio_value(t) = sum(units_i × price_i(t))
```

Weights are nonnegative and sum to one. The portfolio uses exact common constituent dates and never rebalances; weights drift as prices change. Derived availability accounts for every constituent's baseline purchase quote as well as the current quote. Price inputs omit distributions unless reflected in an adjusted wealth curve. Fees, taxes, transaction costs, fractional-share constraints, shorting, borrowing, periodic cash contributions, and rebalancing execution are not modeled by this function. Evaluate the returned same-currency wealth series with `analyze` to obtain real portfolio performance.

## 10. Deposits and bonds

`deposit_curve` is a labeled **illustrative constant gross APR model**, not a reconstruction of a bank product. For principal `V0`, nominal annual rate `r`, time `Y = actual_days/365.2425`, and compounding frequency `n`:

```text
compound value = V0 × (1 + r/n)^(n × Y)
simple value = V0 × (1 + r × Y)
```

Daily, monthly, quarterly, annual, and simple choices are supported. Daily uses `n=365.2425`. Fractional periods accrue smoothly; the routine does not implement settlement-day conventions, changing rates, tax, deposit term rollovers, maturity schedules, or bank-specific interest rounding. Supply an actual net account-value curve for real historical performance.

A bond yield/rate quote is not a wealth series. Supply a bond price series for price analysis or a total-return curve incorporating coupon income and reinvestment. Housing indices likewise measure aggregate prices; rent, transaction costs, financing, taxes, and individual-property variation must be modeled outside the CPI deflator.

## 11. Strategy / trading-bot adapter

`analyze_backtest` consumes an existing marked-to-market net equity table. Execution simulation, slippage, fees, tax, dividend income, borrow costs, and leverage accounting belong to the source trading system.

Without a cashflow column, input must already be a cashflow-free performance curve. With a supplied cashflow column, the adapter supports contributions/withdrawals **at the beginning of each row's period**:

```text
period_growth(t) = equity(t) / [equity(t-1) + external_flow(t)]
unitized_value(t) = unitized_value(t-1) × period_growth(t)
```

Positive flow means contribution; negative flow means withdrawal. The first row establishes baseline equity and requires zero flow. Capital after the beginning-of-period flow must be positive. Intraperiod or end-of-period flows require a separately unitized source curve; this adapter is not a general money-weighted return, XIRR, or transaction-ledger solver.

## 12. Pine and export interpretation

Pine exports embed the selected CPI history and preserve its data label. An observation-time series is retrospective; a released series is constrained by explicitly supplied availability. The price history still comes from the TradingView symbol and timeframe and may differ from your imported adjusted asset history. Retrospective CPI choice is unsuitable as a historical trading signal without release/vintage controls.

A generated script does not create TradingView prices before the provider's available bars and does not supply a live ENAG feed. Verify actual baseline, source, timeframe, and units when comparing Python and Pine reports.

## 13. Interpretation boundaries

The code can check contracts, arithmetic and timing, but cannot certify that a manually labeled input really came from an official source. Positivity deliberately excludes bankrupt equity values at zero, negative-priced instruments, and some derivative contracts; adapt those models before using this engine. No CPI represents every individual's spending basket. Distinct CPI providers, baskets, seasonal adjustments, index methodologies, price/total-return bases and revision vintages produce distinct answers.

The repository provides reproducible measurement, not investment forecasts, automated trading instructions, or an assertion that any provider is the uniquely correct inflation measure.
