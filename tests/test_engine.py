# SPDX-License-Identifier: 0BSD
"""Financial identities, timing, and failure modes of the reference engine."""

from datetime import date
import json

import polars as pl
import pytest

from inflationweaver.engine import (
    DAYS_PER_YEAR,
    analyze,
    chain_monthly_rates,
    compare_assets,
    convert_currency,
    deposit_curve,
    portfolio_curve,
    splice_cpi,
    validate_series,
)
from inflationweaver.models import Series


def series(dates, values, *, kind="price", currency="TRY", available=None, name="asset", **extra):
    data = {"date": dates, "value": values, **extra}
    if available is not None:
        data["available_date"] = available
    return Series(name, pl.DataFrame(data), kind=kind, currency=currency)


def test_real_return_is_multiplicative_not_nominal_minus_inflation():
    dates = ["2023-01-01", "2024-01-01"]
    result = analyze(series(dates, [100, 200]), series(dates, [100, 150], kind="cpi"))
    assert result.metrics["nominal_return_pct"] == pytest.approx(100)
    assert result.metrics["inflation_return_pct"] == pytest.approx(50)
    assert result.metrics["real_return_pct"] == pytest.approx(100 / 3)
    assert result.points["real_value"].to_list() == pytest.approx([100, 400 / 3])
    assert result.metrics["real_cagr_pct"] == pytest.approx(((4 / 3) ** (DAYS_PER_YEAR / 365) - 1) * 100)
    assert json.loads(json.dumps(result.to_dict()))["points"][0]["date"] == "2023-01-01"


def test_nominal_gain_can_have_negative_real_return_and_drawdown():
    dates = ["2024-01-01", "2024-02-01", "2024-03-01"]
    result = analyze(series(dates, [100, 120, 110]), series(dates, [100, 110, 130], kind="cpi"))
    assert result.metrics["nominal_return_pct"] == pytest.approx(10)
    assert result.metrics["real_return_pct"] == pytest.approx(-15.3846153846)
    assert result.metrics["nominal_max_drawdown_pct"] == pytest.approx((110 / 120 - 1) * 100)
    assert result.metrics["real_max_drawdown_pct"] == pytest.approx(((110 / 130) / (120 / 110) - 1) * 100)


def test_no_future_cpi_used_and_stale_observations_are_errors():
    cpi = series(["2024-01-01", "2024-02-01"], [100, 200], kind="cpi")
    result = analyze(series(["2024-01-15", "2024-02-01"], [100, 100]), cpi)
    assert result.points["inflation_value"].to_list() == [100, 200]
    with pytest.raises(ValueError, match="no CPI observation"):
        analyze(series(["2023-12-31"], [100]), cpi)
    with pytest.raises(ValueError, match="stale CPI"):
        analyze(series(["2024-05-01"], [100]), cpi)


def test_released_alignment_prevents_lookahead():
    asset = series(["2024-02-01", "2024-02-05"], [100, 100], available=["2024-02-01", "2024-02-05"])
    cpi = series(["2024-01-01", "2024-02-01"], [100, 120], kind="cpi", available=["2024-01-04", "2024-02-04"])
    retrospective = analyze(asset, cpi)
    released = analyze(asset, cpi, alignment="released")
    assert retrospective.points["inflation_value"].to_list() == [120, 120]
    assert released.points["inflation_value"].to_list() == [100, 120]
    assert retrospective.metrics["real_return_pct"] == 0
    assert released.metrics["real_return_pct"] == pytest.approx(-100 / 6)
    assert released.metadata["retrospective"] is False


@pytest.mark.parametrize("missing_side", ["asset", "cpi"])
def test_released_mode_requires_real_release_dates(missing_side):
    dates = ["2024-01-01"]
    asset = series(dates, [100], available=dates if missing_side != "asset" else None)
    cpi = series(dates, [100], kind="cpi", available=dates if missing_side != "cpi" else None)
    with pytest.raises(ValueError, match="explicit available_date"):
        analyze(asset, cpi, alignment="released")


def test_released_asset_timeline_uses_publication_date():
    asset = series(["2024-01-01"], [100], available=["2024-01-02"])
    cpi = series(["2024-01-01"], [100], kind="cpi", available=["2024-01-02"])
    result = analyze(asset, cpi, alignment="released")
    assert result.points["date"][0] == date(2024, 1, 2)
    assert result.points["asset_observation_date"][0] == date(2024, 1, 1)


def test_late_old_release_does_not_overwrite_newer_known_period():
    cpi = series(["2024-01-01", "2024-02-01"], [100, 120], kind="cpi", available=["2024-02-10", "2024-02-04"])
    asset = series(["2024-02-05", "2024-02-11"], [100, 100], available=["2024-02-05", "2024-02-11"])
    result = analyze(asset, cpi, alignment="released")
    assert result.points["inflation_value"].to_list() == [120, 120]


