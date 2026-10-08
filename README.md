# InflationWeaver

**Inflation adjustment, purchasing-power measurement, and real-return analytics for financial time series.**

InflationWeaver answers a practical question: **how much did an investment gain after inflation, in the currency and consumer basket that matter to you?** Its first use case is BIST 100 analysis from 1986 onward, using separately identified TÜİK, ENAG, or an explicitly constructed TÜİK–ENAG hybrid. The same calculation engine accepts equities, indices, currencies, metals, crypto, funds, deposits, bonds, housing indices, and strategy equity curves.

[Türkçe](README.tr.md) · [Methodology](docs/methodology.md) · [Data sources](docs/data-sources.md) · [1986 history guide](docs/history-1986.md) · [Requirement coverage](docs/requirements.md) · [Architecture](docs/architecture.md) · [Verification](docs/verification.md) · [0BSD license](LICENSE)

## What is included

Version **0.1.0** is a working, local-first analytics repository with a Python package and CLI, Polars calculation engine, Parquet storage and DuckDB catalog, FastAPI service, TypeScript/Next.js dashboard with TradingView Lightweight Charts, Pine Script v6 generation, data-provider adapters, tests, and GitHub Actions workflows.

| Capability | Behavior |
| --- | --- |
| Inflation engine | Positive CPI levels, monthly compounding, rebasing, and hybrid chaining with an explicit overlap |
| Real returns | Nominal and real growth, cumulative return, CAGR, drawdown, and purchasing-power metrics |
| History | Arbitrary verified input dates, including 1986 onward; unavailable coverage is reported rather than invented |
| Validation | Schema, duplicate dates, finite/positive levels, monthly-rate continuity, CPI staleness, and metadata checks |
| Comparisons | Common-date, common-currency benchmark comparisons and fixed-unit portfolios |
| Integrations | CLI, Python API, REST API, CSV/JSON reports, Pine generation, and strategy-equity adapter |
| Data updates | Explicit local/provider manifests suitable for a scheduled workflow |

**Historical data is a separate input.** The bundled examples are clearly marked **synthetic demonstration data**, not genuine XU100, TÜİK, ENAG, or investment performance. No licensed 1986–2026 market database is included. There is no automatic universal market downloader. Each real analysis needs verified input history and the necessary access rights. ENAG does not provide a 1986 history; a long hybrid series is an analytical construction, not an official ENAG historical series.

## Quick start

Requirements: Python **3.11+**. The dashboard additionally requires Node.js **22.18+** and npm; validation used Node.js 24. Run commands from the repository root. Python wheels contain the backend; use the full repository archive for the dashboard, workflows, and examples.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .

inflationweaver demo --out reports/demo
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. The pinned `requirements.lock` recreates the validated dependency versions. For development against compatible newer dependencies, `python -m pip install -e '.[dev]'` is the flexible alternative (`".[dev]"` on PowerShell); rerun the checks after changing versions.

The demo provides a reproducible starting point without provider credentials. It writes `analysis.csv`, `analysis.json`, `report.md`, and demo input CSVs with checksum-bearing metadata sidecars. Output carries synthetic labels; changing a filename or series identifier does not turn demonstration values into historical evidence.

Analyze the bundled inputs explicitly:

```bash
inflationweaver analyze \
  --asset examples/data/demo_asset.csv \
  --inflation examples/data/demo_cpi.csv \
  --base-date 2023-01-01 \
  --synthetic \
  --out reports/analysis
```

Discover the full supported options with `inflationweaver --help` and `inflationweaver <command> --help`.

The Python API uses the same explicit input contracts:

```python
from inflationweaver.engine import analyze
from inflationweaver.providers import read_csv

asset = read_csv(
    "examples/data/demo_asset.csv", "DEMO_XU100",
    source="synthetic-demo", synthetic=True,
)
cpi = read_csv(
    "examples/data/demo_cpi.csv", "DEMO_CPI", kind="cpi",
    source="synthetic-demo", synthetic=True,
)
result = analyze(asset, cpi, base_date="2023-01-01")
print(result.metrics["real_return_pct"])
payload = result.to_dict()  # points, metrics, metadata; ISO dates
```

## Use your own verified data

The canonical CSV contract uses decimal points and ISO dates:

```csv
date,value
2023-01-01,100.0
2023-02-01,102.0
2023-03-01,104.5
```

