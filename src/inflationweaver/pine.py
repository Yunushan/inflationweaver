"""Reproducible Pine Script v6 export of validated CPI index levels.

Generated indicators use embedded observations, not an HTTP request or an
invented ENAG ticker. Date-only observations are evaluated on daily or coarser
standard price bars; the indicator is a research visualization, not a strategy.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

from .engine import validate_series
from .models import Series

MAX_PINE_OBSERVATIONS = 2000
_CHUNK_ROWS = 40
_SYMBOL = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_./!+\-]+$")


def _date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("Pine export expects a date, not an intraday datetime")
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("noncanonical date")
        return parsed
    except (TypeError, ValueError) as exc:
        raise ValueError("base_date must be an ISO YYYY-MM-DD date") from exc


def _milliseconds(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp()) * 1000


def _string(value: str) -> str:
    """JSON's plain escaped string syntax is also safe for our Pine literals."""
    return json.dumps(value, ensure_ascii=False)


def _comment(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def generate_pine(
    inflation: Series,
    asset_symbol: str = "BIST:XU100",
    base_date: date | str | None = None,
    alignment: str = "observation",
    max_staleness_days: int = 62,
) -> str:
    """Generate an embedded-level Pine Script v6 indicator.

    ``alignment='observation'`` is an ex-post purchasing-power view. Released
    alignment requires an ``available_date`` for every observation and only
    uses levels whose availability date is not later than the valuation date.
    Availability dates contain no publication times or revision vintages;
    this export must not be treated as a point-in-time trading backtest.

    The requested base defaults to the first effective CPI date. TradingView
    chooses the first loaded eligible price bar on or after that date and
    shows the actual base in its table. Source data, chart history and CPI
    coverage therefore control the start; no 1986 history is fabricated.
    """
    inflation = validate_series(inflation)
    if inflation.kind != "cpi":
        raise ValueError("Pine export requires CPI index levels (kind='cpi'), not inflation rates")
    if not isinstance(asset_symbol, str) or not _SYMBOL.fullmatch(asset_symbol):
        raise ValueError("asset_symbol must be one TradingView EXCHANGE:SYMBOL, without quotes or expressions")
    if alignment == "release":
        alignment = "released"
    if alignment not in {"observation", "released"}:
        raise ValueError("alignment must be 'observation' or 'released'")
    if isinstance(max_staleness_days, bool) or not isinstance(max_staleness_days, int) or max_staleness_days < 0:
        raise ValueError("max_staleness_days must be a non-negative integer")
    rows = inflation.data.to_dicts()
    if len(rows) > MAX_PINE_OBSERVATIONS:
        raise ValueError(f"Pine export supports at most {MAX_PINE_OBSERVATIONS} CPI observations; filter the period or use Python")

    if alignment == "released":
        if any(row.get("available_date") is None for row in rows):
            raise ValueError("released alignment requires available_date for every CPI observation")
        # Follow the engine's latest-known-observation policy. Same-day
        # releases consolidate to the newest period; late older publications
        # must never replace a more recent period already available.
        events: list[dict] = []
        newest_date = None
        for row in sorted(rows, key=lambda r: (r["available_date"], r["date"])):
            if newest_date is not None and row["date"] <= newest_date:
                continue
            newest_date = row["date"]
            if events and events[-1]["available_date"] == row["available_date"]:
                events[-1] = row
            else:
                events.append(row)
        rows = events

    encoded: list[str] = []
    effective_dates: list[date] = []
    for row in rows:
        observed = row["date"]
        available = row.get("available_date")
        effective = available if alignment == "released" else observed
        effective_dates.append(effective)
        level = format(Decimal(str(float(row["value"]))), "f")
        encoded.append(f"{_milliseconds(observed)}|{_milliseconds(available) if available else -1}|{_milliseconds(effective)}|{level}")
    if any(a >= b for a, b in zip(effective_dates, effective_dates[1:])):
        raise ValueError("Pine export requires strictly increasing effective dates; same-day releases need explicit consolidation")

    requested_base = _date(base_date) if base_date is not None else effective_dates[0]
    checksum = hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()
    loads = "\n".join(
        "    loadChunk(" + _string(";".join(encoded[i : i + _CHUNK_ROWS])) + ", observedDates, availableDates, effectiveDates, levels)"
        for i in range(0, len(encoded), _CHUNK_ROWS)
    )
    label = "SYNTHETIC / HYBRID — " + inflation.series_id if inflation.synthetic else inflation.series_id
    metadata = {
        "source": inflation.source,
        "series_id": inflation.series_id,
        "currency": inflation.currency,
        "synthetic": inflation.synthetic,
        "alignment": alignment,
        "observations": len(rows),
        "sha256": checksum,
    }
    return f'''//@version=6
// SPDX-License-Identifier: 0BSD
// Generated by InflationWeaver. CPI INDEX LEVELS: never divide by annual inflation percentages.
// CPI series: {_comment(inflation.series_id)} | source: {_comment(inflation.source)}
// Embedded data metadata: {_comment(json.dumps(metadata, ensure_ascii=False, sort_keys=True))}
// Date-only inputs; UTC valuation dates; release alignment is not a vintage-aware backtest.
// Update the source CSV and regenerate whenever a new observation or revision is available.
indicator("InflationWeaver — embedded CPI", shorttitle="InflationWeaver", overlay=false, precision=2)

string assetSymbol = input.symbol({_string(asset_symbol)}, "Asset (same quote currency as CPI)")
int requestedBase = input.time({_milliseconds(requested_base)}, "Requested base date (UTC)")
int maxAgeDays = input.int({max_staleness_days}, "Maximum CPI observation age (days)", minval=0)
string view = input.string("Both normalized", "View", options=["Both normalized", "Real normalized", "Base-date money"])
bool showTable = input.bool(true, "Show methodology and returns")
int DAY_MS = 86400000

// Chunked literals keep compiled instructions small. Initialize exactly once.
loadChunk(string encoded, array<int> obs, array<int> avail, array<int> eff, array<float> vals) =>
    array<string> rows = str.split(encoded, ";")
    for row in rows
        array<string> fields = str.split(row, "|")
        array.push(obs, int(str.tonumber(array.get(fields, 0))))
        array.push(avail, int(str.tonumber(array.get(fields, 1))))
        array.push(eff, int(str.tonumber(array.get(fields, 2))))
        array.push(vals, str.tonumber(array.get(fields, 3)))

// Explicit floor search: -1 before first observation, never a negative array access.
asofIndex(array<int> dates, int target) =>
    int left = 0
    int right = array.size(dates) - 1
    int result = -1
    while left <= right
        int middle = int(math.floor((left + right) / 2))
        if array.get(dates, middle) <= target
            result := middle
            left := middle + 1
        else
            right := middle - 1
    result

dateText(int stamp) =>
    na(stamp) or stamp == -1 ? "n/a" : str.format_time(stamp, "yyyy-MM-dd", "UTC")

numberText(float value) =>
    na(value) ? "n/a" : str.tostring(value, "#.##")

var array<int> observedDates = array.new<int>()
var array<int> availableDates = array.new<int>()
var array<int> effectiveDates = array.new<int>()
var array<float> levels = array.new<float>()
if barstate.isfirst
{loads}

if not chart.is_standard
    runtime.error("Use standard time-based candles; synthetic chart prices are unsuitable for real returns.")
if na(timeframe.in_seconds()) or timeframe.in_seconds() < 86400
    runtime.error("Use a daily, weekly or monthly chart. Date-only CPI releases do not establish intraday availability.")

// Same chart timeframe; no higher-timeframe lookahead or forward-filled absent asset bars.
[assetPrice, assetOpenTime, assetCloseTime, assetCurrency] = request.security(assetSymbol, timeframe.period, [close, time, time_close, syminfo.currency], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_off, ignore_invalid_symbol=true)
if assetCurrency != "" and assetCurrency != {_string(inflation.currency)}
    runtime.error("Asset quote currency differs from embedded CPI currency. Convert prices in Python or generate with the appropriate CPI.")
// Completed bars use their last instant. A forming bar never sees embedded future CPI.
int valuationDate = not na(assetCloseTime) ? int(math.floor(math.min(assetCloseTime - 1, timenow) / DAY_MS)) * DAY_MS : na
int idx = not na(valuationDate) ? asofIndex(effectiveDates, valuationDate) : -1
float currentCpi = na
int observedDate = na
int availableDate = na
int effectiveDate = na
int ageDays = na
if idx >= 0
    observedDate := array.get(observedDates, idx)
    availableDate := array.get(availableDates, idx)
    effectiveDate := array.get(effectiveDates, idx)
    ageDays := int((valuationDate - observedDate) / DAY_MS)
    if ageDays >= 0 and ageDays <= maxAgeDays
        currentCpi := array.get(levels, idx)

bool priceValid = not na(assetPrice) and assetPrice > 0 and not na(assetOpenTime)
bool eligible = priceValid and not na(currentCpi) and currentCpi > 0 and valuationDate >= requestedBase
var float basePrice = na
var float baseCpi = na
var int actualBase = na
if eligible and na(basePrice)
    basePrice := assetPrice
    baseCpi := currentCpi
    actualBase := valuationDate

bool afterBase = priceValid and not na(basePrice) and valuationDate >= actualBase
float nominal100 = afterBase ? 100 * assetPrice / basePrice : na
float real100 = afterBase and not na(currentCpi) ? nominal100 * baseCpi / currentCpi : na
float realPrice = afterBase and not na(currentCpi) ? assetPrice * baseCpi / currentCpi : na
float inflationChange = afterBase and not na(currentCpi) ? 100 * (currentCpi / baseCpi - 1) : na
float years = afterBase ? (valuationDate - actualBase) / DAY_MS / 365.2425 : na
float realCagr = not na(real100) and years >= 1 ? 100 * (math.pow(real100 / 100, 1 / years) - 1) : na

plot(view == "Both normalized" ? nominal100 : na, "Nominal index (base=100)", color=color.gray, style=plot.style_linebr)
plot(view != "Base-date money" ? real100 : na, "Real index (base=100)", color=color.teal, linewidth=2, style=plot.style_linebr)
plot(view == "Base-date money" ? realPrice : na, "Real price in actual-base-date money", color=color.teal, linewidth=2, style=plot.style_linebr)
plot(currentCpi, "Embedded CPI level", display=display.data_window)
plot(ageDays, "CPI observation age in days", display=display.data_window)

var table stats = table.new(position.top_right, 2, 13, border_width=1)
if barstate.islast and showTable
    table.cell(stats, 0, 0, "InflationWeaver", text_color=chart.fg_color)
    table.cell(stats, 1, 0, {_string(label)}, text_color=chart.fg_color)
    table.cell(stats, 0, 1, "Alignment / currency", text_color=chart.fg_color)
    table.cell(stats, 1, 1, {_string(alignment + ' / ' + inflation.currency)}, text_color=chart.fg_color)
    table.cell(stats, 0, 2, "Requested / actual base", text_color=chart.fg_color)
    table.cell(stats, 1, 2, dateText(requestedBase) + " / " + dateText(actualBase), text_color=chart.fg_color)
    table.cell(stats, 0, 3, "Valuation date (UTC)", text_color=chart.fg_color)
    table.cell(stats, 1, 3, dateText(valuationDate), text_color=chart.fg_color)
    table.cell(stats, 0, 4, "CPI observation / level", text_color=chart.fg_color)
    table.cell(stats, 1, 4, dateText(observedDate) + " / " + numberText(currentCpi), text_color=chart.fg_color)
    table.cell(stats, 0, 5, "CPI availability / effective", text_color=chart.fg_color)
    table.cell(stats, 1, 5, dateText(availableDate) + " / " + dateText(effectiveDate), text_color=chart.fg_color)
    table.cell(stats, 0, 6, "Observation age / limit", text_color=chart.fg_color)
    table.cell(stats, 1, 6, str.tostring(ageDays) + " / " + str.tostring(maxAgeDays) + " days", text_color=chart.fg_color)
    table.cell(stats, 0, 7, "Nominal return", text_color=chart.fg_color)
    table.cell(stats, 1, 7, numberText(nominal100 - 100) + "%", text_color=chart.fg_color)
    table.cell(stats, 0, 8, "Real return", text_color=chart.fg_color)
    table.cell(stats, 1, 8, numberText(real100 - 100) + "%", text_color=chart.fg_color)
    table.cell(stats, 0, 9, "CPI increase since base", text_color=chart.fg_color)
    table.cell(stats, 1, 9, numberText(inflationChange) + "%", text_color=chart.fg_color)
    table.cell(stats, 0, 10, "Real CAGR (>= 1 year)", text_color=chart.fg_color)
    table.cell(stats, 1, 10, numberText(realCagr) + "%", text_color=chart.fg_color)
    table.cell(stats, 0, 11, "Embedded effective coverage", text_color=chart.fg_color)
    table.cell(stats, 1, 11, "{effective_dates[0].isoformat()} — {effective_dates[-1].isoformat()}", text_color=chart.fg_color)
    table.cell(stats, 0, 12, "Status", text_color=chart.fg_color)
    table.cell(stats, 1, 12, na(real100) ? "Missing price/CPI, stale data or no eligible base" : barstate.isrealtime and not barstate.isconfirmed ? "Forming price bar; date-only CPI" : "Valid price/CPI pair", text_color=chart.fg_color)
'''
