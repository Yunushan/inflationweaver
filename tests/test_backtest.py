# SPDX-License-Identifier: 0BSD
"""Cash-flow timing and existing trading-system integration contracts."""

import polars as pl
import pytest
from datetime import date

from inflationweaver.backtest import analyze_backtest, equity_series
from inflationweaver.models import Series


def test_period_beginning_contributions_and_withdrawals_are_unitized():
    equity = pl.DataFrame({
        "date": ["2024-01-01", "2024-02-01", "2024-03-01"],
        "value": [100, 220, 187],
        "flow": [0, 100, -50],
    })
    unitized = equity_series(equity, cashflow_column="flow")
    assert unitized.data["value"].to_list() == pytest.approx([100, 110, 121])
    cpi = Series("cpi", pl.DataFrame({"date": equity["date"], "value": [100, 110, 121]}), kind="cpi")
    result = analyze_backtest(equity, cpi, cashflow_column="flow")
    assert result.metrics["nominal_return_pct"] == pytest.approx(21)
    assert result.metrics["real_return_pct"] == pytest.approx(0)
    assert result.metadata["cashflow_timing"] == "period_beginning"


def test_a_contribution_does_not_look_like_profit():
    equity = pl.DataFrame({"date": ["2024-01-01", "2024-02-01"], "value": [100, 200], "flow": [0, 100]})
    assert equity_series(equity, cashflow_column="flow").data["value"].to_list() == [100, 100]


def test_cashflow_free_input_is_preserved_and_contract_is_reported():
    equity = pl.DataFrame({"date": ["2024-01-01", "2024-02-01"], "value": [100, 150]})
    assert equity_series(equity).data["value"].to_list() == [100, 150]
    cpi = Series("cpi", pl.DataFrame({"date": equity["date"], "value": [100, 125]}), kind="cpi")
    result = analyze_backtest(equity, cpi)
    assert result.metrics["real_return_pct"] == pytest.approx(20)
    assert result.metadata["cashflow_timing"] == "cashflow_free_input_required"


@pytest.mark.parametrize("flows", [[100, 0], [0, -100], [0, float("nan")]])
def test_ambiguous_initial_flow_insolvency_and_invalid_flows_rejected(flows):
    equity = pl.DataFrame({"date": ["2024-01-01", "2024-02-01"], "value": [100, 100], "flow": [float(flow) for flow in flows]})
    with pytest.raises(ValueError):
        equity_series(equity, cashflow_column="flow")


def test_named_cashflow_column_must_exist():
    equity = pl.DataFrame({"date": ["2024-01-01"], "value": [100]})
    with pytest.raises(ValueError, match="missing cashflow column"):
        equity_series(equity, cashflow_column="flow")


def test_unitized_availability_depends_on_prior_equity_and_flows():
    equity = pl.DataFrame({
        "date": ["2024-01-01", "2024-02-01"],
        "value": [100, 200], "flow": [0, 100],
        "available_date": ["2024-03-01", "2024-02-01"],
    })
    result = equity_series(equity, cashflow_column="flow")
    assert result.data["available_date"].to_list() == [date(2024, 3, 1), date(2024, 3, 1)]
