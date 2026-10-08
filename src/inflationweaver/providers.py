"""Explicit, auditable imports and official-provider adapters.

No adapter invents an observation or derives monthly inflation from a yearly rate.
Release dates must be supplied from release/vintage data, not inferred from periods.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

import httpx
import polars as pl

from .models import Series
from .engine import validate_series


class ProviderError(ValueError):
    """A source failed validation, authentication, or a documented response contract."""


def _iso_day(value: str | date, *, field: str = "date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}", value):
        value += "-01"
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ProviderError(f"{field} must be an ISO YYYY-MM-DD date (or YYYY-MM period): {value!r}") from exc


def _normalize(frame: pl.DataFrame) -> pl.DataFrame:
    if not {"date", "value"}.issubset(frame.columns):
        raise ProviderError("CSV must contain date,value columns")
    if frame.is_empty():
        raise ProviderError("Source contains no usable observations")
    dates = [_iso_day(v) for v in frame["date"].to_list()]
    if any(isinstance(v, bool) for v in frame["value"].to_list()):
        raise ProviderError("Observation values must be numbers, not booleans")
    try:
        values = [float(v) for v in frame["value"].to_list()]
    except (TypeError, ValueError) as exc:
        raise ProviderError("Every observation value must be numeric and nonmissing") from exc
    if any(not math.isfinite(v) for v in values):
        raise ProviderError("Observation values must be finite")
    if len(set(dates)) != len(dates):
        raise ProviderError("Duplicate observation dates; select one series/vintage before import")
    result = frame.with_columns(pl.Series("date", dates, dtype=pl.Date), pl.Series("value", values))
    if "available_date" in result.columns:
        available = [_iso_day(v, field="available_date") if v not in (None, "") else None for v in result["available_date"].to_list()]
        if any(a is not None and a < d for a, d in zip(available, dates, strict=True)):
            raise ProviderError("available_date cannot precede its observation period")
        result = result.with_columns(pl.Series("available_date", available, dtype=pl.Date))
    return result.sort("date")


def read_csv(
    path: str | Path,
    series_id: str,
    kind: str = "price",
    currency: str = "TRY",
    source: str = "user",
    synthetic: bool = False,
) -> Series:
    """Read canonical CSV, preserving extra published and provenance columns.

    Metadata arguments are authoritative. A checksum-bearing export sidecar is
    verified when present; conflicting metadata is rejected, not silently reused.
    Decimal points and ISO dates are deliberate defaults (no locale guessing).
    """
    path = Path(path)
    raw = path.read_bytes()
    sidecar = path.with_suffix(path.suffix + ".metadata.json")
    if sidecar.exists():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        if meta.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise ProviderError("CSV checksum does not match its metadata sidecar")
        supplied = {"series_id": series_id, "kind": kind, "currency": currency, "source": source, "synthetic": synthetic}
        for key, value in supplied.items():
            if key in meta and meta[key] != value:
                raise ProviderError(f"CSV metadata conflicts with requested {key}")
    frame = pl.read_csv(io.BytesIO(raw), try_parse_dates=False, infer_schema_length=None)
    return validate_series(Series(series_id, _normalize(frame), kind, currency, source, synthetic))


def write_csv(series: Series, path: str | Path) -> Path:
    """Export canonical CSV with a checksum-bearing metadata sidecar."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = _normalize(validate_series(series).data)
    raw = frame.write_csv().encode("utf-8")
    path.write_bytes(raw)
    meta = {"schema_version": 1, "series_id": series.series_id, "kind": series.kind, "currency": series.currency, "source": series.source, "synthetic": series.synthetic, "sha256": hashlib.sha256(raw).hexdigest(), "rows": frame.height}
    path.with_suffix(path.suffix + ".metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return path


def _request(url: str, *, params: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None) -> httpx.Response:
    """GET with bounded timeout, no redirects and no credential-bearing errors."""
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=30.0, follow_redirects=False)
    except httpx.HTTPError:
        # HTTP library errors can include query strings containing API keys.
        raise ProviderError("Provider connection failed; check connectivity and provider status") from None
    if response.is_redirect:
        raise ProviderError("Provider endpoint redirected; verify the documented endpoint before sending credentials")
    if not response.is_success:
        raise ProviderError(f"Provider returned HTTP {response.status_code}; check credentials, request, and provider status")
    return response


def _interval(start: str | date, end: str | date) -> tuple[date, date]:
    first, last = _iso_day(start, field="start"), _iso_day(end, field="end")
    if first > last:
        raise ProviderError("start must be on or before end")
    return first, last


