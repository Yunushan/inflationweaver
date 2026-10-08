# SPDX-License-Identifier: 0BSD
"""Regression cases for data dependencies in derived inflation series."""

from datetime import date

import polars as pl
import pytest
from fastapi.testclient import TestClient

from inflationweaver.api import create_app
from inflationweaver.engine import analyze, chain_monthly_rates, portfolio_curve, splice_cpi
from inflationweaver.models import Series
from inflationweaver.providers import read_csv
from inflationweaver.store import SeriesStore


def make_series(identifier, dates, values, *, kind="cpi", releases=None):
    data = {"date": dates, "value": values}
    if releases is not None:
        data["available_date"] = releases
    return Series(identifier, pl.DataFrame(data), kind=kind)


def test_chained_level_cannot_precede_any_contributing_rate_release():
    rates = make_series(
        "rates", ["2024-01-01", "2024-02-01"], [10, 20], kind="monthly_rate",
        releases=["2024-04-01", "2024-03-01"],
    )
    chained = chain_monthly_rates(rates, "2023-12-01")
    assert chained.data["value"].to_list() == pytest.approx([100, 110, 132])
    assert chained.data["available_date"].to_list() == [
        None, date(2024, 4, 1), date(2024, 4, 1),
    ]


def test_unknown_rate_release_keeps_all_dependent_levels_unknown():
    rates = make_series(
        "rates", ["2024-01-01", "2024-02-01"], [10, 20], kind="monthly_rate",
        releases=[None, "2024-03-01"],
    )
    chained = chain_monthly_rates(rates, "2023-12-01")
    assert chained.data["available_date"].to_list() == [None, None, None]


def test_hybrid_scaled_level_waits_for_both_overlap_releases():
    left = make_series(
        "official", ["2023-12-01", "2024-01-01"], [100, 110],
        releases=["2023-12-04", "2024-04-01"],
    )
    right = make_series(
        "alternative", ["2024-01-01", "2024-02-01"], [200, 240],
        releases=["2024-03-15", "2024-03-01"],
    )
    hybrid = splice_cpi(left, right, "2024-01-01")
    assert hybrid.data["value"].to_list() == pytest.approx([100, 110, 132])
    assert hybrid.data["available_date"][-1] == date(2024, 4, 1)
    asset = make_series(
        "asset", ["2024-03-02", "2024-04-02"], [100, 100], kind="price",
        releases=["2024-03-02", "2024-04-02"],
    )
    result = analyze(asset, hybrid, alignment="released", max_staleness_days=150)
    assert result.points["inflation_value"].to_list() == pytest.approx([100, 132])


def test_unknown_overlap_release_cannot_become_known_after_splice():
    left = make_series("official", ["2024-01-01"], [110])
    right = make_series(
        "alternative", ["2024-01-01", "2024-02-01"], [200, 240],
        releases=["2024-02-01", "2024-03-01"],
    )
    hybrid = splice_cpi(left, right, "2024-01-01")
    assert hybrid.data["available_date"][-1] is None


def test_derived_hybrid_and_portfolio_identifiers_can_be_stored(tmp_path):
    dates = ["2024-01-01", "2024-02-01"]
    a = make_series("a", dates, [100, 110], kind="price")
    b = make_series("b", dates, [100, 120], kind="price")
    portfolio = portfolio_curve([a, b], [0.5, 0.5])
    left = make_series("official", dates, [100, 110])
    right = make_series("alternative", dates, [200, 240])
    hybrid = splice_cpi(left, right, "2024-01-01")
    store = SeriesStore(tmp_path)
    for derived in (portfolio, hybrid):
        store.write(derived)
        restored = store.read(derived.series_id)
        assert restored.data["value"].to_list() == pytest.approx(derived.data["value"].to_list())


@pytest.mark.parametrize("field,value", [("value", True), ("date", 1704067200)])
def test_api_financial_observations_do_not_coerce_booleans_or_timestamps(field, value):
    payload = {
        "asset": {"series_id": "asset", "data": [{"date": "2024-01-01", "value": 100}]},
        "inflation": {
            "series_id": "cpi", "kind": "cpi", "data": [{"date": "2024-01-01", "value": 100}],
        },
    }
    payload["asset"]["data"][0][field] = value
    response = TestClient(create_app()).post("/v1/analyze", json=payload)
    assert response.status_code == 422


def test_csv_boolean_is_not_a_financial_number(tmp_path):
    path = tmp_path / "boolean.csv"
    path.write_text("date,value\n2024-01-01,true\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_csv(path, "boolean")
