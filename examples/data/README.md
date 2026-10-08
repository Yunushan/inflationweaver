# Synthetic fixtures

All CSV values and release dates in this folder are invented for demonstration and testing. `DEMO_` identifiers, `source: synthetic-demo` and `synthetic: true` are deliberate. They are not BIST, ENAG, TÜİK, TCMB or US CPI history. They cover January 2023 through December 2024 (CPI level fixtures also include a synthetic December 2022 seed published on January 1, 2023 to make released-mode alignment possible at the first asset point) and cannot substantiate a real investment return.

`demo_asset.csv` uses a hypothetical TRY price, `demo_cpi.csv` a hypothetical slower inflation index and `demo_enag_cpi.csv` a hypothetical faster inflation index. `demo_enag_mom.csv` provides illustrative 4.5% monthly observations; chaining it requires an explicit seed before the first observation. `demo_usdtry.csv`, `demo_us_cpi.csv` and `demo_gold.csv` illustrate conversion and comparison workflows.

An `available_date` on price rows equals its observation date for the toy dataset. Inflation fixtures are deliberately released on the third day of the next month, with the initial December 2022 seed released January 1, 2023, all invented; actual release calendars must be supplied for real data.