These example numbers illustrate the format only. They are not actual CPI values. `YYYY-MM` dates are normalized to the first day of the month. A price input can use daily dates. Monthly-rate chaining requires every consecutive observation month. CPI-level analysis uses backward as-of matching and a configurable age limit, so a missing month within that limit can still be accepted; inspect source frequency and gaps separately. CSV readers preserve additional columns such as `published_mom`, `published_yoy`, and `source_url`; these do not automatically change a series from levels to inflation rates.

For publication-aware analysis, provide the **actual public availability date** for every observation. Unknown dates may remain blank in storage/CSV, but released alignment rejects them:

```csv
date,value,available_date
2023-01-01,100.0,2023-02-03
2023-02-01,102.0,2023-03-03
2023-03-01,104.5,2023-04-03
```

The dates and numbers above are illustrative. Observation month and publication date are different concepts. Do not infer availability from the month label or a generic lag.

Store a supplied asset series:

```bash
inflationweaver import \
  --file examples/data/demo_asset.csv \
  --id DEMO_XU100 \
  --kind price \
  --currency TRY \
  --synthetic
```

For real data, use your own file and identifier and omit `--synthetic`. Supply trustworthy metadata through the import/update contract; the software cannot independently certify the origin of an arbitrary user file. Exported CSV sidecars contain metadata and a SHA-256 checksum. A checksum detects changes; it does not prove that a provider published a value.

### Provider coverage

| Source | Included route | What you must supply |
| --- | --- | --- |
| TÜİK | Canonical CSV import; EVDS compatibility adapter for a verified series | Correct CPI level series, base history, releases, and any older-series links |
| ENAG | Canonical CSV import | Verified monthly E-TÜFE changes or a documented constructed level series; source references and release dates |
| FRED | Authenticated observations adapter | API key, exact series ID, units, currency, and vintage/release policy |
| OECD | SDMX CSV adapter with explicit dimension filters | An actual query URL and one unambiguous series selection |
| TCMB EVDS | Single-series EVDS2 compatibility adapter | API key and exact series code; verify service availability and contract |
| Market feeds | Canonical CSV import | Licensed or otherwise authorized price/total-return history, currency, and corporate-action treatment |

Provider API responses are **latest-vintage** unless independently prepared otherwise. The FRED adapter is not an ALFRED vintage archive. A supplied `available_date` avoids using a release before that date, but does not by itself reverse later data revisions. Provider failures, redirects, and ambiguous series selections are errors, not reasons to substitute another inflation measure silently. Current and older TÜİK CPI reference bases must be checked from source metadata rather than assumed; a historical 2003-base file and a newer 2025-base release need an explicit verified connection.

An authenticated FRED import can be described by a reviewed manifest:

```json
{
  "schema_version": 1,
  "series": [
    {
      "provider": "fred",
      "series_id": "CPIAUCNS",
      "kind": "cpi",
      "currency": "USD",
      "start": "2000-01-01",
      "end": "2025-12-31",
      "mode": "error"
    }
  ]
}
```

