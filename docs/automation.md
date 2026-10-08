# Validation and source updates

The validation workflow runs Python tests on 3.11, 3.12 and 3.13, Ruff, synthetic CLI
workflows, package builds, and the dashboard's tests, typecheck and production build.
These checks do not contact paid data sources or compile Pine on TradingView.

`data-update.yml` supports a manual run and a Monday 07:15 UTC schedule. Its default
manifest imports **synthetic fixtures only**. Replace that manifest with your own
audited CSV/FRED/OECD/EVDS-compatible definitions and configure repository variable
`INFLATIONWEAVER_UPDATE_MANIFEST` to its tracked relative path. Store FRED/EVDS keys
in GitHub Actions secrets `FRED_API_KEY` and `EVDS_API_KEY`. Never commit keys or
private data. The workflow uploads the refreshed Parquet/DuckDB store and a separate
synthetic smoke report as an artifact; it does not commit market data to the repository.

Manifest schema version is `1`. Each `series` item supplies `series_id`, `provider`,
`kind`, `currency`, and an explicit store `mode`. CSV items use `path` relative to the
manifest, `source`, and `synthetic`; FRED/EVDS items use `start` and `end`; OECD items
use the explicit official `url` and exact dimension `filters`. Use consistent units,
seasonal-adjustment flags and data vintages. Source fetching has not been tested
with your credentials. EVDS2 compatibility is documented in [data-sources.md](data-sources.md).

Updates are ordered. Each successfully written series is committed independently;
a later error stops the run and returns failure, without rolling back preceding
series. Published provider revisions require an explicit `replace` or `update` mode;
`error` is the safe default. `append` does not overwrite old observations. Every
stored series retains source metadata and a checked Parquet SHA-256 checksum.

GitHub schedules execute only after the workflow exists on the default branch and
can be delayed or disabled by GitHub. A downloaded repository does not itself
activate a scheduled job. Offline tests use mocked provider responses. Installing
from `requirements.lock` and `web/package-lock.json` recreates the validated dependency
versions; upgrade deliberately and rerun the checks.
