# TradingView and Pine Script v6

InflationWeaver exports validated **CPI index levels** into a self-contained Pine v6 indicator. The indicator reads an asset from TradingView, aligns it with the embedded CPI table, and displays nominal and inflation-adjusted performance from the same actual base date. You can use BIST indices and shares, currency pairs, metals, ETFs, crypto, or other TradingView price symbols, subject to provider history and a matching quote currency.

The checked-in [`inflationweaver_demo.pine`](../tradingview/inflationweaver_demo.pine) embeds **synthetic 2023–2024 CPI data**. It demonstrates the workflow; its output is not a TÜİK or ENAG measurement. For meaningful results, regenerate with verified source data.

## Generate and open the indicator

After installing the repository package:

```bash
inflationweaver pine \
  --inflation examples/data/demo_cpi.csv \
  --symbol BIST:XU100 \
  --currency TRY \
  --base-date 2023-01-01 \
  --alignment observation \
  --max-staleness-days 62 \
  --source "synthetic demonstration" \
  --synthetic \
  --out reports/inflationweaver.pine
```

1. Open a standard **daily** TradingView chart for your chosen asset. Weekly and monthly charts are also supported as end-of-bar snapshots.
2. Open Pine Editor, create a new indicator, and replace its contents with the generated file.
3. Save, compile, and add it to the chart. The repository does not contain a local TradingView compiler.
4. In the indicator settings, select the asset symbol, requested base date, age limit, and display mode.
5. Read the **actual base date**, CPI source/series, valuation date, observation age, and status in the table before interpreting returns. With the demonstration file, inspect 2023–2024; current dates eventually have stale CPI and produce gaps.

For your own data, replace the path and source label and omit `--synthetic` when the data is an unmodified real series. Currency labels must describe the asset's quote currency and the purchasing-power CPI used. An asset quoted in USD needs USD CPI, or you must convert its price to TRY before applying TRY CPI in Python. The generated indicator refuses known quote-currency mismatches; it does not perform FX conversion.

The generator embeds all supplied rows. Filter the CSV explicitly before exporting a shorter period; the CLI rejects `--start-date` and `--end-date` for Pine rather than silently ignoring them.

## Input contract and alignment

```csv
date,value,available_date
2023-01-01,100.0,2023-02-03
2023-02-01,102.5,2023-03-03
```

These numbers and publication dates are an illustrative example. Supply real CPI **levels**, not annual inflation percentages. Observations must have unique, increasing ISO dates and positive finite values. `available_date` is optional for the retrospective view; it is mandatory for released alignment and cannot precede the observation date.

| Alignment | Eligible CPI observation | Purpose |
| --- | --- | --- |
| `observation` | Latest observation date on or before the valuation date | Retrospective purchasing-power comparison |
| `released` | Newest observation whose explicit availability date is on or before the valuation date | Comparison that respects supplied publication dates |

Released alignment consolidates multiple releases on the same date to the newest observation period. A delayed publication of an older period does not replace a newer period already available. Staleness is measured from the **observation date**, consistently with the Python engine, rather than from the publication date.

Date-only release records do not establish an intraday publication time. The indicator therefore refuses intraday and nonstandard charts. Release-date alignment alone does not establish a point-in-time backtest: historical revisions require actual vintage data, and this format holds one version per observation period.

## Calculation and chart semantics

For an eligible asset price `P(t)`, CPI level `C(t)`, and the actual shared base `b`:

```text
nominal_index(t) = 100 × P(t) / P(b)
real_index(t)    = nominal_index(t) × C(b) / C(t)
real_price(t)    = P(t) × C(b) / C(t)
real_return(t)   = real_index(t) - 100     [%]
```

The base is the first **loaded valid price/CPI pair** on or after the requested date. Nominal and real indices are both 100 there. A weekend, missing asset price, stale CPI, or limited TradingView history can move the actual base forward; the table exposes that movement. The “Base-date money” view uses the purchasing power of the actual base date, not automatically today's lira.

The same-timeframe asset request uses `barmerge.lookahead_off` and `barmerge.gaps_on`. CPI lookup is an explicit backward as-of search with no observation before the source begins. The last instant of a completed price bar determines its UTC valuation date. Weekly/monthly results therefore use each price bar's closing date and can differ from a daily chart's selected base. For an open price bar, the valuation time is capped at the current time so future embedded CPI is not selected; the price and returns can still change until that bar closes.