def fetch_fred(series_id: str, start: str | date, end: str | date, api_key: str | None = None, *, kind: str = "cpi", currency: str = "USD") -> Series:
    """Download FRED levels, paging observations; missing '.' values are skipped.

    Current-vintage realtime_start is not the original release date. The returned
    series intentionally has no available_date; attach an audited release file
    before publication-aware backtests. No automatic transformations are applied.
    """
    key = api_key or os.getenv("FRED_API_KEY")
    if not key:
        raise ProviderError("Set FRED_API_KEY or supply api_key")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", series_id):
        raise ProviderError("Invalid FRED series identifier")
    first, last = _interval(start, end)
    params: dict[str, Any] = {"series_id": series_id, "api_key": key, "file_type": "json", "units": "lin", "observation_start": first.isoformat(), "observation_end": last.isoformat(), "sort_order": "asc", "limit": 100000, "offset": 0}
    rows: list[dict[str, Any]] = []
    while True:
        try:
            payload = _request("https://api.stlouisfed.org/fred/series/observations", params=params).json()
            observations = payload["observations"]
            if not isinstance(observations, list):
                raise TypeError
            for observation in observations:
                if observation.get("value") in (None, ".", ""):
                    continue
                rows.append({"date": observation["date"], "value": observation["value"]})
            count = int(payload.get("count", len(observations)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("FRED response does not match its observations contract") from exc
        params["offset"] += len(observations)
        if params["offset"] >= count:
            break
        if not observations:
            raise ProviderError("FRED pagination ended before the reported count")
    frame = _normalize(pl.DataFrame(rows, schema={"date": pl.String, "value": pl.String}))
    if frame["date"].min() < first or frame["date"].max() > last:
        raise ProviderError("FRED returned observations outside the requested interval")
    return validate_series(Series(series_id, frame, kind, currency, "FRED:current-vintage", False))


def _evds_date(value: str) -> date:
    value = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y-%m", "%Y-%m-01"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # EVDS monthly periods can be supplied as YYYY-MM or MM-YYYY.
    try:
        return datetime.strptime(value, "%m-%Y").date()
    except ValueError as exc:
        raise ProviderError(f"Unsupported EVDS observation date: {value!r}") from exc


def fetch_evds(series_code: str, start: str | date, end: str | date, api_key: str | None = None, *, kind: str = "cpi", currency: str = "TRY") -> Series:
    """Single-series documented EVDS2 compatibility endpoint, key in HTTP header.

    EVDS3 is the new portal. Redirects deliberately fail rather than leaking a
    credential or implying verified compatibility with an undocumented API.
    """
    key = api_key or os.getenv("EVDS_API_KEY")
    if not key:
        raise ProviderError("Set EVDS_API_KEY or supply api_key")
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,128}", series_code):
        raise ProviderError("Use one explicit EVDS series code")
    first, last = _interval(start, end)
    params = {"series": series_code, "startDate": first.strftime("%d-%m-%Y"), "endDate": last.strftime("%d-%m-%Y"), "type": "json", "formulas": "0"}
    # EVDS documentation places its arguments in the path, not a ? query.
    endpoint = "https://evds2.tcmb.gov.tr/service/evds/" + urlencode(params)
    try:
        payload = _request(endpoint, headers={"key": key}).json()
        items = payload["items"]
        if not isinstance(items, list):
            raise TypeError
        column = series_code.replace(".", "_")
        rows = []
        for row in items:
            value = row.get(column, row.get(series_code))
            if value in (None, "", "."):
                continue
            rows.append({"date": _evds_date(row["Tarih"]), "value": float(value)})
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("EVDS response does not match its single-series items contract") from exc
    frame = _normalize(pl.DataFrame(rows, schema={"date": pl.Date, "value": pl.Float64}))
    if frame["date"].min() < first or frame["date"].max() > last:
        raise ProviderError("EVDS returned observations outside the requested interval")
    return validate_series(Series(series_code, frame, kind, currency, "TCMB:EVDS2", False))


def fetch_oecd(
    url: str,
    series_id: str,
    filters: Mapping[str, str],
    *,
    kind: str = "cpi",
    currency: str = "USD",
    date_column: str = "TIME_PERIOD",
    value_column: str = "OBS_VALUE",
) -> Series:
    """Fetch an OECD Data Explorer SDMX CSV query with explicit dimension filters.

    Copy an actual query from the OECD builder. Dataset keys vary; this adapter
    never claims a universal CPI mapping. Remaining duplicate dates are an error.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "sdmx.oecd.org" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ProviderError("OECD URL must be an HTTPS query on sdmx.oecd.org")
    if not filters:
        raise ProviderError("Specify dimension filters explicitly (for example REF_AREA and FREQ)")
    response = _request(url, headers={"Accept": "text/csv"})
    try:
        frame = pl.read_csv(io.StringIO(response.text), infer_schema_length=None)
        for column, value in filters.items():
            if column not in frame.columns:
                raise ProviderError(f"OECD filter dimension is missing: {column}")
            frame = frame.filter(pl.col(column).cast(pl.String) == str(value))
        if date_column not in frame.columns or value_column not in frame.columns:
            raise ProviderError("OECD date/value columns are absent; select CSV format in the query")
        # An observation status/footnote is not a numerical value.
        frame = frame.filter(pl.col(value_column).is_not_null()).select(pl.col(date_column).alias("date"), pl.col(value_column).alias("value"))
        frame = _normalize(frame)
    except pl.exceptions.PolarsError as exc:
        raise ProviderError("OECD response is not a supported CSV table") from exc
    return validate_series(Series(series_id, frame, kind, currency, "OECD:SDMX-current", False))
