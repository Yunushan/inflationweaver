# Attachment requirements and implementation coverage

This matrix preserves all requirements from the five supplied project screenshots. It separates an implemented computational or integration route from acquisition of verified real-world data. Version **0.1.0** is the software release; the proposal's **V1.0 / V2.0 / V3.0** labels are development phases, not claims that those three production releases already exist.

**Implemented route** means code and examples are supplied. **Data-dependent** means verified historical input, rights, series choice, or provider access is still needed. Synthetic demonstrations establish that an algorithm can run; they do not establish authentic historical coverage.

## Attachment 1 — financial asset groups

| Requested group | Screenshot examples | Original priority | Implementation route | Real-data condition |
| --- | --- | --- | --- | --- |
| Türkiye indices | XU100, XU030, XBANK | Very high | Catalog metadata, CSV import, generic price analysis and comparison | Authorized history; scales; price/return basis |
| BIST equities | THYAO, TUPRS, ASELS, ISCTR | Very high | Catalog metadata, CSV input, common-currency analysis | Adjusted prices or wealth; corporate actions |
| Inflation indices | ENAG, TÜİK, US CPI | Very high | CPI levels, monthly-rate chaining, hybrid overlap; CSV and official-provider adapters | Verified rates/levels, source basket, releases/vintages |
| FX | USD/TRY, EUR/TRY | High | FX series, validated multiply/divide conversion | Correct quote-unit metadata and dates |
| Precious metals | Gram gold, ounce gold, silver | High | Generic price series and comparisons | Consistent weight unit, currency, product |
| US indices | S&P 500, Nasdaq 100, Dow Jones | High | Generic price/wealth analysis and FX conversion | Source-specific history; dividend basis |
| Crypto | BTC, ETH | High | Generic series and common-date comparisons | Venue, currency, observation time, valid history |
| Funds and ETFs | SPY, QQQ, TEFAS funds | Medium | NAV/adjusted price/wealth inputs | Distributions, fund inception, expense policy |
| Interest and bonds | Deposits, government bonds | Medium | Gross constant-APR illustration; supplied price or total-return curves | Real account/settlement history; bond coupon income |
| Real estate | Türkiye housing price index | Medium | Housing price-index input and inflation deflation | Verified index; not automatically rent/net property return |

No row promises a bundled live feed. Asset metadata is a discovery aid, not evidence that the repository ships each instrument's complete history. Instruments without a valid common interval cannot be compared for that interval.

## Attachment 2 — technical stack

The screenshot scores were recommendations, not measured repository benchmark results. The selected stack follows every requested component.

| Component | Requested technology | Implemented in repository | Verification / boundary |
| --- | --- | --- | --- |
| Calculation engine | Python + Polars | `src/inflationweaver/engine.py`, `models.py`, `backtest.py` | Financial identities, date/currency/gap failure tests |
| Historical storage | Parquet + DuckDB | Local store and catalog module | Persist/retrieve tests; local storage, not multi-tenant DB |
| Web interface | TypeScript + Next.js | `web/` | Type checks, tests and production build |
| Chart system | TradingView Lightweight Charts | Web chart component | Runtime receives analysis points; upstream notice retained |
| TradingView integration | Pine Script v6 | Python generator and `tradingview/` export | Generated contract tests; no claim of live TradingView compilation |
| API | FastAPI | `src/inflationweaver/api.py` | Health/catalog/series/analysis/compare/portfolio tests |
| Testing | Pytest | `tests/` | Deterministic fixtures; live-feed uptime not inferred |
| Automation | GitHub Actions | `.github/workflows/` | Code checks and configured demo/update/report tasks |
| License | 0BSD | Root `LICENSE`, Python and web metadata | First-party work only; separate upstream/data terms |

## Attachment 3 — modules and priority