Save this as your own manifest, supply `FRED_API_KEY` in the process environment, and run `inflationweaver update --manifest my-fred-manifest.json`. `CPIAUCNS` is the [monthly, not seasonally adjusted US CPI level](https://fred.stlouisfed.org/series/CPIAUCNS); it is not a Türkiye CPI series. Use `--store` to choose the destination. Existing data requires an intentional store mode, such as a reviewed `replace` or `update`, rather than silent overwrite. See [data sources](docs/data-sources.md) for provider contracts and [automation](docs/automation.md) for manifest/workflow behavior.

## Which assets can be analyzed?

The engine works on validated positive level/equity series. The categories below describe supported input and analysis, not a promise of bundled live quotes.

| Asset group | Examples | Required interpretation |
| --- | --- | --- |
| Türkiye indices | XU100, XU030, XBANK | Price versus return index; consistent historical scale |
| BIST equities | THYAO, TUPRS, ASELS, ISCTR | Splits, rights issues, dividends, and delisted-history handling |
| Inflation indices | TÜİK CPI, ENAG E-TÜFE, US CPI | CPI level versus monthly change; basket and seasonal adjustment |
| Foreign exchange | USD/TRY, EUR/TRY | Explicit quote direction; conversion into the comparison currency |
| Precious metals | Gram gold, ounce gold, silver | Quote currency, weight unit, and metal product |
| US indices | S&P 500, Nasdaq 100, Dow Jones | Price/total-return basis and USD-to-TRY conversion where relevant |
| Crypto | BTC, ETH | Currency, venue, observation time, and exchange coverage |
| Funds and ETFs | SPY, QQQ, TEFAS funds | NAV/adjusted price, distributions, fees, and inception date |
| Interest and bonds | Deposits, government bonds | Value or total-return curves; an interest/yield quote alone is not a price |
| Real estate | Türkiye housing price index | Aggregate index rather than an individual property's investable return |

For Turkish purchasing power, first express the investment in **TRY**, then deflate with the chosen Turkish CPI. An unconverted USD asset divided by Turkish CPI does not measure Turkish purchasing power. A USD asset deflated by US CPI answers a different, valid question. Fees, withholding tax, income, and spread must already be reflected in an input equity/value curve if they are to appear in the result.

## The calculation

For asset value `P(t)`, inflation level `C(t)`, and selected base observation `b`:

```text
nominal growth(t) = P(t) / P(b)
inflation factor(t) = C(t) / C(b)
real growth(t) = nominal growth(t) / inflation factor(t)
real return(t) = real growth(t) - 1
real value in base-date money(t) = P(t) × C(b) / C(t)
```

If the asset rises from 100 to 150 and CPI rises from 100 to 125, nominal return is 50% and real return is **20%**, because `1.50 / 1.25 - 1 = 0.20`. Subtracting inflation from nominal return would give 25% and is not the exact compounded result.

Monthly inflation changes compound multiplicatively. Year-over-year rates cannot be compounded as monthly observations. The arbitrary CPI base cancels in ratios; the **comparison base date**, currency, basket, and release timing remain consequential. See [methodology](docs/methodology.md) for the complete conventions.

## XU100 from 1986

[Borsa İstanbul's XU100 record](https://www.borsaistanbul.com/en/index/xu100) identifies **1 January 1986** as the index start date. That is a reference date, not a guarantee of a trading observation on that day. Select an actual supplied observation and verify that the input provider consistently adjusts historical scale changes.

To run an analysis beginning in 1986, provide continuous compatible historical CPI and verified XU100 data covering the requested interval. The program must not extend ENAG backward, fill missing decades, compound annual headline rates into a fake monthly history, or treat the index's rescaling as investment losses. Follow [the historical-data checklist](docs/history-1986.md) before interpreting a result.

A TÜİK–ENAG hybrid uses TÜİK before a documented switch and ENAG afterward, scales the successor at a validated common observation, and preserves its hybrid identity. It is useful for a stated analytical scenario; it is not a single official basket observed since 1986. Compare separate TÜİK and ENAG/hybrid results when studying sensitivity.

The synthetic fixtures also demonstrate monthly compounding and an explicit switch:

```bash
inflationweaver chain \
  --rates examples/data/demo_enag_mom.csv \
  --anchor-date 2022-12-01 \
  --synthetic \
  --out reports/demo_enag_chained.csv

inflationweaver splice \
  --left examples/data/demo_cpi.csv \
  --right reports/demo_enag_chained.csv \
  --splice-date 2023-01-01 \
  --synthetic \
  --out reports/demo_hybrid.csv
```

These commands exercise the algorithm with invented inputs. For real data, choose the anchor and common switch from verified history. The constructed anchor's availability is unknown; supply a justified date before using released alignment.

## Dashboard and REST API

Start the local API:

```bash
inflationweaver serve
```

Open its generated API documentation at <http://127.0.0.1:8000/docs>. The API includes health, catalog and series retrieval, analysis, asset comparison, and fixed-unit portfolio calculation:

| Route | Purpose |
| --- | --- |
| `GET /health` | Service health |
| `GET /v1/catalog` | Supported series definitions and categories |
| `GET /v1/series` | Imported local series list |
| `GET /v1/series/{id}` | One stored local series |
| `POST /v1/analyze` | Inflation-adjusted analysis |
| `POST /v1/compare` | Common-basis asset comparison |
| `POST /v1/portfolio` | Fixed-unit portfolio valuation and real returns |
| `POST /v1/cpi/chain` | Convert verified monthly percentages to CPI levels |
| `POST /v1/cpi/splice` | Construct an explicitly identified CPI hybrid |
| `POST /v1/backtest` | Analyze a strategy equity curve and beginning-period cashflows |

Then start the web application in another terminal:

```bash
cd web
npm ci
npm run dev
```

Open <http://localhost:3000>. The dashboard supports CSV/JSON analysis, CPI mode and base-date selection, charts, metrics, comparison, and exports. The bundled demo is visibly synthetic. With `NEXT_PUBLIC_API_URL` empty, its TypeScript reference calculator runs in the browser and uploaded inputs remain there. To use the Python service, set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in `web/.env.local` before starting/building the app; full selected series are then sent to that configured origin. Copy `web/.env.example` for the documented setting. The Python `.env.example` lists provider-key, storage, and CORS variables; load them explicitly in your shell or process manager.

The default service is intended for local use. Shared deployments require an authentication layer, TLS, request limits, deliberate CORS settings, and controlled persistent storage. See [dashboard usage](docs/dashboard.md) and [SECURITY.md](SECURITY.md).

## TradingView / Pine Script v6

Generate an inflation-aware indicator from a supplied CPI series:

```bash
inflationweaver pine \
  --inflation examples/data/demo_cpi.csv \
  --symbol BIST:XU100 \
  --synthetic \
  --out reports/inflationweaver.pine
```

Paste the generated file into TradingView's Pine Editor and use **Add to chart**. An exported CPI series is embedded in the indicator; Pine cannot call this repository's Python API or freely fetch ENAG from the internet. Regenerate the script when the underlying inflation history changes.

Pine output is generated and checked locally; the repository does not claim live TradingView compilation or parity for every chart/timeframe. The export accepts standard daily, weekly, and monthly charts; intraday and nonstandard charts are refused. TradingView's available price history, script-size and execution limits, symbol availability, and the chosen CPI timing constrain what a chart can show. Historical real-return analysis should be verified against the Python output. Synthetic/constructed Pine exports carry a visible label. See [the TradingView guide](docs/tradingview.md).

## Updates, reports, and automation

```bash
inflationweaver update --manifest examples/update-manifest.json
```

The sample manifest imports only the bundled synthetic inputs. Use an explicit, reviewed manifest for real provider series. Relative file paths resolve from the manifest's directory. Keep credentials in environment variables or GitHub Actions secrets, and licensed data outside the public repository.

GitHub Actions covers code checks, tests, and reproducible demo/report generation. A data-update workflow can run configured imports on a schedule or manual dispatch. It requires a configured manifest, source rights and keys where applicable, and a persistent destination; the repository does not create a guaranteed continuously maintained database merely by being cloned.

## Develop and verify

```bash
python -m pytest
python -m ruff check .
python -m build

cd web
npm run typecheck
npm test
npm run build
```

Core tests target financial identities and failure boundaries: exact real-return ratios, compounding, date coverage, missing months, hybrid overlap, currency alignment, storage, API behavior, and generated Pine contracts. Network-provider tests use deterministic fixtures; a passing fixture test is not proof that an external provider is currently available.

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and [CHANGELOG.md](CHANGELOG.md) for releases. The screenshot proposals' V1/V2/V3 phases are capability groups rather than already published version numbers; [requirements](docs/requirements.md) maps every attachment row to this release and its data/operational dependencies.

## License and attribution

First-party InflationWeaver code and documentation are licensed under **BSD Zero Clause (`0BSD`)**, copyright © 2026 **Yunus ÇOĞAL**. You may use, copy, modify, and distribute this software for any purpose, with or without a fee. The complete license is in [LICENSE](LICENSE).

The 0BSD grant applies to this project's first-party work. It does not relicense imported datasets, upstream dependencies, provider APIs, exchange indices, trademarks, or credentials. TradingView Lightweight Charts is an upstream dependency with its own license and attribution requirements; the dashboard retains its notice and a link to TradingView. Consult provider terms before redistributing data or publishing derived products.

### Primary references

- [BLS: CPI percentage changes](https://www.bls.gov/cpi/factsheets/calculating-percent-changes.htm) and [purchasing power / constant dollars](https://www.bls.gov/cpi/factsheets/purchasing-power-constant-dollars.htm)
- [Borsa İstanbul: price versus return indices](https://www.borsaistanbul.com/en/faq/indices), [historical index data](https://www.borsaistanbul.com/en/index/index-data), and [index licensing](https://www.borsaistanbul.com/en/indices)
- [TÜİK inflation and prices](https://data.tuik.gov.tr/Kategori/GetKategori?p=enflasyon-ve-fiyat-106&dil=2), [ENAG](https://enagrup.org/), and [TCMB inflation data](https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb%2Ben/main%2Bmenu/statistics/inflation%2Bdata)
- [FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), and [OECD API guidance](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)
- [TradingView Lightweight Charts licensing](https://github.com/tradingview/lightweight-charts#license) and [SPDX 0BSD](https://spdx.org/licenses/0BSD.html)