def test_base_date_resolves_to_existing_observation_and_can_precede_display():
    dates = ["2024-01-02", "2024-02-02", "2024-03-02"]
    result = analyze(series(dates, [100, 200, 150]), series(dates, [100, 100, 100], kind="cpi"), base_date="2024-01-01", start_date="2024-02-01")
    assert result.metadata["actual_base_date"] == "2024-01-02"
    assert result.points["nominal_index"].to_list() == [200, 150]
    assert result.metrics["nominal_return_pct"] == 50
    assert result.metrics["nominal_max_drawdown_pct"] == -25
    assert result.metadata["display_observations"] == 2
    assert result.metrics["observations"] == 3


def test_requested_long_history_is_not_silently_clamped_to_short_demo():
    asset = series(["2023-01-01"], [100])
    cpi = series(["2023-01-01"], [100], kind="cpi")
    with pytest.raises(ValueError, match="asset coverage gap"):
        analyze(asset, cpi, base_date="1986-01-01")


def test_single_observation_cagr_is_undefined():
    result = analyze(series(["2024-01-01"], [100]), series(["2024-01-01"], [100], kind="cpi"))
    assert result.metrics["nominal_cagr_pct"] is None
    assert result.metrics["real_return_pct"] == 0


@pytest.mark.parametrize("values", [[0], [-1], [float("nan")], [float("inf")], [None]])
def test_invalid_level_values_rejected(values):
    with pytest.raises(ValueError):
        validate_series(series(["2024-01-01"], values))


@pytest.mark.parametrize("dates", [["2024-01-01", "2024-01-01"], ["2024-02-01", "2024-01-01"]])
def test_duplicate_and_unsorted_dates_rejected(dates):
    with pytest.raises(ValueError, match="sorted, increasing, and unique"):
        validate_series(series(dates, [1, 2]))


def test_release_before_observation_rejected_and_metadata_columns_preserved():
    with pytest.raises(ValueError, match="cannot precede"):
        validate_series(series(["2024-02-01"], [100], available=["2024-01-01"]))
    normalized = validate_series(series(["2024-01-01"], [100], source_url=["https://example.org/data"]))
    assert normalized.data.schema["date"] == pl.Date
    assert normalized.data.schema["value"] == pl.Float64
    assert normalized.data["source_url"][0] == "https://example.org/data"
    assert "available_date" not in normalized.data.columns


def test_inflation_rates_and_wrong_currency_cannot_be_used_as_levels():
    asset = series(["2024-01-01"], [100])
    with pytest.raises(ValueError, match="CPI level"):
        analyze(asset, series(["2024-01-01"], [10], kind="monthly_rate"))
    with pytest.raises(ValueError, match="same currency"):
        analyze(asset, series(["2024-01-01"], [100], kind="cpi", currency="USD"))


def test_monthly_rates_chain_using_mom_and_preserve_anchor_uncertainty():
    rates = series(["2024-02-29", "2024-03-31"], [10, -5], kind="monthly_rate", available=["2024-03-04", "2024-04-03"])
    levels = chain_monthly_rates(rates, "2024-01-31")
    assert levels.data["value"].to_list() == pytest.approx([100, 110, 104.5])
    assert levels.data["available_date"][0] is None
    with pytest.raises(ValueError, match="explicit available_date"):
        analyze(series(["2024-04-04"], [100], available=["2024-04-04"]), levels, alignment="released")


def test_chained_levels_depend_on_every_prior_months_release():
    rates = series(["2024-02-29", "2024-03-31"], [10, 10], kind="monthly_rate", available=["2024-05-01", "2024-04-03"])
    levels = chain_monthly_rates(rates, "2024-01-31")
    assert levels.data["available_date"].to_list() == [None, date(2024, 5, 1), date(2024, 5, 1)]
    rates_unknown = series(["2024-02-29", "2024-03-31"], [10, 10], kind="monthly_rate", available=[None, "2024-04-03"])
    assert chain_monthly_rates(rates_unknown, "2024-01-31").data["available_date"].null_count() == 3


@pytest.mark.parametrize("dates,values", [(["2024-03-31"], [10]), (["2024-02-29", "2024-04-30"], [10, 10]), (["2024-02-15", "2024-02-29"], [10, 10]), (["2024-02-29"], [-100])])
def test_missing_month_duplicate_month_or_total_deflation_rejected(dates, values):
    with pytest.raises(ValueError):
        chain_monthly_rates(series(dates, values, kind="monthly_rate"), "2024-01-31")


def test_hybrid_has_continuous_overlap_scale_and_provenance():
    left = series(["2024-01-01", "2024-02-01", "2024-03-01"], [100, 110, 120], kind="cpi", name="official")
    right = series(["2024-02-01", "2024-03-01"], [200, 240], kind="cpi", name="alternative")
    hybrid = splice_cpi(left, right, "2024-02-01")
    assert hybrid.data["value"].to_list() == pytest.approx([100, 110, 132])
    assert hybrid.synthetic is True
    assert "hybrid" in hybrid.source
    with pytest.raises(ValueError, match="same-date"):
        splice_cpi(left, right, "2024-01-01")


