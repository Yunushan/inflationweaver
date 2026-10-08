# Delivery verification

Version: **0.1.0**. Local verification date: **8 October 2026**.

| Check | Result |
| --- | --- |
| Python suite | 101 tests passed on Python 3.12.14 |
| Python static checks | Ruff passed for source, tests and fixture-generation script |
| Browser suite | 10 tests passed on Node.js 24.19.0 |
| Shared financial contract | Browser points, metrics and metadata match five Python API fixtures within numerical tolerance |
| TypeScript | Strict typecheck passed |
| Next.js | Production build passed |
| Python packaging | Wheel and source distribution built successfully |
| CLI examples | Demo, analyze, import, update, Pine export, rate chaining, hybrid splice, FX conversion, deposit model, common-date comparison and fixed-unit portfolio ran successfully |
| Documentation | Relative Markdown links checked; README commands smoke-tested |

The parity cases cover compounded real returns, a baseline before the display
range, publication-aware selection, a late release of an older CPI period, and
explicitly synthetic 1986 dates. The final case tests old date handling; it does
not contain real 1986 market or inflation observations. Regenerate the parity
records with `python scripts/generate_web_reference.py`, or check them with
`python scripts/generate_web_reference.py --check` before running browser tests.

Dependency versions are retained in `requirements.lock` and `web/package-lock.json`.
The GitHub workflow defines Python 3.11/3.12/3.13 checks; those other interpreters
and the hosted workflow were not executed during this local verification.

Provider HTTP tests use deterministic mocked responses. Live account credentials,
current provider availability, real historical data coverage and original
publication vintages were not verified. The legacy EVDS2 compatibility limitation
is described in [data-sources.md](data-sources.md).

Pine source was generated and tested locally; compilation and execution in
TradingView remain external checks. Browser visual/end-to-end QA was unavailable
because a Chromium test binary could not be downloaded in this environment;
production compilation, calculation parity and parsers were checked instead.
