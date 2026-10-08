# SPDX-License-Identifier: 0BSD
"""Data contract tests use local fixtures and mocked HTTP, never live secrets."""

from datetime import date
import json

import httpx
import polars as pl
import pytest

from inflationweaver.catalog import get_asset, get_catalog, list_assets
from inflationweaver.engine import portfolio_curve, splice_cpi
from inflationweaver.models import Series
from inflationweaver.providers import (
    ProviderError, fetch_evds, fetch_fred, fetch_oecd, read_csv, write_csv,
)
from inflationweaver.store import SeriesStore


def series(values=(100.0, 110.0), dates=("2024-01-01", "2024-02-01"), **kwargs):
    return Series("TEST_ASSET", pl.DataFrame({"date": dates, "value": values}), **kwargs)


def response(payload=None, *, text=None, status=200):
    return httpx.Response(status, json=payload if text is None else None, text=text, request=httpx.Request("GET", "https://example.test"))


def test_csv_preserves_published_values_and_release_dates(tmp_path):
    path = tmp_path / "published.csv"
    path.write_text("date,value,available_date,published_mom,published_yoy,source_url\n2024-02,104,2024-03-04,4,70,https://example.test/release\n2024-01,100,2024-02-03,3,68,https://example.test/previous\n")
    imported = read_csv(path, "ENAG_TEST", kind="cpi")
    assert imported.data["date"].to_list() == [date(2024, 1, 1), date(2024, 2, 1)]
    assert imported.data["published_mom"].to_list() == [3, 4]
    assert imported.data["available_date"][1] == date(2024, 3, 4)


@pytest.mark.parametrize("body", [
    "date,value\n2024-01-01,100\n2024-01-01,101\n",
    "date,value\n2024-01-01,NaN\n",
    "date,value\n2024-01-01,-2\n",
    "date,value,available_date\n2024-02-01,100,2024-01-01\n",
])
def test_csv_rejects_invalid_input(tmp_path, body):
    path = tmp_path / "invalid.csv"
    path.write_text(body)
    with pytest.raises(ValueError):
        read_csv(path, "TEST")


def test_csv_roundtrip_checks_sidecar_and_metadata(tmp_path):
    original = series()
    path = write_csv(original, tmp_path / "export.csv")
    imported = read_csv(path, original.series_id)
    assert imported.data["value"].to_list() == list(original.data["value"])
    with pytest.raises(ProviderError, match="conflicts"):
        read_csv(path, original.series_id, currency="USD")
    path.write_text(path.read_text().replace("110.0", "120.0"))
    with pytest.raises(ProviderError, match="checksum"):
        read_csv(path, original.series_id)


def test_unknown_publication_dates_roundtrip_without_invention(tmp_path):
    original = Series("DERIVED_CPI", pl.DataFrame({"date": [date(2023, 12, 1), date(2024, 1, 1)],
        "value": [100., 104.], "available_date": [None, date(2024, 2, 3)]}), kind="cpi")
    path = write_csv(original, tmp_path / "derived.csv")
    restored = read_csv(path, original.series_id, kind="cpi")
    assert restored.data["available_date"][0] is None
    from inflationweaver.engine import analyze
    with pytest.raises(ValueError, match="available_date"):
        analyze(series(), restored, alignment="released")


def test_store_explicit_revisions_and_manifest(tmp_path):
    store = SeriesStore(tmp_path)
    first = store.write(series())
    assert store.read("TEST_ASSET").data["value"].to_list() == [100.0, 110.0]
    with pytest.raises(FileExistsError):
        store.write(series())
    with pytest.raises(ValueError, match="later"):
        store.write(series(values=(112,), dates=("2024-02-01",)), mode="append")
    store.write(series(values=(120,), dates=("2024-03-01",)), mode="append")
    last = store.write(series(values=(115,), dates=("2024-02-01",)), mode="update")
    assert store.read("TEST_ASSET").data["value"].to_list() == [100.0, 115.0, 120.0]
    assert last["provenance"]["previous_sha256"] != first["sha256"]
    assert json.loads((tmp_path / "manifest.json").read_text())["series"][0]["rows"] == 3
    store.write(series(values=(80,), dates=("2024-01-01",)), mode="replace")
    assert store.list()[0]["rows"] == 1


def test_store_rejects_metadata_mismatch_and_identifier_injection(tmp_path):
    store = SeriesStore(tmp_path)
    store.write(series())
    with pytest.raises(ValueError, match="currency"):
        store.write(series(currency="USD"), mode="update")
    for identifier in ("../escape", "x'; DROP TABLE series_catalog;--", "/tmp/x"):
        with pytest.raises(ValueError):
            store.write(Series(identifier, series().data))


def test_store_accepts_derived_series_identifiers(tmp_path):
    store = SeriesStore(tmp_path)
    asset_a = Series("A", series().data)
    asset_b = Series("B", series(values=(200.0, 180.0)).data)
    derived = [portfolio_curve([asset_a, asset_b], [.5, .5]),
               splice_cpi(Series("A", asset_a.data, kind="cpi"),
                          Series("B", asset_b.data, kind="cpi"), "2024-01-01")]
    for original in derived:
        store.write(original)
        restored = store.read(original.series_id)
        assert restored.series_id == original.series_id
        assert restored.data["value"].to_list() == original.data["value"].to_list()


