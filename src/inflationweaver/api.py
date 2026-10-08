"""Local REST API; data is supplied explicitly. SPDX-License-Identifier: 0BSD."""

import os
import re
from datetime import date
from typing import Annotated, Literal

import polars as pl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import __version__
from .backtest import analyze_backtest
from .engine import analyze, chain_monthly_rates, compare_assets, portfolio_curve, splice_cpi
from .models import Series
from .store import SeriesStore


def _calendar_date(value):
    if value is None or type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise ValueError("Use a calendar date in YYYY-MM-DD format")


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    date: date
    value: float = Field(strict=True)
    available_date: date | None = None

    @field_validator("date", "available_date", mode="before")
    @classmethod
    def calendar_dates(cls, value):
        return _calendar_date(value)


class SeriesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series_id: str = Field(min_length=1, max_length=120)
    kind: Literal["price", "cpi", "monthly_rate", "wealth", "fx"] = "price"
    currency: str = Field(default="TRY", min_length=3, max_length=8)
    source: str = Field(default="user", max_length=1000)
    synthetic: bool = False
    data: list[Observation] = Field(min_length=1, max_length=50000)

    def to_series(self) -> Series:
        rows = [item.model_dump() for item in self.data]
        if all(row["available_date"] is None for row in rows):
            rows = [{"date": row["date"], "value": row["value"]} for row in rows]
        return Series(self.series_id, pl.DataFrame(rows), self.kind, self.currency,
                      self.source, self.synthetic)


class AnalysisOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    alignment: Literal["observation", "released"] = "observation"
    max_staleness_days: int = Field(default=62, ge=0, le=3660, strict=True)

    @field_validator("base_date", "start_date", "end_date", mode="before")
    @classmethod
    def calendar_dates(cls, value):
        return _calendar_date(value)

    def options(self) -> dict:
        return {name: getattr(self, name) for name in AnalysisOptions.model_fields}


class AnalyzeRequest(AnalysisOptions):
    asset: SeriesPayload
    inflation: SeriesPayload


class CompareRequest(AnalysisOptions):
    assets: list[SeriesPayload] = Field(min_length=1, max_length=20)
    inflation: SeriesPayload


class PortfolioRequest(AnalysisOptions):
    assets: list[SeriesPayload] = Field(min_length=1, max_length=20)
    weights: list[Annotated[float, Field(ge=0, le=1, strict=True)]] = Field(min_length=1, max_length=20)
    initial_value: float = Field(default=100, gt=0, allow_inf_nan=False, strict=True)
    inflation: SeriesPayload | None = None


class ChainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rates: SeriesPayload
    anchor_date: date
    anchor_value: float = Field(default=100, gt=0, allow_inf_nan=False, strict=True)

    @field_validator("anchor_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return _calendar_date(value)


class SpliceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: SeriesPayload
    right: SeriesPayload
    splice_date: date

    @field_validator("splice_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return _calendar_date(value)


class BacktestRow(Observation):
    cashflow: float = Field(default=0, strict=True)


class BacktestRequest(AnalysisOptions):
    data: list[BacktestRow] = Field(min_length=2, max_length=50000)
    inflation: SeriesPayload
    currency: str = "TRY"


def series_payload(series: Series) -> dict:
    return {"series_id": series.series_id, "kind": series.kind, "currency": series.currency,
            "source": series.source, "synthetic": series.synthetic,
            "data": series.data.to_dicts()}


def create_app() -> FastAPI:
    app = FastAPI(title="InflationWeaver", version=__version__,
                  description="Explicit-input inflation and real-return analytics. Demo data is synthetic.")
    origins = os.getenv("INFLATIONWEAVER_CORS_ORIGINS",
                        "http://localhost:3000,http://127.0.0.1:3000")
    app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in origins.split(",") if s.strip()],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def execute(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/v1/catalog")
    def catalog():
        from .catalog import get_catalog
        return get_catalog()

    @app.get("/v1/series")
    def list_series():
        return SeriesStore(os.getenv("INFLATIONWEAVER_STORE", "data/local")).list()

    @app.get("/v1/series/{series_id}")
    def get_series(series_id: str):
        try:
            result = SeriesStore(os.getenv("INFLATIONWEAVER_STORE", "data/local")).read(series_id)
        except (FileNotFoundError, KeyError) as exc:
            raise HTTPException(status_code=404, detail="Series not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return series_payload(result)

    @app.post("/v1/analyze")
    def analyze_endpoint(body: AnalyzeRequest):
        return execute(analyze, body.asset.to_series(), body.inflation.to_series(),
                       **body.options()).to_dict()

    @app.post("/v1/compare")
    def compare_endpoint(body: CompareRequest):
        result = execute(compare_assets, [item.to_series() for item in body.assets],
                         body.inflation.to_series(), **body.options())
        return {key: value.to_dict() for key, value in result.items()}

    @app.post("/v1/portfolio")
    def portfolio_endpoint(body: PortfolioRequest):
        series = execute(portfolio_curve, [item.to_series() for item in body.assets],
                         body.weights, initial_value=body.initial_value)
        if body.inflation is not None:
            return execute(analyze, series, body.inflation.to_series(), **body.options()).to_dict()
        return series_payload(series)

    @app.post("/v1/cpi/chain")
    def chain_endpoint(body: ChainRequest):
        return series_payload(execute(chain_monthly_rates, body.rates.to_series(),
                                      body.anchor_date, body.anchor_value))

    @app.post("/v1/cpi/splice")
    def splice_endpoint(body: SpliceRequest):
        return series_payload(execute(splice_cpi, body.left.to_series(), body.right.to_series(),
                                      body.splice_date))

    @app.post("/v1/backtest")
    def backtest_endpoint(body: BacktestRequest):
        frame = pl.DataFrame([item.model_dump() for item in body.data])
        if frame["available_date"].null_count() == frame.height:
            frame = frame.drop("available_date")
        return execute(analyze_backtest, frame, body.inflation.to_series(), currency=body.currency,
                       cashflow_column="cashflow", **body.options()).to_dict()

    return app


app = create_app()