CPI remains constant between observations, so the real curve can jump at observation or release boundaries. This is expected for monthly source data. Missing price bars and CPI older than the configured limit create gaps, and real plots use `plot.style_linebr` to keep gaps visible. Nominal prices can still appear after CPI becomes stale because they do not need a new inflation observation.

An expression such as `BIST:XU100 / ECONOMICS:TRCPI` is a raw ratio to a provider's CPI **level** series. It does not itself establish a shared base, explain coverage, or supply ENAG history. Never divide a price by a year-over-year rate such as `40%` to represent purchasing power. TradingView's economic field list distinguishes `CPI` levels from `IRMM` and `IRYY` rates. [Official economic-data reference](https://www.tradingview.com/support/solutions/43000665359-what-economic-data-is-available-in-pine/).

## ENAG, TÜİK and long history

The embedded export does not depend on a presumed ENAG TradingView symbol, an automatic ENAG feed, or arbitrary HTTP calls from Pine. Import verified ENAG levels, or compound verified **consecutive monthly percentage changes** with `chain_monthly_rates` and an explicitly chosen preceding-month anchor. Annual percentages cannot uniquely reconstruct a monthly CPI history. Supply the anchor's availability date yourself if you need released alignment; the engine leaves unknown availability missing.

A chart requested from **1986** works only when both trustworthy source levels and actual asset bars exist for that period. ENAG history must not be extended into decades before its published source coverage. To show older TÜİK data followed by ENAG, explicitly splice two level series at a shared observation date and label the result a synthetic methodological hybrid:

```python
from pathlib import Path

from inflationweaver.engine import splice_cpi
from inflationweaver.pine import generate_pine
from inflationweaver.providers import read_csv

official = read_csv("data/tuik_levels.csv", "TUIK:CPI", kind="cpi", source="verified TÜİK export")
enag = read_csv("data/enag_levels.csv", "ENAG:CPI", kind="cpi", source="verified ENAG export")
# Replace this example with an actual same-date observation present in BOTH inputs.
hybrid = splice_cpi(official, enag, splice_date="2023-01-01")
Path("reports").mkdir(exist_ok=True)
Path("reports/hybrid.pine").write_text(
    generate_pine(hybrid, asset_symbol="BIST:XU100", base_date="1986-01-01"),
    encoding="utf-8",
)
```

The splice rescales the right series at the shared observation and uses it only afterwards. It makes no claim that different inflation methodologies are interchangeable. Keep original source files, the splice date, and provenance alongside the generated indicator. A CSV with metadata sidecars must be opened with matching series identifiers/source labels, as explained in [the data documentation](data-sources.md).

## Export and verification limits

The generator limits exports to **2,000 source CPI observations**, ample for roughly 166 years of monthly data. Four arrays retain observation dates, availability dates, effective dates and levels. Chunked strings of 40 rows are parsed once on the first bar, while binary lookup avoids scanning the whole table on every price bar. This repository limit is deliberately conservative; it is not a guarantee that every possible input will fit TradingView's compiler and runtime budgets.

TradingView still controls available chart history, account limits, source licensing, compilation size, execution time and memory. The file contains a deterministic checksum and source metadata so regenerated results are auditable; it never automatically refreshes embedded CPI. Regenerate after each new observation or revision.

Python tests validate reproducibility, embedded date/value round trips, release ordering, stale-data and missing-pair guards, symbol/metadata escaping, and export bounds. **Generated Pine code has not been compiled or executed in TradingView as part of the local test suite.** Final validation requires Pine Editor compilation plus a manual comparison of a few identical daily price/CPI pairs against the Python engine. Loading a different history range or choosing a different timeframe can change the actual base.

Official references: [Pine v6 manual](https://www.tradingview.com/pine-script-docs/welcome/), [arrays](https://www.tradingview.com/pine-script-docs/language/arrays/), [request and timeframe behavior](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/), [UTC time semantics](https://www.tradingview.com/pine-script-docs/concepts/time/), and [platform limits](https://www.tradingview.com/pine-script-docs/writing/limitations/).
