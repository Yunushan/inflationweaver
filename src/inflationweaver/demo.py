"""Entirely synthetic examples; not historical financial observations. SPDX-License-Identifier: 0BSD."""

from datetime import date

import polars as pl

from .models import Series


def demo_series() -> tuple[Series, Series]:
    dates = [date(2023 + i // 12, i % 12 + 1, 1) for i in range(24)]
    asset_values = [100 * (1.024 ** i) * (1 + (0.025 if i % 5 == 0 else -0.01)) for i in range(24)]
    cpi_values = [100 * (1.017 ** i) for i in range(24)]
    asset = Series("DEMO_ASSET", pl.DataFrame({"date": dates, "value": asset_values,
                   "available_date": dates}), "price", "TRY", "synthetic-demo", True)
    inflation = Series("DEMO_CPI", pl.DataFrame({"date": dates, "value": cpi_values,
                       "available_date": [d.replace(day=5) for d in dates]}),
                       "cpi", "TRY", "synthetic-demo", True)
    return asset, inflation
