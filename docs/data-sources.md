# Data sources and reproducible imports

InflationWeaver supplies an analysis engine and ingestion adapters. It does not
bundle historical market feeds, a complete ENAG archive, or a 1986-to-present
dataset. The catalog lists instruments and their interpretation; listing an
instrument does not download it. All bundled CSV values are **synthetic demos**.

## Canonical CSV contract

CSV is UTF-8, comma-delimited, with decimal points. Observation dates use
`YYYY-MM-DD`; a `YYYY-MM` monthly period is accepted and normalized to its first
day. Choose an observation convention consciously. A month's first-day label
does not mean its inflation number was available on that day.

| Column | Meaning | Requirement |
|---|---|---|
| `date` | Economic observation date/period | Required, unique |
| `value` | Level, or published MoM percentage when `kind=monthly_rate` | Required, finite |
| `available_date` | Actual first public availability of that exact observation/vintage | Optional; blank/unknown values are preserved. Known dates cannot precede `date`; released alignment requires a known date for every observation |
| `published_mom` | Original reported monthly percentage retained as evidence | Optional; never substituted for index level |
| `published_yoy` | Original reported annual percentage retained as evidence | Optional; never compounded as monthly inflation |
| `source_url` | Release or downloadable source supporting the row | Optional; preserved |

Other columns are preserved. Blank numerical observations, duplicate dates,
nonfinite values and nonpositive levels are rejected. Importing several series
or vintages under one identifier is an error. Published monthly rates can be
negative but must exceed -100%.

The following rows are illustrative, not official observations:

```csv
date,value,available_date,published_mom,published_yoy,source_url
2024-01-01,100,2024-02-05,3.2,70,https://example.com/release-2024-01
2024-02-01,104,2024-03-04,4.0,72,https://example.com/release-2024-02
```

Supply metadata explicitly:

```python
from inflationweaver.providers import read_csv, write_csv
from inflationweaver.store import SeriesStore

cpi = read_csv("my-cpi.csv", "MY_CPI", kind="cpi", currency="TRY",
               source="official release archive", synthetic=False)
store = SeriesStore("var/data")
store.write(cpi)                       # rejects overwriting an existing ID
store.write(cpi, mode="replace")       # explicit complete replacement
write_csv(store.read("MY_CPI"), "exports/my-cpi.csv")
```

`write_csv` adds `my-cpi.csv.metadata.json` with the series ID, kind, currency,
source, synthetic flag, row count and SHA-256 of the exported bytes. `read_csv`
verifies an existing sidecar and rejects mismatched metadata. When reading an
export, pass the same metadata arguments that were used to write it.

## Official-provider adapters

| Adapter | Implemented contract | Important limit |
|---|---|---|
| FRED | Official `fred/series/observations` JSON; levels, pagination, missing `.` values skipped | Requires `FRED_API_KEY`; current vintage is not publication history |
| EVDS2 compatibility | One explicitly selected series; documented path parameters; key in HTTP header | Legacy contract only; current portal is EVDS3, live compatibility not verified |
| OECD SDMX | User-selected official CSV query plus explicit dimension filters | No universal hardcoded CPI dataset mapping; duplicate dates after filtering rejected |
| ENAG/TÜİK manual | Canonical CSV with source evidence and actual release dates | No invented backfill; annual percentages do not recover monthly observations |

HTTP errors are sanitized so credential-bearing URLs are not emitted. Redirects
are rejected, including legacy EVDS redirects; credentials are not forwarded to
a replacement endpoint. Requests have a 30-second timeout. No provider key is
written to the store or manifest. Adapter tests mock official response contracts
and do not establish live availability or account entitlement.

### FRED

```python
from inflationweaver.providers import fetch_fred

# Read FRED_API_KEY from the environment. Never put it in a committed manifest.
us_cpi = fetch_fred("CPIAUCSL", "1986-01-01", "2024-12-31")
```

`CPIAUCSL` is seasonally adjusted; `CPIAUCNS` is a different choice. Select the
series according to the intended interpretation. The adapter requests
`units=lin` and never silently transforms a level into a percentage. It keeps
the observation date but deliberately omits `available_date`: a current-vintage
response's `realtime_start` is **not** the first release date of an observation.
Released-data analysis requires a separate audited release/vintage dataset.

Sources: [FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html),
[FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html),
[FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).

### TCMB EVDS compatibility

```python
from inflationweaver.providers import fetch_evds

# Read EVDS_API_KEY from the environment. Dates below are supplied in ISO form;
# the adapter renders startDate/endDate as DD-MM-YYYY for the documented service.
usdtry = fetch_evds("TP.DK.USD.A.YTL", "2024-01-01", "2024-12-31",
                   kind="fx", currency="TRY/USD")
```

The implementation targets the documented EVDS2
`https://evds2.tcmb.gov.tr/service/evds/series=...&startDate=...&endDate=...&type=json`
contract and sends the API key only in the `key` request header. It uses native
frequency and requests levels (`formulas=0`). The caller must verify the chosen
series' meaning, buying/selling side, currency and frequency.
An FX series declares its quote direction in `currency`: `TRY/USD` means TRY
per one USD, `TRY/EUR` means TRY per one EUR, and `TRY/CHF` means TRY per one CHF.
This is the metadata contract used by the engine's currency conversion.

