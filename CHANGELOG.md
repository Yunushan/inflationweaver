# Changelog

User-visible changes are recorded here. Version numbers identify software releases, not verified historical dataset releases.

## 0.1.0 — 2026-10-08

### Added

- Python/Polars series contracts, exact CPI-ratio real returns, normalized indices, base-money values, actual-day CAGR and nominal/real drawdowns.
- Monthly percentage-rate chaining with consecutive-month checks; exact-overlap CPI hybrid construction with explicit provenance.
- Backward as-of observation/released matching, explicit availability requirements and configurable CPI staleness.
- FX quote-direction validation, common-date multi-asset comparison, fixed-unit portfolios and a labeled gross constant-APR deposit illustration.
- Trading-bot net equity adapter with optional beginning-of-period external-flow unitization.
- Canonical CSV imports/exports with metadata/checksums, official-provider response adapters, Parquet/DuckDB local storage and update manifests.
- CLI, FastAPI/OpenAPI analysis routes, Next.js/TypeScript dashboard, TradingView Lightweight Charts and Pine Script v6 generation.
- Clearly synthetic examples, deterministic tests and GitHub Actions automation.
- English/Turkish README, full attachment requirement matrix, calculation methodology, architecture and 1986 historical-data preparation guide.
- First-party BSD Zero Clause (`0BSD`) license, copyright 2026 Yunus ÇOĞAL.

### Boundaries

No authentic 1986–2026 XU100/TÜİK/ENAG database is bundled. Latest-vintage provider responses are not an ALFRED point-in-time replay. Pine source generation is checked locally; live TradingView execution is not claimed. Shared authentication, deployment operations and source/data rights remain operator responsibilities.
