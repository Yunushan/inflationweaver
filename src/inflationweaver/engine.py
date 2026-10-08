# SPDX-License-Identifier: 0BSD
"""Inflation adjustment with explicit dates, provenance, and gap checks.

Indices are rebased to 100 on the actual selected base date. Returns are
percentage points, drawdowns are negative percentages, and CAGR uses elapsed
calendar days / 365.2425. There is no forward fill from a future observation.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
import math
from typing import Any

import polars as pl

from .models import AnalysisResult, Series

KINDS = frozenset({"price", "cpi", "monthly_rate", "wealth", "fx"})
DAYS_PER_YEAR = 365.2425


def _date(value: Any, name: str = "date") -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{name} must be a calendar date, not a timestamp")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{name} must use YYYY-MM-DD") from error
        if parsed.isoformat() != value:
            raise ValueError(f"{name} must use YYYY-MM-DD")
        return parsed
    raise ValueError(f"{name} must be a date or YYYY-MM-DD string")


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must contain finite numeric values")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must contain finite numeric values") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} must contain finite numeric values")
    if positive and number <= 0:
        raise ValueError(f"{name} must be strictly positive")
    return number


def _staleness(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("max_staleness_days must be a nonnegative integer")
    return value


def validate_series(series: Series) -> Series:
    """Validate and normalize a series without inventing availability dates.

    Observations must already be strictly increasing and unique. Level series
    require positive finite values; monthly rates must exceed -100 percent.
    """
    if not isinstance(series, Series):
        raise TypeError("expected a Series")
    if not isinstance(series.series_id, str) or not series.series_id.strip():
        raise ValueError("series_id must be a nonempty string")
    if series.kind not in KINDS:
        raise ValueError(f"unsupported series kind: {series.kind}")
    if not isinstance(series.currency, str) or not series.currency.strip():
        raise ValueError("currency must be a nonempty label")
    if not isinstance(series.data, pl.DataFrame):
        raise TypeError("Series.data must be a Polars DataFrame")
    if not {"date", "value"}.issubset(series.data.columns):
        raise ValueError("series requires date and value columns")
    if series.data.height == 0:
        raise ValueError("series must contain at least one observation")
    dates = [_date(item) for item in series.data["date"].to_list()]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("observation dates must be sorted, increasing, and unique")
    values = [
        _finite(item, "value", positive=series.kind != "monthly_rate")
        for item in series.data["value"].to_list()
    ]
    if series.kind == "monthly_rate" and any(value <= -100 for value in values):
        raise ValueError("monthly_rate percentages must exceed -100")
    data = series.data.with_columns(
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("value", values, dtype=pl.Float64),
    )
    if "available_date" in data.columns:
        releases = [
            None if item is None else _date(item, "available_date")
            for item in data["available_date"].to_list()
        ]
        if any(release is not None and release < observed for observed, release in zip(dates, releases)):
            raise ValueError("available_date cannot precede its observation date")
        data = data.with_columns(pl.Series("available_date", releases, dtype=pl.Date))
    return replace(series, data=data)


def _rows(series: Series) -> list[dict[str, Any]]:
    return series.data.to_dicts()


def _require_availability(series: Series) -> None:
    if "available_date" not in series.data.columns or series.data["available_date"].null_count():
        raise ValueError(
            f"released alignment requires explicit available_date for every observation in {series.series_id}"
        )


def chain_monthly_rates(series: Series, anchor_date: str, anchor_value: float = 100) -> Series:
    """Compound monthly percentage changes from a preceding-month anchor.

    The first supplied rate applies to the month immediately after the anchor;
    missing months are rejected. The anchor's publication date is unknown, so
    callers must explicitly supply it before released-mode use.
    """
    series = validate_series(series)
    if series.kind != "monthly_rate":
        raise ValueError("chain_monthly_rates requires kind='monthly_rate'")
    anchor = _date(anchor_date, "anchor_date")
    level = _finite(anchor_value, "anchor_value", positive=True)
    previous_month = anchor.year * 12 + anchor.month
    points: list[dict[str, Any]] = [{"date": anchor, "value": level}]
    has_release = "available_date" in series.data.columns
    if has_release:
        points[0]["available_date"] = None
    cumulative_release = None
    unknown_release = False
    for row in _rows(series):
        observed = row["date"]
        month = observed.year * 12 + observed.month
        if month != previous_month + 1:
            raise ValueError("monthly rates must cover consecutive months immediately after the anchor")
        level *= 1 + row["value"] / 100
        if not math.isfinite(level) or level <= 0:
            raise ValueError("chained index overflowed or underflowed")
        point = {"date": observed, "value": level}
        if has_release:
            if row["available_date"] is None:
                unknown_release = True
            else:
                cumulative_release = max(cumulative_release, row["available_date"]) if cumulative_release else row["available_date"]
            point["available_date"] = None if unknown_release else cumulative_release
        points.append(point)
        previous_month = month
    return Series(
        series_id=f"{series.series_id}:chained",
        data=pl.DataFrame(points),
        kind="cpi",
        currency=series.currency,
        source=f"chained monthly percentages; {series.source}; anchor={anchor.isoformat()}:{anchor_value}",
        synthetic=series.synthetic,
    )


def splice_cpi(left: Series, right: Series, splice_date: str) -> Series:
    """Scale right CPI at an exact overlap, then use it after that date.

    A splice is explicitly synthetic: it does not turn distinct methodologies
    into a single historical official series.
    """
    left, right = validate_series(left), validate_series(right)
    if left.kind != "cpi" or right.kind != "cpi":
        raise ValueError("splice_cpi requires two CPI level series")
    if left.currency != right.currency:
        raise ValueError("CPI series must describe the same currency before splicing")
    when = _date(splice_date, "splice_date")
    left_rows, right_rows = _rows(left), _rows(right)
    left_at = next((row for row in left_rows if row["date"] == when), None)
    right_at = next((row for row in right_rows if row["date"] == when), None)
    if left_at is None or right_at is None:
        raise ValueError("splice_date requires a same-date observation in both CPI series")
    scale = left_at["value"] / right_at["value"]
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("splice scale overflowed or underflowed")
    points = [row for row in left_rows if row["date"] <= when]
    for row in right_rows:
        if row["date"] > when:
            point = dict(row)
            point["value"] *= scale
            if "available_date" in point:
                releases = (left_at.get("available_date"), right_at.get("available_date"), point["available_date"])
                point["available_date"] = max(releases) if all(item is not None for item in releases) else None
            points.append(point)
    result = Series(
        f"hybrid:{left.series_id}+{right.series_id}",
        pl.DataFrame(points),
        kind="cpi",
        currency=left.currency,
        source=f"hybrid CPI; {left.source} -> {right.source}; splice={when}; scale={scale:.12g}",
        synthetic=True,
    )
    return validate_series(result)


def _lookup(series: Series, alignment: str):
    rows = _rows(series)
    if alignment == "observation":
        return [row["date"] for row in rows], rows
    _require_availability(series)
    ordered = sorted(rows, key=lambda row: (row["available_date"], row["date"]))
    keys, newest_rows = [], []
    newest = ordered[0]
    for row in ordered:
        # A late publication of an older period must not replace a newer known period.
        if row["date"] > newest["date"]:
            newest = row
        keys.append(row["available_date"])
        newest_rows.append(newest)
    return keys, newest_rows


def _asof(keys: list[date], rows: list[dict[str, Any]], when: date, max_days: int, label: str):
    index = bisect_right(keys, when) - 1
    if index < 0:
        raise ValueError(f"no {label} observation available on or before {when}")
    row = rows[index]
    lag = (when - row["date"]).days
    if lag > max_days:
        raise ValueError(f"stale {label} observation at {when}: {lag} days exceeds {max_days}")
    return row


def _cagr(ratio: float, elapsed_days: int) -> float | None:
    if elapsed_days == 0:
        return None
    try:
        value = math.expm1(math.log(ratio) * DAYS_PER_YEAR / elapsed_days) * 100
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def analyze(
    asset: Series,
    inflation: Series,
    base_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    alignment: str = "observation",
    max_staleness_days: int = 62,
) -> AnalysisResult:
    """Compute nominal and inflation-adjusted indices on asset dates.

    Observation mode is retrospective. Released mode evaluates prices on their
    explicit availability dates and uses only CPI observations published then.
    Requested dates select existing observations; they never manufacture prices.
    The actual base is the first asset point on or after base_date (or start_date).
    An explicit base may precede the display start: all metrics and drawdowns
    still cover the base-to-end period; points are filtered to the display range.
    """
    asset, inflation = validate_series(asset), validate_series(inflation)
    if asset.kind not in {"price", "wealth"}:
        raise ValueError("asset must be a price or wealth level series")
    if inflation.kind != "cpi":
        raise ValueError("inflation must be a CPI level series; chain monthly rates first")
    if asset.currency != inflation.currency:
        raise ValueError("asset and inflation must use the same currency; convert the asset first")
    if alignment not in {"observation", "released"}:
        raise ValueError("alignment must be 'observation' or 'released'")
    max_days = _staleness(max_staleness_days)
    start = _date(start_date, "start_date") if start_date is not None else None
    end = _date(end_date, "end_date") if end_date is not None else None
    requested_base = _date(base_date, "base_date") if base_date is not None else start
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must not be after end_date")
    if requested_base is not None and end is not None and requested_base > end:
        raise ValueError("base_date must not follow end_date")
    asset_rows = _rows(asset)
    if alignment == "released":
        _require_availability(asset)
        asset_rows = sorted(asset_rows, key=lambda row: (row["available_date"], row["date"]))
        keys = [row["available_date"] for row in asset_rows]
        if len(keys) != len(set(keys)):
            raise ValueError("asset available_date must be unique for released analysis")
    timeline = "available_date" if alignment == "released" else "date"
    selected = [
        row for row in asset_rows
        if (end is None or row[timeline] <= end)
        and (requested_base is None or row[timeline] >= requested_base)
    ]
    if not selected:
        raise ValueError("requested date range contains no asset observations")
    if requested_base is not None and (selected[0][timeline] - requested_base).days > max_days:
        raise ValueError(
            f"asset coverage gap: first eligible observation {selected[0][timeline]} is more than "
            f"{max_days} days after requested base {requested_base}"
        )
    inflation_keys, inflation_rows = _lookup(inflation, alignment)
    matched = [
        _asof(inflation_keys, inflation_rows, row[timeline], max_days, "CPI")
        for row in selected
    ]
    p0, c0 = selected[0]["value"], matched[0]["value"]
    nominal_peak = real_peak = 100.0
    points = []
    for asset_row, cpi_row in zip(selected, matched):
        nominal = 100 * asset_row["value"] / p0
        inflation_index = 100 * cpi_row["value"] / c0
        real = 100 * nominal / inflation_index
        real_value = asset_row["value"] * c0 / cpi_row["value"]
        if not all(math.isfinite(item) and item > 0 for item in (nominal, inflation_index, real, real_value)):
            raise ValueError("index arithmetic overflowed or underflowed")
        nominal_peak = max(nominal_peak, nominal)
        real_peak = max(real_peak, real)
        points.append({
            "date": asset_row[timeline],
            "asset_observation_date": asset_row["date"],
            "asset_value": asset_row["value"],
            "inflation_observation_date": cpi_row["date"],
            "inflation_available_date": cpi_row.get("available_date"),
            "inflation_value": cpi_row["value"],
            "nominal_index": nominal,
            "inflation_index": inflation_index,
            "real_index": real,
            "real_value": real_value,
            "nominal_drawdown": (nominal / nominal_peak - 1) * 100,
            "real_drawdown": (real / real_peak - 1) * 100,
        })
    displayed_points = [point for point in points if start is None or point["date"] >= start]
    if not displayed_points:
        raise ValueError("requested display range contains no asset observations")
    frame = pl.DataFrame(displayed_points).with_columns(
        pl.col("inflation_available_date").cast(pl.Date)
    )
    first, last = points[0], points[-1]
    elapsed = (last["date"] - first["date"]).days
    metrics = {
        "nominal_return_pct": last["nominal_index"] - 100,
        "inflation_return_pct": last["inflation_index"] - 100,
        "real_return_pct": last["real_index"] - 100,
        "nominal_cagr_pct": _cagr(last["nominal_index"] / 100, elapsed),
        "inflation_cagr_pct": _cagr(last["inflation_index"] / 100, elapsed),
        "real_cagr_pct": _cagr(last["real_index"] / 100, elapsed),
        "nominal_max_drawdown_pct": min(row["nominal_drawdown"] for row in points),
        "real_max_drawdown_pct": min(row["real_drawdown"] for row in points),
        "elapsed_days": elapsed,
        "observations": len(points),
    }
    metadata = {
        "asset_id": asset.series_id,
        "inflation_id": inflation.series_id,
        "asset_source": asset.source,
        "inflation_source": inflation.source,
        "currency": asset.currency,
        "asset_kind": asset.kind,
        "alignment": alignment,
        "retrospective": alignment == "observation",
        "requested_base_date": requested_base.isoformat() if requested_base else None,
        "actual_base_date": first["date"].isoformat(),
        "actual_end_date": last["date"].isoformat(),
        "actual_display_start_date": displayed_points[0]["date"].isoformat(),
        "display_observations": len(displayed_points),
        "base_inflation_observation_date": matched[0]["date"].isoformat(),
        "max_staleness_days": max_days,
        "staleness_basis": "observation_date",
        "synthetic": asset.synthetic or inflation.synthetic,
        "cagr_year_days": DAYS_PER_YEAR,
        "real_value_units": f"{asset.currency} at base-date purchasing power",
    }
    return AnalysisResult(frame, metrics, metadata)


def convert_currency(
    asset: Series,
    fx: Series,
    target_currency: str,
    operation: str = "multiply",
    max_staleness_days: int = 7,
) -> Series:
    """Convert with backward-asof FX quotes.

    For multiply, ``fx.currency`` must be ``TARGET/SOURCE`` (target units per
    source unit). For divide it must be ``SOURCE/TARGET``. Quote direction is
    validated; conversion does not infer it from a ticker symbol.
    """
    asset, fx = validate_series(asset), validate_series(fx)
    if asset.kind not in {"price", "wealth"} or fx.kind != "fx":
        raise ValueError("convert_currency requires a price/wealth asset and kind='fx' quotes")
    if operation not in {"multiply", "divide"}:
        raise ValueError("operation must be 'multiply' or 'divide'")
    if not isinstance(target_currency, str) or not target_currency.strip() or target_currency == asset.currency:
        raise ValueError("target_currency must be a different nonempty currency label")
    expected = f"{target_currency}/{asset.currency}" if operation == "multiply" else f"{asset.currency}/{target_currency}"
    if fx.currency != expected:
        raise ValueError(f"FX quote currency must be {expected} for {operation}")
    max_days = _staleness(max_staleness_days)
    keys, quote_rows = _lookup(fx, "observation")
    converted = []
    all_releases_known = "available_date" in asset.data.columns and "available_date" in fx.data.columns
    for row in _rows(asset):
        quote = _asof(keys, quote_rows, row["date"], max_days, "FX")
        value = row["value"] * quote["value"] if operation == "multiply" else row["value"] / quote["value"]
        point = {"date": row["date"], "value": _finite(value, "converted value", positive=True)}
        if all_releases_known:
            releases = (row["available_date"], quote["available_date"])
            point["available_date"] = max(releases) if all(item is not None for item in releases) else None
        converted.append(point)
    return validate_series(Series(
        f"{asset.series_id}:{target_currency}", pl.DataFrame(converted), asset.kind,
        target_currency, f"{asset.source}; FX={fx.source}; {operation} {fx.currency}",
        asset.synthetic or fx.synthetic,
    ))


def _common_assets(assets: Sequence[Series]) -> tuple[list[Series], list[date]]:
    if not assets:
        raise ValueError("at least one asset is required")
    checked = [validate_series(asset) for asset in assets]
    if any(asset.kind not in {"price", "wealth"} for asset in checked):
        raise ValueError("assets must have kind='price' or 'wealth'")
    if len({asset.series_id for asset in checked}) != len(checked):
        raise ValueError("asset identifiers must be unique")
    if len({asset.currency for asset in checked}) != 1:
        raise ValueError("all assets must use the same currency")
    common = set(checked[0].data["date"].to_list())
    for asset in checked[1:]:
        common.intersection_update(asset.data["date"].to_list())
    if not common:
        raise ValueError("assets have no common observation dates")
    return checked, sorted(common)


def compare_assets(assets: Sequence[Series], inflation: Series, **analysis_options: Any) -> dict[str, AnalysisResult]:
    """Analyze assets on identical observation dates and a shared base."""
    checked, common = _common_assets(assets)
    if analysis_options.get("alignment", "observation") == "released":
        # Shared dates must also be shared decision dates for honest comparisons.
        for asset in checked:
            _require_availability(asset)
            rows = {row["date"]: row["available_date"] for row in _rows(asset)}
            if any(rows[when] != when for when in common):
                raise ValueError("released comparison requires same-day asset availability on common dates")
    return {
        asset.series_id: analyze(
            replace(asset, data=asset.data.filter(pl.col("date").is_in(common))),
            inflation, **analysis_options,
        )
        for asset in checked
    }


def portfolio_curve(
    assets: Sequence[Series], weights: Sequence[float], initial_value: float = 100.0
) -> Series:
    """Buy fixed units at the first common date; never rebalance.

    Values are price-only unless the caller supplies total-return wealth inputs.
    Missing constituent dates are excluded via exact common-date intersection.
    """
    checked, common = _common_assets(assets)
    if len(weights) != len(checked):
        raise ValueError("weights must match the number of assets")
    amounts = [_finite(weight, "weights") for weight in weights]
    if any(weight < 0 for weight in amounts) or not math.isclose(sum(amounts), 1, rel_tol=0, abs_tol=1e-9):
        raise ValueError("weights must be nonnegative and sum to 1")
    initial = _finite(initial_value, "initial_value", positive=True)
    tables = [{row["date"]: row for row in _rows(asset)} for asset in checked]
    units = [initial * weight / table[common[0]]["value"] for table, weight in zip(tables, amounts)]
    has_release = all("available_date" in asset.data.columns for asset in checked)
    base_releases = [table[common[0]].get("available_date") for table in tables]
    points = []
    for when in common:
        point = {"date": when, "value": sum(unit * table[when]["value"] for unit, table in zip(units, tables))}
        if has_release:
            releases = base_releases + [table[when]["available_date"] for table in tables]
            point["available_date"] = max(releases) if all(item is not None for item in releases) else None
        points.append(point)
    return validate_series(Series(
        "portfolio:" + "+".join(asset.series_id for asset in checked),
        pl.DataFrame(points), kind="wealth", currency=checked[0].currency,
        source="fixed-unit portfolio; " + "; ".join(f"{asset.series_id}={weight:.12g}" for asset, weight in zip(checked, amounts)),
        synthetic=any(asset.synthetic for asset in checked),
    ))


def deposit_curve(
    principal: float,
    annual_rate: float,
    start_date: str,
    end_date: str,
    compounding: str = "daily",
    currency: str = "TRY",
) -> Series:
    """Illustrate a constant gross nominal APR, with daily valuations.

    Compounding choices are daily/monthly/quarterly/annual/simple. Fractional
    periods accrue smoothly using actual days / 365.2425; this is a mathematical
    model, not a bank settlement schedule. Fees and tax are not assumed.
    """
    initial = _finite(principal, "principal", positive=True)
    apr = _finite(annual_rate, "annual_rate") / 100
    start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    frequencies = {"daily": DAYS_PER_YEAR, "monthly": 12, "quarterly": 4, "annual": 1}
    if compounding not in {*frequencies, "simple"}:
        raise ValueError("unsupported compounding: use daily, monthly, quarterly, annual, or simple")
    if compounding != "simple" and 1 + apr / frequencies[compounding] <= 0:
        raise ValueError("annual_rate produces a nonpositive compounding factor")
    points = []
    for day in range((end - start).days + 1):
        when = start + timedelta(days=day)
        years = day / DAYS_PER_YEAR
        try:
            factor = 1 + apr * years if compounding == "simple" else math.exp(
                frequencies[compounding] * years * math.log1p(apr / frequencies[compounding])
            )
        except OverflowError as error:
            raise ValueError("deposit calculation overflowed") from error
        points.append({"date": when, "value": _finite(initial * factor, "deposit value", positive=True), "available_date": when})
    return validate_series(Series(
        "deposit", pl.DataFrame(points), kind="wealth", currency=currency,
        source=f"illustrative constant gross APR={annual_rate}%; compounding={compounding}; actual/{DAYS_PER_YEAR}",
        synthetic=True,
    ))
