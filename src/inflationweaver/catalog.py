"""Instrument metadata; membership does not imply a bundled market-data feed."""

from importlib.resources import files
import json


def get_catalog() -> dict:
    return json.loads(files("inflationweaver").joinpath("data/catalog.json").read_text(encoding="utf-8"))


def list_assets() -> list[dict]:
    return get_catalog()["series"]


def get_asset(series_id: str) -> dict:
    for asset in list_assets():
        if asset["series_id"] == series_id:
            return asset
    raise KeyError(f"Unknown catalog identifier: {series_id}")
