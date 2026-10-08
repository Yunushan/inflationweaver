"""Local immutable Parquet objects indexed by a parameterized DuckDB catalog."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
import uuid

import duckdb
import polars as pl

from .models import Series
from .providers import _normalize
from .engine import validate_series


WriteMode = Literal["error", "replace", "append", "update"]


def _identifier(series_id: str) -> str:
    if not isinstance(series_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}", series_id):
        raise ValueError("Series ID must be 1–128 letters/digits with '.', '_', ':', '+', or '-'; no paths")
    return series_id


class SeriesStore:
    """A single-machine store with explicit overwrite semantics.

    DuckDB transactions make the catalog switch atomic. Each Parquet write has a
    distinct name, so an interrupted write cannot corrupt the active version.
    ``manifest.json`` is a convenient snapshot, not the authoritative index.
    Use one writer at a time; this is not a multi-host database service.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "objects").mkdir(exist_ok=True)
        self.database = self.root / "catalog.duckdb"
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS series_catalog (series_id VARCHAR PRIMARY KEY, relative_path VARCHAR NOT NULL, metadata VARCHAR NOT NULL)")

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.database))

    def _entry(self, series_id: str) -> tuple[str, dict] | None:
        _identifier(series_id)
        with self._connect() as connection:
            row = connection.execute("SELECT relative_path, metadata FROM series_catalog WHERE series_id = ?", [series_id]).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def list(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT metadata FROM series_catalog ORDER BY series_id").fetchall()
        return [json.loads(row[0]) for row in rows]

    def read(self, series_id: str) -> Series:
        entry = self._entry(series_id)
        if entry is None:
            raise KeyError(f"Unknown series: {series_id}")
        relative_path, meta = entry
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root / "objects"):
            raise ValueError("Catalog path escapes the store object directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            raise ValueError(f"Stored Parquet checksum failed for {series_id}")
        # The path is a bound value, never interpolated into SQL. Avoid requiring
        # pyarrow merely to materialize this small canonical table.
        with self._connect() as connection:
            result = connection.execute("SELECT * FROM read_parquet(?) ORDER BY date", [str(path)])
            columns = [column[0] for column in result.description]
            rows = result.fetchall()
            frame = pl.DataFrame(rows, schema=columns, orient="row", infer_schema_length=None)
        return Series(series_id, _normalize(frame), meta["kind"], meta["currency"], meta["source"], meta["synthetic"])

    def write(self, series: Series, mode: WriteMode = "error") -> dict:
        """Persist a series; default rejects overwriting an existing identifier.

        replace: entire series and metadata become the supplied input.
        append: all supplied dates must be later than existing observations.
        update: supplied dates replace overlaps, other dates remain intact.
        append/update require matching kind/currency/source/synthetic metadata.
        """
        series_id = _identifier(series.series_id)
        if mode not in {"error", "replace", "append", "update"}:
            raise ValueError("mode must be error, replace, append, or update")
        frame = _normalize(validate_series(series).data)
        previous = self._entry(series_id)
        old_meta = previous[1] if previous else None
        if previous and mode == "error":
            raise FileExistsError(f"Series {series_id} exists; choose replace, append, or update explicitly")
        metadata = {"series_id": series_id, "kind": series.kind, "currency": series.currency, "source": series.source, "synthetic": series.synthetic}
        if previous and mode in {"append", "update"}:
            for key in ("kind", "currency", "source", "synthetic"):
                if old_meta[key] != metadata[key]:
                    raise ValueError(f"Cannot {mode} series with conflicting {key}")
            existing = self.read(series_id).data
            if mode == "append" and frame["date"].min() <= existing["date"].max():
                raise ValueError("append accepts only dates later than the stored last date; use update for revisions")
            frame = _normalize(pl.concat([existing, frame], how="diagonal_relaxed").unique(subset=["date"], keep="last", maintain_order=True).sort("date"))
        now = datetime.now(timezone.utc).isoformat()
        relative_path = Path("objects") / f"{hashlib.sha256(series_id.encode()).hexdigest()[:24]}-{uuid.uuid4().hex}.parquet"
        path = self.root / relative_path
        temporary = path.with_suffix(".tmp")
        try:
            frame.write_parquet(temporary, compression="zstd")
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            temporary.replace(path)
            metadata.update({"schema_version": 1, "rows": frame.height, "start_date": frame["date"].min().isoformat(), "end_date": frame["date"].max().isoformat(), "release_dates_present": "available_date" in frame.columns, "columns": frame.columns, "sha256": digest, "parquet_path": relative_path.as_posix(), "created_at": old_meta["created_at"] if old_meta else now, "updated_at": now, "last_write_mode": mode, "provenance": {"source": series.source, "synthetic": series.synthetic, "previous_sha256": old_meta["sha256"] if old_meta else None}})
            with self._connect() as connection:
                connection.execute("BEGIN TRANSACTION")
                connection.execute("INSERT INTO series_catalog VALUES (?, ?, ?) ON CONFLICT (series_id) DO UPDATE SET relative_path = excluded.relative_path, metadata = excluded.metadata", [series_id, relative_path.as_posix(), json.dumps(metadata, sort_keys=True)])
                connection.execute("COMMIT")
        except Exception:
            temporary.unlink(missing_ok=True)
            # A completed unreferenced object is safe to remove on catalog failure.
            if path.exists() and (self._entry(series_id) or (None,))[0] != relative_path.as_posix():
                path.unlink()
            raise
        self._write_manifest()
        return metadata

    def _write_manifest(self) -> None:
        manifest = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "series": self.list()}
        temporary = self.root / f"manifest-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.root / "manifest.json")
