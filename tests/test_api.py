# SPDX-License-Identifier: 0BSD
from fastapi.testclient import TestClient

from inflationweaver.api import create_app


def series(identifier="asset", kind="price", values=(100, 150), currency="TRY"):
    return {"series_id": identifier, "kind": kind, "currency": currency, "source": "synthetic-test",
            "synthetic": True, "data": [
                {"date": "2023-01-01", "value": values[0], "available_date": "2023-01-01"},
                {"date": "2023-02-01", "value": values[1], "available_date": "2023-02-05"}]}


def request():
    return {"asset": series(), "inflation": series("cpi", "cpi", (100, 125))}


def test_health_and_openapi():
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "ok"
    assert "/v1/backtest" in client.get("/openapi.json").json()["paths"]


def test_stored_series_retrieval_and_missing_series(tmp_path, monkeypatch):
    from inflationweaver.store import SeriesStore
    from inflationweaver.api import SeriesPayload
    monkeypatch.setenv("INFLATIONWEAVER_STORE", str(tmp_path))
    SeriesStore(tmp_path).write(SeriesPayload(**series()).to_series())
    client = TestClient(create_app())
    assert client.get("/v1/series/asset").json()["data"][1]["value"] == 150
    assert client.get("/v1/series/missing").status_code == 404


def test_real_return_uses_compound_ratio():
    response = TestClient(create_app()).post("/v1/analyze", json=request())
    assert response.status_code == 200, response.text
    result = response.json()
    assert abs(result["metrics"]["real_return_pct"] - 20) < 1e-10
    assert result["points"][-1]["real_index"] == 120
    assert result["metadata"]["synthetic"] is True


def test_unpublished_inflation_is_not_seen():
    payload = request()
    payload["asset"]["data"][1]["available_date"] = "2023-02-01"
    payload["alignment"] = "released"
    response = TestClient(create_app()).post("/v1/analyze", json=payload)
    assert response.status_code == 200, response.text
    assert abs(response.json()["metrics"]["real_return_pct"] - 50) < 1e-10


def test_rates_cannot_be_used_as_cpi_levels():
    payload = request()
    payload["inflation"]["kind"] = "monthly_rate"
    response = TestClient(create_app()).post("/v1/analyze", json=payload)
    assert response.status_code == 422


def test_wrong_currency_and_missing_publication_date_fail():
    client = TestClient(create_app())
    payload = request()
    payload["inflation"]["currency"] = "USD"
    assert client.post("/v1/analyze", json=payload).status_code == 422
    payload = request()
    payload["alignment"] = "released"
    payload["inflation"]["data"][1].pop("available_date")
    assert client.post("/v1/analyze", json=payload).status_code == 422


def test_extra_fields_nan_and_duplicate_dates_rejected():
    client = TestClient(create_app())
    payload = request()
    payload["secret"] = "unexpected"
    assert client.post("/v1/analyze", json=payload).status_code == 422
    payload = request()
    payload["asset"]["data"][1]["date"] = "2023-01-01"
    assert client.post("/v1/analyze", json=payload).status_code == 422


def test_compare_and_fixed_unit_portfolio():
    client = TestClient(create_app())
    assets = [series(), series("gold", values=(100, 100))]
    inflation = series("cpi", "cpi", (100, 125))
    response = client.post("/v1/compare", json={"assets": assets, "inflation": inflation})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"asset", "gold"}
    response = client.post("/v1/portfolio", json={"assets": assets, "weights": [0.5, 0.5],
                                               "inflation": inflation})
    assert response.status_code == 200, response.text
    assert abs(response.json()["metrics"]["real_return_pct"]) < 1e-10


def test_chain_endpoint_needs_contiguous_months():
    payload = {"rates": {"series_id": "rates", "kind": "monthly_rate", "currency": "TRY", "data": [
                {"date": "2023-02-01", "value": 10}, {"date": "2023-04-01", "value": 10}]},
               "anchor_date": "2023-01-01"}
    response = TestClient(create_app()).post("/v1/cpi/chain", json=payload)
    assert response.status_code == 422


def test_backtest_excludes_external_cashflows():
    payload = {"data": [{"date": "2023-01-01", "value": 100, "cashflow": 0},
                        {"date": "2023-02-01", "value": 150, "cashflow": 50}],
               "inflation": series("cpi", "cpi", (100, 100))}
    response = TestClient(create_app()).post("/v1/backtest", json=payload)
    assert response.status_code == 200, response.text
    assert abs(response.json()["metrics"]["real_return_pct"]) < 1e-10