**Current endpoint limitation:** TCMB operates the EVDS3 portal. During source
review, the old official EVDS2 usage-guide URL redirected to EVDS3. The project
does not claim the legacy service works live or that an undocumented EVDS3
route has been implemented. If the legacy request redirects or fails, export
the desired data from the current official portal and import it as CSV. Add a
new adapter only against an accessible official contract and real account
verification. No route or authentication format is guessed.

Sources: [TCMB EVDS3](https://evds3.tcmb.gov.tr/),
[current EVDS documentation](https://evds3.tcmb.gov.tr/dokumanlar),
[legacy official web-service guide URL](https://evds2.tcmb.gov.tr/help/videos/EVDS_Web_Service_Usage_Guide.pdf),
[TCMB announcement of the renewed system](https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Duyurular/Basin/2026/DUY2026-03).

### OECD SDMX

Use the [OECD Data Explorer](https://data-explorer.oecd.org/) query builder to
select a dataset, country, frequency, unit, adjustment and measure. Copy its
actual query and choose `format=csvfile` or `format=csvfilewithlabels`. Schema
keys differ by dataset; do not infer country/measure positions from an unrelated
example. `fetch_oecd` permits HTTPS on `sdmx.oecd.org` only and requires an
explicit nonempty filter mapping.

```python
from inflationweaver.providers import fetch_oecd

# url is the exact current query copied from the official builder.
# Dimension names and values must match that query's actual CSV schema.
cpi = fetch_oecd(url, "OECD_SELECTED_CPI",
                 {"REF_AREA": "TUR", "FREQ": "M"}, currency="TRY")
```

Filter every dimension needed to isolate one series. If several rows remain on
a date, the adapter fails and requests a narrower selection. Units/base year,
seasonal adjustment and revision history still require checking against the
dataset's metadata. Quarterly/yearly period strings are not silently expanded
into fabricated monthly data.

Sources: [OECD API](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html),
[OECD API best practices](https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html).

## ENAG, TÜİK and history beginning in 1986

Keep ENAG and TÜİK as distinct named sources. For ENAG published MoM rates, use
`kind=monthly_rate`, `value` in percent (for example `4.5`, not `0.045`) and the
actual release date. Keep `published_yoy` as a separate column. Use
`chain_monthly_rates` with an explicit anchor to construct levels only across
consecutive observed months. Missing months must be supplied from source
evidence; yearly rates cannot fill them. The anchor's normalization to 100 is a
choice of units, not an actual provider-reported index level.

TÜİK has published rebased and revised CPI series. The current official source
uses a 2025=100 base; historical exports may use 2003=100 or another base. Do not
concatenate different bases without an explicit audited overlap/splice. Keep
the vintage and release calendar of each input; today's revised history is not
automatically the history investors knew at each historical date.

An analysis requested from 1986 can run only where the selected asset, inflation
and currency inputs actually overlap. Historic BIST continuity, share splits,
dividends, index methodology and pre-2005 currency units need source-specific
handling. Later-created ETFs, cryptocurrencies and funds cannot have real 1986
prices. ENAG's modern publication history cannot substantiate an ENAG series
back to 1986. An explicitly spliced TÜİK→ENAG series is a **hybrid**, not a
historical ENAG series. The core rejects missing requested historical coverage
instead of making a chart appear complete.

Sources: [TÜİK official data portal](https://veriportali.tuik.gov.tr/),
[TÜİK current economic indicators](https://www.tuik.gov.tr/Turcat),
[TÜİK revision history](https://takvim.tuik.gov.tr/Kurumsal/Gecmis_Yil_Revizyonlari),
[ENAG's own December 2020 bulletin](https://enagrup.org/bulten/aralik2020.pdf).

## Local persistence and update manifests

`SeriesStore` writes Zstandard-compressed Parquet objects and a DuckDB metadata
catalog. IDs and paths are bound values in SQL, not executable query text.
Stored object paths must remain under the store's `objects` directory. A read
verifies its SHA-256 before opening the file. Each write creates a new object
and switches the catalog reference in a transaction; old objects remain for
manual recovery. It does not automatically restore arbitrary older versions.

| Write mode | Existing identifier behavior |
|---|---|
| `error` (default) | Refuse overwrite |
| `replace` | Entire input replaces the active series and metadata |
| `append` | Only later dates; metadata must match |
| `update` | Replace overlapping dates and retain others; metadata must match |

Metadata includes row count, covered dates, full column list, release-date
presence, source, synthetic flag, checksum, UTC creation/update times and prior
checksum. `manifest.json` snapshots the DuckDB catalog for inspection. DuckDB is
the authoritative catalog; the manifest is not a transaction log. Use a single
writer per store. This local design is not a clustered database.

`examples/series.json` declares local CSV series. Paths are relative to the
manifest directory. `examples/update-manifest.json` adds `provider: csv` and an
explicit `mode: replace` to repeatably load the synthetic fixtures. Example:

```json
{
  "schema_version": 1,
  "description": "SYNTHETIC DEMO ONLY",
  "series": [
    {
      "series_id": "DEMO_XU100",
      "provider": "csv",
      "path": "data/demo_asset.csv",
      "kind": "price",
      "currency": "TRY",
      "source": "synthetic-demo",
      "synthetic": true,
      "mode": "replace"
    }
  ]
}
```

The 0BSD license applies to this project's code and original synthetic
fixtures. Imported third-party data keeps its own provider terms; the software
license does not grant redistribution rights to commercial price feeds.
