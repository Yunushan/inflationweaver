"""Export invariants; Pine compilation itself must be checked in TradingView."""

from datetime import date, timedelta
import json
import re

import polars as pl
import pytest

from inflationweaver.models import Series
from inflationweaver.pine import MAX_PINE_OBSERVATIONS, generate_pine


def cpi(points=None, **metadata):
    points = points or {
        "date": ["2023-01-01", "2023-02-01"],
        "value": [100.0, 103.5],
        "available_date": ["2023-02-03", "2023-03-03"],
    }
    return Series("DEMO:CPI", pl.DataFrame(points), kind="cpi", **metadata)


def embedded_rows(script):
    rows = []
    for line in script.splitlines():
        if line.startswith('    loadChunk("'):
            literal = line.removeprefix("    loadChunk(").split(", observedDates", 1)[0]
            rows.extend(json.loads(literal).split(";"))
    return [row.split("|") for row in rows]


def test_export_is_reproducible_and_preserves_levels_and_dates():
    script = generate_pine(cpi(synthetic=True), base_date="2023-01-01")
    assert script == generate_pine(cpi(synthetic=True), base_date=date(2023, 1, 1))
    assert script.startswith("//@version=6\n")
    assert embedded_rows(script) == [
        ["1672531200000", "1675382400000", "1672531200000", "100.0"],
        ["1675209600000", "1677801600000", "1675209600000", "103.5"],
    ]
    assert "SYNTHETIC / HYBRID" in script
    assert '"sha256":' in script
    assert "1986" not in script


def test_release_dates_replace_effective_dates_and_default_base():
    script = generate_pine(cpi(), alignment="released")
    rows = embedded_rows(script)
    assert rows[0][2] == "1675382400000"
    assert rows[1][2] == "1677801600000"
    assert 'input.time(1675382400000,' in script
    assert script == generate_pine(cpi(), alignment="release")


def test_late_older_publication_does_not_replace_newest_known_observation():
    data = cpi({
        "date": ["2023-01-01", "2023-02-01", "2023-03-01"],
        "value": [100, 110, 120],
        "available_date": ["2023-04-01", "2023-03-03", "2023-04-03"],
    })
    rows = embedded_rows(generate_pine(data, alignment="released"))
    assert [float(row[3]) for row in rows] == [110.0, 120.0]
    assert rows[0][2] < rows[1][2]


def test_same_day_releases_select_the_newest_period():
    data = cpi({"date": ["2023-01-01", "2023-02-01"], "value": [100, 110],
                "available_date": ["2023-03-03", "2023-03-03"]})
    assert [float(row[3]) for row in embedded_rows(generate_pine(data, alignment="released"))] == [110.0]


def test_generated_indicator_guards_dates_currency_and_missing_pairs():
    script = generate_pine(cpi())
    assert "lookahead=barmerge.lookahead_off" in script
    assert "lookahead_on" not in script
    assert "gaps=barmerge.gaps_on" in script
    assert "if idx >= 0" in script
    assert "ageDays >= 0 and ageDays <= maxAgeDays" in script
    assert "math.min(assetCloseTime - 1, timenow)" in script
    assert "if not chart.is_standard" in script
    assert "timeframe.in_seconds() < 86400" in script
    assert 'assetCurrency != "TRY"' in script
    assert "nominal100 * baseCpi / currentCpi" in script
    assert "plot.style_linebr" in script
    assert "valuationDate >= requestedBase" in script
    assert "eligible and na(basePrice)" in script


@pytest.mark.parametrize("symbol", ['BIST:XU100"', "BIST:XU100\nplot(close)", "BIST:XU100 / FX:USDTRY", "XU100", ""])
def test_symbol_expressions_and_injection_are_rejected(symbol):
    with pytest.raises(ValueError, match="EXCHANGE:SYMBOL"):
        generate_pine(cpi(), asset_symbol=symbol)


def test_metadata_strings_are_escaped_and_comments_cannot_inject_code():
    script = generate_pine(cpi(source='example\nplot(close)\r"source"'))
    assert not re.search(r"^plot\(close\)", script, flags=re.MULTILINE)
    assert 'source: example plot(close) "source"' in script


def test_rates_missing_release_dates_and_unsorted_observations_are_rejected():
    with pytest.raises(ValueError, match="CPI index levels"):
        generate_pine(Series("MOM", pl.DataFrame({"date": ["2023-01-01"], "value": [3.5]}), kind="monthly_rate"))
    with pytest.raises(ValueError, match="available_date"):
        generate_pine(cpi({"date": ["2023-01-01"], "value": [100]}), alignment="released")
    with pytest.raises(ValueError, match="sorted"):
        generate_pine(cpi({"date": ["2023-02-01", "2023-01-01"], "value": [110, 100]}))


@pytest.mark.parametrize("invalid", [-1, 1.2, True])
def test_staleness_validation(invalid):
    with pytest.raises(ValueError, match="non-negative integer"):
        generate_pine(cpi(), max_staleness_days=invalid)


def test_export_size_is_bounded_and_multiple_chunks_round_trip():
    dates = [date(2000, 1, 1) + timedelta(days=i) for i in range(MAX_PINE_OBSERVATIONS + 1)]
    data = Series("MANY", pl.DataFrame({"date": dates, "value": [100.0] * len(dates)}), kind="cpi")
    with pytest.raises(ValueError, match="at most 2000"):
        generate_pine(data)
    small = Series("MANY", data.data.head(85), kind="cpi")
    assert len(embedded_rows(generate_pine(small))) == 85


@pytest.mark.parametrize("invalid", ["1986-13-01", "20230101"])
def test_base_date_requires_a_calendar_iso_date(invalid):
    with pytest.raises(ValueError, match="base_date"):
        generate_pine(cpi(), base_date=invalid)
