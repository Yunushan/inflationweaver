"""Portable CSV/JSON/Markdown outputs. SPDX-License-Identifier: 0BSD."""

import json
from pathlib import Path


def write_report(result, destination: str | Path) -> Path:
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    (path / "analysis.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False,
                                                 allow_nan=False, default=str) + "\n", encoding="utf-8")
    result.points.write_csv(path / "analysis.csv")
    lines = ["# InflationWeaver analysis", "", "Generated from explicitly supplied input series.", "",
             "## Metrics", "", "| Metric | Value |", "| --- | ---: |"]
    for key, value in result.metrics.items():
        display = "N/A" if value is None else f"{value:.6f}" if isinstance(value, (int, float)) else str(value)
        lines.append(f"| {key} | {display} |")
    lines += ["", "## Provenance and alignment", "", "```json",
              json.dumps(result.metadata, indent=2, ensure_ascii=False, default=str), "```", ""]
    (path / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return path
