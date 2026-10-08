# TradingView indicators

`inflationweaver_demo.pine` is a reproducible Pine Script v6 export using the **synthetic CPI** in `examples/data/demo_cpi.csv`. Its CPI is a demonstration, not a TÜİK or ENAG dataset. Inspect historical 2023–2024 bars to see its output; CPI older than the configured age limit creates visible gaps.

Regenerate an indicator with your validated CPI levels and follow [the TradingView guide](../docs/tradingview.md) for installation, release-date alignment, shared-base calculations, currency rules, and historical coverage. Real nominal asset prices from TradingView do not make the embedded demonstration CPI real.

The indicator code is under [0BSD](../LICENSE). Source data and TradingView services retain their own terms. Local Python tests do not compile or execute Pine; verify the file in TradingView's Pine Editor before using it.
