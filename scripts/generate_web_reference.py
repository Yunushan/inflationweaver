# SPDX-License-Identifier: 0BSD
"""Regenerate API-backed browser parity fixtures; --check detects engine drift."""
import argparse
import copy
import json
import math
from pathlib import Path
from fastapi.testclient import TestClient
from inflationweaver.api import create_app


def equivalent(left, right):
    if isinstance(left, float) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-9)
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equivalent(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return left == right


def series(identifier, kind, rows):
    return {"series_id": identifier, "kind": kind, "currency": "TRY", "source": "synthetic-parity-test",
            "synthetic": True, "data": [{"date": d, "value": v, "available_date": a} for d, v, a in rows]}


def fixtures():
    days = ["2024-01-31", "2024-02-29", "2024-03-31"]
    simple = {"asset": series("TEST_PRICE", "price", list(zip(days, [100, 120, 180], days))),
              "inflation": series("TEST_CPI", "cpi", list(zip(days, [100, 110, 150], days))),
              "alignment": "observation", "max_staleness_days": 62}
    displayed = copy.deepcopy(simple)
    displayed.update(base_date="2024-01-31", start_date="2024-02-29")
    displayed["asset"]["data"][1]["value"] = 80
    released = copy.deepcopy(simple)
    released["alignment"] = "released"
    released["asset"]["data"][0]["available_date"] = "2024-02-02"
    released["inflation"]["data"][1]["available_date"] = "2024-03-03"
    late = {"asset": series("TEST_PRICE", "price", [("2024-03-30", 100, "2024-03-30"), ("2024-03-31", 110, "2024-03-31")]),
            "inflation": series("TEST_CPI", "cpi", [("2024-01-31", 100, "2024-03-20"), ("2024-02-29", 110, "2024-03-03")]),
            "alignment": "released", "max_staleness_days": 62}
    old_days = ["1986-01-31", "1986-02-28", "1986-03-31"]
    historical = {"asset": series("SYNTHETIC_1986", "price", list(zip(old_days, [1, 1.2, 1.8], old_days))),
                  "inflation": series("SYNTHETIC_1986_CPI", "cpi", list(zip(old_days, [100, 110, 150], old_days))),
                  "alignment": "observation", "max_staleness_days": 62}
    client = TestClient(create_app())
    results = []
    for name, body in [("compound-ratio", simple), ("base-before-display", displayed),
                       ("released", released), ("late-old-release", late), ("synthetic-1986-dates", historical)]:
        response = client.post("/v1/analyze", json=body)
        if response.status_code != 200:
            raise RuntimeError(f"Fixture {name} failed: {response.text}")
        results.append({"name": name, "request": body, "result": response.json()})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "web/tests/fixtures/engine-reference.json"
    content = json.dumps(fixtures(), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.check:
        if not equivalent(json.loads(target.read_text()), json.loads(content)):
            raise SystemExit("Browser fixtures differ from Python API; regenerate and rerun web tests")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
