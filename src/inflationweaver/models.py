# SPDX-License-Identifier: 0BSD
"""Small data contracts shared by the library, CLI, and service adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import polars as pl


@dataclass(frozen=True)
class Series:
    """An identified time series; values are levels except for monthly_rate.

    ``date`` is the observation date. ``available_date``, when supplied, is the
    first date on which that exact observation was publicly available. Missing
    availability is never interpreted as a known publication date.
    """

    series_id: str
    data: pl.DataFrame
    kind: str = "price"
    currency: str = "TRY"
    source: str = "user"
    synthetic: bool = False


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class AnalysisResult:
    """Comparable points plus summary statistics and provenance."""

    points: pl.DataFrame
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation without losing dates."""
        return _json_value(
            {
                "points": self.points.to_dicts(),
                "metrics": self.metrics,
                "metadata": self.metadata,
            }
        )