| Module | Original responsibility | Priority | Implemented contract | Remaining input/operational dependency |
| --- | --- | --- | --- | --- |
| Inflation Engine | CPI, ENAG, different base dates | P0 | CPI-ratio adjustment, monthly chain, exact-overlap hybrid and base selection | Historical source verification and basket interpretation |
| Historical Data | Appropriate sources since 1986 | P0 | Arbitrary historical date support, imports, metadata, local store; history guide | Complete authorized XU100/CPI records are not bundled |
| Real Return Engine | Nominal/real return and CAGR | P0 | Normalized nominal/real indices, exact ratio returns, actual-day CAGR, drawdown | Correct input wealth/price basis |
| Data Validation | Missing/error checks and source verification | P0 | Schema, duplicates, numeric/positive values, consecutive monthly-rate inputs, CPI staleness, checksums and metadata consistency | Checksums/provenance labels do not independently authenticate a publisher; manual frequency/source review |
| Asset Comparison | BIST, US markets, gold, crypto | P1 | Exact common dates, shared CPI, FX conversion and multiple assets | Asset histories, currency normalization and calendar overlap |
| TradingView Adapter | Pine Script generation | P1 | CPI-embedded Pine v6 with source labels and baseline handling | User executes/validates in TradingView; bar/feed limits apply |
| Backtesting Adapter | Real performance metrics for Trading Bot | P1 | Net equity curve deflation; optional beginning-of-period flow unitization | Source trading system models execution/costs/vintages |
| Dashboard / REST API | Web analysis and third-party integration | P2 | Next.js dashboard and FastAPI/OpenAPI routes | Authentication/TLS/storage operations for shared deployment |

Data validation deliberately distinguishes absence from uncertainty. Missing monthly-rate periods fail compounding. A CPI level matched within the chosen staleness limit can remain usable even if a monthly observation is absent; the source date is exposed so that this policy can be audited. The code does not turn a manually entered `source="TÜİK"` label into verified official provenance.

## Attachment 4 — development phases

| Proposal phase | Requested behavior | Available in 0.1.0 | What is still data- or deployment-dependent |
| --- | --- | --- | --- |
| V1 — Historical Inflation Engine | XU100 1986–2026 analysis | Long-history engine, selected dates, scale/history guidance | Verified XU100/CPI coverage across the whole period |
| V1 | TÜİK/ENAG hybrid | Exact overlap and scale, explicit hybrid provenance | Verified source inputs and a defensible switch |
| V1 | Base year/date selection | Requested and actual baseline exposed | Actual trading observations on/after requested date |
| V1 | Validation and Pine output | Validators and Pine v6 generator | Source authenticity and TradingView execution |
| V2 — Multi-Asset Analytics | BIST equities, gold, USD, US indices, crypto | Generic positive series, FX conversion, shared-date comparisons | Required instrument feeds and distribution adjustments |
| V2 | Different inflation measures | Separate CPI analyses and explicitly constructed hybrid | Comparable baskets/currency and verified coverage |
| V3 — Financial Analytics Platform | Web dashboard and API | `web/`, local FastAPI service, OpenAPI | Hardened shared deployment and account-level access |
| V3 | Automatic data updates | Reviewed manifests, provider adapters and workflow | Credentials/source access, updated mappings and persistence |
| V3 | Historical performance reports | Analysis points, summary metrics and reports | Correct source data; reports do not certify upstream history |
| V3 | Portfolio comparisons | Fixed-unit wealth curves plus comparison engine | Broader rebalancing/transaction-ledger strategies not implemented |
| V3 | CSV/JSON exports | Report exports and integrity metadata | Rights to publish underlying or derived data |

## Attachment 5 — proposed project scope

| Requested block | Requested items | Covered behavior |
| --- | --- | --- |
| Data sources | ENAG, TÜİK, FRED, OECD, market prices, FX and gold | CSV import for verified exports; FRED, OECD and EVDS compatibility adapters; asset catalog; no fabricated all-market feed |
| Calculation engine | Real return, CAGR, drawdown, compounded inflation, purchasing power | Exact CPI-ratio deflation, monthly multiplicative chaining, nominal/real CAGR and drawdown, base-money value |
| Charts and analysis | Pine Script, interactive charts, benchmark comparison | CPI-embedded Pine, Lightweight Charts dashboard, common-date asset comparison |
| Automation | GitHub Actions, validation, automatic tests and reports | CI checks, deterministic fixtures, reproducible synthetic reports and explicit update manifests |

## Delivery acceptance and limits

The deliverable is source code, first-party 0BSD license, English/Turkish README, financial-method documentation, historical-data guide, reproducible synthetic examples, tests, and integration surfaces. It provides the requested software routes without pretending to ship authentic licensed market histories.

Live provider access, real 1986 data acquisition, past-vintage reconstruction, operational uptime, bank/bond settlement, dividend/corporate-action reconstruction, full transaction-ledger/rebalancing backtests, authentication and public hosting are separate operational or future implementation work. No fabricated historical result or unverified production claim should be used to mark those dependencies complete.
