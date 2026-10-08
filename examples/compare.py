# SPDX-License-Identifier: 0BSD
"""Run from the repo root: python examples/compare.py. All values are synthetic."""

from pathlib import Path

from inflationweaver.engine import compare_assets, portfolio_curve, analyze
from inflationweaver.providers import read_csv
from inflationweaver.report import write_report

root = Path(__file__).resolve().parent / "data"
assets = [read_csv(root / "demo_asset.csv", "DEMO_XU100", synthetic=True, source="synthetic-demo"),
          read_csv(root / "demo_gold.csv", "DEMO_GOLD", synthetic=True, source="synthetic-demo")]
cpi = read_csv(root / "demo_cpi.csv", "DEMO_CPI", kind="cpi", synthetic=True, source="synthetic-demo")
for identifier, result in compare_assets(assets, cpi).items():
    write_report(result, Path("reports/comparison") / identifier)
portfolio = portfolio_curve(assets, [0.6, 0.4])
write_report(analyze(portfolio, cpi), "reports/portfolio")
print("Synthetic common-date comparisons and 60/40 fixed-unit portfolio written to reports/")