def test_store_detects_parquet_tampering(tmp_path):
    store = SeriesStore(tmp_path)
    metadata = store.write(series())
    (tmp_path / metadata["parquet_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        store.read("TEST_ASSET")


def test_store_rejects_catalog_path_escape(tmp_path):
    store = SeriesStore(tmp_path)
    store.write(series())
    with store._connect() as connection:
        connection.execute("UPDATE series_catalog SET relative_path=? WHERE series_id=?", ["../../escape", "TEST_ASSET"])
    with pytest.raises(ValueError, match="escapes"):
        store.read("TEST_ASSET")


def test_fred_levels_missing_values_and_pagination(monkeypatch):
    calls = []
    def mocked_get(url, **kwargs):
        calls.append((url, dict(kwargs["params"])))
        if kwargs["params"]["offset"] == 0:
            return response({"count": 3, "observations": [{"date": "2024-01-01", "value": "100", "realtime_start": "2026-10-08"}, {"date": "2024-02-01", "value": "."}]})
        return response({"count": 3, "observations": [{"date": "2024-03-01", "value": "102"}]})
    monkeypatch.setattr(httpx, "get", mocked_get)
    fetched = fetch_fred("CPIAUCSL", "2024-01-01", "2024-12-31", api_key="secret")
    assert fetched.data["value"].to_list() == [100.0, 102.0]
    assert calls[0][0] == "https://api.stlouisfed.org/fred/series/observations"
    assert calls[0][1]["units"] == "lin"
    assert calls[1][1]["offset"] == 2
    assert "available_date" not in fetched.data.columns
    assert "secret" not in fetched.source


def test_provider_keys_required_and_errors_redacted(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("EVDS_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="FRED_API_KEY"):
        fetch_fred("TEST", "2024-01-01", "2024-12-31")
    with pytest.raises(ProviderError, match="EVDS_API_KEY"):
        fetch_evds("TEST", "2024-01-01", "2024-12-31")
    def raises(*args, **kwargs):
        raise httpx.ConnectError("secret-api-key was in the raw request URL")
    monkeypatch.setattr(httpx, "get", raises)
    with pytest.raises(ProviderError) as caught:
        fetch_fred("TEST", "2024-01-01", "2024-12-31", api_key="secret-api-key")
    assert "secret-api-key" not in str(caught.value)


def test_evds_key_header_date_contract(monkeypatch):
    calls = []
    def mocked_get(url, **kwargs):
        calls.append((url, kwargs))
        return response({"items": [{"Tarih": "01-01-2024", "TP_DK_USD_A_YTL": "30.0"}, {"Tarih": "02-01-2024", "TP_DK_USD_A_YTL": None}]})
    monkeypatch.setattr(httpx, "get", mocked_get)
    fetched = fetch_evds("TP.DK.USD.A.YTL", "2024-01-01", "2024-01-02", api_key="secret", kind="fx")
    assert fetched.data["value"].to_list() == [30.0]
    assert "startDate=01-01-2024" in calls[0][0]
    assert "endDate=02-01-2024" in calls[0][0]
    assert "secret" not in calls[0][0]
    assert calls[0][1]["headers"] == {"key": "secret"}
    assert calls[0][1]["follow_redirects"] is False


def test_redirect_and_status_do_not_expose_keys(monkeypatch):
    for status in (302, 401, 429, 500):
        monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response(status=status))
        with pytest.raises(ProviderError) as caught:
            fetch_fred("TEST", "2024-01-01", "2024-01-02", api_key="secret")
        assert "secret" not in str(caught.value)


def test_oecd_filters_are_explicit_and_single_series(monkeypatch):
    body = "REF_AREA,FREQ,TIME_PERIOD,OBS_VALUE\nUSA,M,2024-01,100\nTUR,M,2024-01,110\nTUR,M,2024-02,112\n"
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response(text=body))
    fetched = fetch_oecd("https://sdmx.oecd.org/public/rest/data/example?format=csvfile", "OECD_TEST", {"REF_AREA": "TUR", "FREQ": "M"}, currency="TRY")
    assert fetched.data["value"].to_list() == [110.0, 112.0]
    with pytest.raises(ProviderError, match="filters"):
        fetch_oecd("https://sdmx.oecd.org/public/rest/data/example", "TEST", {})
    with pytest.raises(ProviderError, match="HTTPS"):
        fetch_oecd("https://untrusted.test/data", "TEST", {"FREQ": "M"})
    with pytest.raises(ProviderError, match="Duplicate"):
        fetch_oecd("https://sdmx.oecd.org/public/rest/data/example", "TEST", {"FREQ": "M"})


def test_catalog_is_metadata_only():
    assert get_catalog()["schema_version"] == 1
    assert all(asset["bundled_data"] is False for asset in list_assets())
    assert get_asset("XU100")["currency"] == "TRY"
    assert get_asset("US_CPI")["provider_id"] == "CPIAUCSL"
    assert get_asset("ENAG_MOM")["kind"] == "monthly_rate"
