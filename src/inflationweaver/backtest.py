# SPDX-License-Identifier: 0BSD
"""Inflation reporting for an existing trading system's net equity output.

This adapter consumes marked-to-market net equity. Trading costs, dividends,
slippage, taxes, leverage, and execution simulation belong to the source system.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from .engine import _finite, analyze, validate_series
from .models import AnalysisResult, Series


def equity_series(
    data: pl.DataFrame,
    series_id: str = "backtest",
    currency: str = "TRY",
    cashflow_column: str | None = None,
) -> Series:
    """Adapt net equity, optionally removing period-beginning external flows.

    Input columns are date/value and optionally available_date. With no flow
    column, value must already be a cashflow-free net wealth curve. With flows,
    positive means contributions and negative means withdrawals made at the
    beginning of that row's period. The first row establishes the baseline and
    must have zero flow. The daily return is equity[t] / (equity[t-1] + flow[t])
    - 1; chaining those returns unitizes performance and removes contributions.
    Intraperiod or end-period flows require a source-system unitized curve.
    """
    raw = validate_series(Series(series_id, data, kind="wealth", currency=currency, source="backtest net equity"))
    if cashflow_column is None:
        return raw
    if cashflow_column not in data.columns:
        raise ValueError(f"missing cashflow column: {cashflow_column}")
    flows = [_finite(value, "cashflow") for value in data[cashflow_column].to_list()]
    if not math.isclose(flows[0], 0.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("first-row cashflow must be zero; first equity establishes the baseline")
    values = raw.data["value"].to_list()
    normalized = [values[0]]
    for index in range(1, len(values)):
        capital = values[index - 1] + flows[index]
        if capital <= 0:
            raise ValueError("beginning-of-period equity plus cashflow must be positive")
        adjusted = normalized[-1] * values[index] / capital
        normalized.append(_finite(adjusted, "unitized equity", positive=True))
    output = raw.data.with_columns(pl.Series("value", normalized, dtype=pl.Float64))
    if "available_date" in output.columns:
        # Unitized levels depend on the baseline and every previous flow/equity.
        # Preserve uncertainty and do not publish a derived level before inputs.
        releases = []
        cumulative_release = None
        unknown_release = False
        for release in output["available_date"].to_list():
            if release is None:
                unknown_release = True
            else:
                cumulative_release = max(cumulative_release, release) if cumulative_release else release
            releases.append(None if unknown_release else cumulative_release)
        output = output.with_columns(pl.Series("available_date", releases, dtype=pl.Date))
    return validate_series(Series(
        series_id, output, kind="wealth", currency=currency,
        source=f"backtest unitized net equity; {cashflow_column} at period beginning",
    ))


def analyze_backtest(
    data: pl.DataFrame,
    inflation: Series,
    series_id: str = "backtest",
    currency: str = "TRY",
    cashflow_column: str | None = None,
    **analysis_options: Any,
) -> AnalysisResult:
    """Analyze existing net performance against a same-currency CPI series."""
    result = analyze(
        equity_series(data, series_id, currency, cashflow_column), inflation,
        **analysis_options,
    )
    metadata = dict(result.metadata)
    metadata.update({
        "backtest_adapter": True,
        "cashflow_timing": "period_beginning" if cashflow_column else "cashflow_free_input_required",
        "source_equity_must_include_costs": True,
    })
    return AnalysisResult(result.points, result.metrics, metadata)
