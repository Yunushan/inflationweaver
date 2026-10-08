# Web analysis workspace

Start the Next.js app in [`web/`](../web/README.md). The workspace includes an interactive TradingView Lightweight Charts™ plot, nominal/real/CPI indices, nominal and real drawdowns, cumulative returns, CAGR, purchasing-power measurements, a second-asset comparison, source descriptions, an accessible observation table, and CSV/JSON exports.

## Data entry

The initial equity, gold and CPI histories are **fictional, synthetic demonstrations**, covering 2016–2025. They are not historical XU100, ENAG, TÜİK, gold or any other market values. Their sources and synthetic flags remain visible in the UI and exports.

Use **Bring your own history** to select an asset or CPI series. A CSV must have `date,value` headers; `available_date` is optional for retrospective analysis and mandatory on every observation in released mode. The uploader's form supplies series ID, currency, type, source description and synthetic status. Values use a decimal point with no thousands separators. Quoted CSV syntax is supported by Papa Parse. Duplicate dates, invalid dates, non-positive/non-finite values, malformed files and excess columns produce an explicit error.

```csv
date,value,available_date
2024-01-31,100.0,2024-02-03
2024-02-29,105.5,2024-03-03
```

A full JSON series supplies its own metadata, which overrides the import form:

```json
{
  "series_id": "MY_PRICE_TRY",
  "kind": "price",
  "currency": "TRY",
  "source": "Provider export; include series code, extraction date and adjustment policy",
  "synthetic": false,
  "data": [
    {"date": "2024-01-31", "value": 100.0, "available_date": "2024-01-31"},
    {"date": "2024-02-29", "value": 105.5, "available_date": "2024-02-29"}
  ]
}
```

A JSON array of observations uses the metadata from the form. Asset types are `price` and `wealth`; CPI requires `cpi` index levels. Monthly/annual inflation percentages need conversion to index levels before dashboard import. Use the Python rate-chaining tools for monthly rates; annual rates alone do not identify a unique monthly index path.

The app accepts BIST shares and indices, international shares/indices, FX-valued assets, gold and silver, crypto, funds/ETFs, deposit/bond wealth indices and housing indices through the same generic value-series contract. Provider connectivity and data licensing are separate from numerical support. Values from 1986 or earlier are allowed when the supplied histories actually cover the period. This dashboard does not invent earlier ENAG observations or implicitly splice ENAG and official CPI.

Uploads are limited to 12 MB and 50,000 observations per series. Imported series are held in browser memory. Reload clears them; downloaded reports persist only where the user saves them.

## Calculation controls

| Control | Meaning |
| --- | --- |
| Base date | Normalize to the first eligible asset observation on or after this date. An asset gap larger than the configured maximum age causes an error. |
| Display start | Crop the chart/table. With an explicit earlier base, metrics and drawdowns still cover base through end. Without an explicit base, display start becomes the requested base. |
| End date | Use observations on or before this date. |
| Observation alignment | Retrospective view, matching the latest CPI observation period at/before the asset date. Later publications can appear in this view. |
| Released alignment | Use asset availability dates as decision dates. Match the latest CPI period published by that date. Availability dates are required for both series. |
| Maximum CPI age | Reject a CPI observation older than this number of days measured from its observation period. Default 62 days. |
| Comparison | Analyze another asset over shared base/end decision dates. At least two shared dates are required. Different intermediate frequencies are allowed; the endpoints and normalization are shared. |

An asset must be expressed in the same currency as the CPI basket. Convert the asset before import to assess Turkish purchasing power for USD assets, for example. A generic price series reflects prices only; total returns need adjusted prices or a wealth index that includes distributions, fees and the relevant cash-flow policy.

The formulas are:

```text
nominal_index = 100 × asset_value / asset_value_at_base
inflation_index = 100 × CPI / CPI_at_base
real_index = 100 × nominal_index / inflation_index
real_value = asset_value × CPI_at_base / CPI
real_return_pct = real_index_at_end − 100
drawdown_pct = 100 × (current_index / running_peak − 1)
CAGR_pct = 100 × ((end_index / base_index)^(365.2425 / elapsed_days) − 1)
```

CAGR is undefined for a zero-day period. All drawdown fields use percentage units: `-15` means a 15% drawdown. Running peaks are separate for nominal and real indices. Missing/stale data is rejected; it is never interpolated from future observations.

## Local and API execution

With `NEXT_PUBLIC_API_URL` empty, a deterministic TypeScript reference calculator processes data in the browser. No uploaded file is transmitted. Its calculation tests cover inflation compounding, released timing, baseline/display separation, stale data, coverage gaps, invalid dates and unit consistency.

When configured, the app posts the complete selected series to `/v1/analyze` on that API origin. Configure CORS on the FastAPI server to include the dashboard origin. `NEXT_PUBLIC_` configuration is embedded at build time. Only set a trusted API origin, especially for proprietary portfolios. A failed API request produces an explicit error; it does not silently switch calculation engines.

The dashboard reports the actual base/end and selected source metadata. The JSON report includes metrics, aligned points and source provenance; CSV includes aligned primary-asset points, series IDs and the synthetic flag. The displayed table is paginated in 12-observation pages, and exports include the entire validated display range.

## Dependency licensing

First-party files are 0BSD. TradingView Lightweight Charts™ uses Apache-2.0 and requires its own public attribution/link; the dashboard and notices directory retain those. Next.js, React and Papa Parse retain MIT licenses. See [`web/licenses/`](../web/licenses/README.md).