def test_hybrid_scale_is_not_available_until_both_overlap_values_are_known():
    left = series(["2024-01-01", "2024-02-01"], [100, 110], kind="cpi", available=["2024-01-04", "2024-05-01"])
    right = series(["2024-02-01", "2024-03-01"], [200, 240], kind="cpi", available=["2024-02-04", "2024-03-04"])
    hybrid = splice_cpi(left, right, "2024-02-01")
    assert hybrid.data["available_date"][-1] == date(2024, 5, 1)
    right_unknown = series(["2024-02-01", "2024-03-01"], [200, 240], kind="cpi", available=[None, "2024-03-04"])
    assert splice_cpi(left, right_unknown, "2024-02-01").data["available_date"][-1] is None


def test_fx_quote_direction_is_enforced_and_asof_never_looks_forward():
    asset = series(["2024-01-01", "2024-01-03"], [100, 100])
    fx = series(["2024-01-01", "2024-01-04"], [20, 40], kind="fx", currency="TRY/USD")
    converted = convert_currency(asset, fx, "USD", operation="divide")
    assert converted.currency == "USD"
    assert converted.data["value"].to_list() == [5, 5]
    with pytest.raises(ValueError, match="FX quote currency"):
        convert_currency(asset, fx, "USD", operation="multiply")
    with pytest.raises(ValueError, match="stale FX"):
        convert_currency(series(["2024-02-01"], [100]), fx, "USD", operation="divide")


def test_fixed_unit_portfolio_weights_drift_instead_of_rebalancing():
    dates = ["2024-01-01", "2024-02-01", "2024-03-01"]
    a = series(dates, [100, 200, 200], name="a")
    b = series(dates, [100, 100, 200], name="b")
    portfolio = portfolio_curve([a, b], [0.5, 0.5])
    assert portfolio.data["value"].to_list() == [100, 150, 200]
    assert portfolio.kind == "wealth"
    with pytest.raises(ValueError, match="sum to 1"):
        portfolio_curve([a, b], [0.2, 0.2])
    with pytest.raises(ValueError, match="nonnegative"):
        portfolio_curve([a, b], [-0.1, 1.1])


def test_portfolio_availability_depends_on_initial_purchase_prices():
    dates = ["2024-01-01", "2024-02-01"]
    a = series(dates, [100, 200], available=["2024-03-01", "2024-02-01"], name="a")
    b = series(dates, [100, 100], available=dates, name="b")
    portfolio = portfolio_curve([a, b], [0.5, 0.5])
    assert portfolio.data["available_date"].to_list() == [date(2024, 3, 1), date(2024, 3, 1)]


def test_comparison_and_portfolio_use_exact_common_dates():
    a = series(["2024-01-01", "2024-02-01", "2024-03-01"], [100, 150, 200], name="a")
    b = series(["2024-02-01", "2024-03-01"], [100, 200], name="b")
    cpi = series(["2024-01-01", "2024-02-01", "2024-03-01"], [100, 100, 100], kind="cpi")
    results = compare_assets([a, b], cpi)
    assert {value.metadata["actual_base_date"] for value in results.values()} == {"2024-02-01"}
    assert results["a"].metrics["nominal_return_pct"] == pytest.approx(100 / 3)
    assert results["b"].metrics["nominal_return_pct"] == 100
    assert portfolio_curve([a, b], [0.5, 0.5]).data["date"].to_list() == [date(2024, 2, 1), date(2024, 3, 1)]


def test_deposit_curve_is_a_declared_gross_apr_model():
    curve = deposit_curve(1000, 40, "2024-01-01", "2025-01-01", compounding="monthly")
    assert curve.data.height == 367
    assert curve.data["value"][-1] == pytest.approx(1000 * (1 + 0.4 / 12) ** (12 * 366 / DAYS_PER_YEAR))
    assert curve.synthetic is True
    assert "gross" in curve.source
    assert curve.data["available_date"][0] == date(2024, 1, 1)
    with pytest.raises(ValueError, match="compounding"):
        deposit_curve(1000, 40, "2024-01-01", "2024-01-02", compounding="invalid")


def test_range_and_staleness_parameter_failures_are_explicit():
    asset = series(["2024-01-01"], [100])
    cpi = series(["2024-01-01"], [100], kind="cpi")
    with pytest.raises(ValueError, match="start_date"):
        analyze(asset, cpi, start_date="2024-02-01", end_date="2024-01-01")
    with pytest.raises(ValueError, match="no asset observations"):
        analyze(asset, cpi, base_date="2025-01-01")
    with pytest.raises(ValueError, match="nonnegative integer"):
        analyze(asset, cpi, max_staleness_days=-1)
    with pytest.raises(ValueError, match="alignment"):
        analyze(asset, cpi, alignment="magic")
