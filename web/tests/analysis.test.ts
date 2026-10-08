// SPDX-License-Identifier: 0BSD
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { analyzeLocal } from "../lib/analyze.ts";
import { validateRows, type AnalysisRequest, type Series } from "../lib/model.ts";
import { parseCsv } from "../lib/files.ts";

const make = (id: string, kind: string, rows: [string, number, string?][]): Series => ({ series_id: id, kind, currency: "TRY", source: "Test fixture", synthetic: true, data: rows.map(([date, value, available_date]) => ({ date, value, ...(available_date ? { available_date } : {}) })) });
const request = (): AnalysisRequest => ({
  asset: make("TEST_PRICE", "price", [["2024-01-31", 100, "2024-01-31"], ["2024-02-29", 120, "2024-02-29"], ["2024-03-31", 180, "2024-03-31"]]),
  inflation: make("TEST_CPI", "cpi", [["2024-01-31", 100, "2024-01-31"], ["2024-02-29", 110, "2024-02-29"], ["2024-03-31", 150, "2024-03-31"]]),
  alignment: "observation", max_staleness_days: 62,
});

test("compound real return uses division, not percentage subtraction", () => {
  const result = analyzeLocal(request());
  assert.equal(result.metrics.nominal_return_pct, 80);
  assert.equal(result.metrics.inflation_return_pct, 50);
  assert.ok(Math.abs(result.metrics.real_return_pct - 20) < 1e-10);
  assert.equal(result.points.at(-1)?.real_index, 120);
  assert.equal(result.points.at(-1)?.real_value, 120);
});

test("explicit base precedes display range and preserves metrics and drawdown peaks", () => {
  const input = request();
  input.asset.data[1].value = 80;
  input.base_date = "2024-01-31";
  input.start_date = "2024-02-29";
  const result = analyzeLocal(input);
  assert.equal(result.points.length, 2);
  assert.equal(result.points[0].nominal_index, 80);
  assert.ok(Math.abs(result.points[0].nominal_drawdown + 20) < 1e-10);
  assert.equal(result.metrics.nominal_return_pct, 80);
  assert.equal(result.metrics.observations, 3);
  assert.equal(result.metadata.actual_base_date, "2024-01-31");
  assert.equal(result.metadata.actual_display_start_date, "2024-02-29");
});

test("released data uses decision dates and only CPI already published", () => {
  const input = request();
  input.alignment = "released";
  input.asset.data[0].available_date = "2024-02-02";
  input.inflation.data[1].available_date = "2024-03-03";
  const result = analyzeLocal(input);
  assert.equal(result.points[0].date, "2024-02-02");
  assert.equal(result.points[0].asset_observation_date, "2024-01-31");
  assert.equal(result.points[1].inflation_observation_date, "2024-01-31");
  assert.equal(result.points[1].inflation_index, 100);
});

test("later release of an older CPI period never overrides a newer known period", () => {
  const input = request();
  input.alignment = "released";
  input.asset.data = [{ date: "2024-03-30", value: 100, available_date: "2024-03-30" }, { date: "2024-03-31", value: 110, available_date: "2024-03-31" }];
  input.inflation.data = [{ date: "2024-01-31", value: 100, available_date: "2024-03-20" }, { date: "2024-02-29", value: 110, available_date: "2024-03-03" }];
  const result = analyzeLocal(input);
  assert.equal(result.points[0].inflation_observation_date, "2024-02-29");
});

test("released mode rejects missing and duplicate asset availability", () => {
  const missing = request(); missing.alignment = "released";
  delete missing.asset.data[0].available_date;
  assert.throws(() => analyzeLocal(missing), /requires available_date/);
  const duplicate = request(); duplicate.alignment = "released";
  duplicate.asset.data[0].available_date = "2024-03-31";
  duplicate.asset.data[1].available_date = "2024-03-31";
  assert.throws(() => analyzeLocal(duplicate), /decision dates must be unique/);
});

test("missing CPI, stale CPI, currency mismatch and fabricated early coverage reject", () => {
  const missing = request(); missing.inflation.data.shift();
  assert.throws(() => analyzeLocal(missing), /at least two|No eligible CPI/);
  const stale = request(); stale.max_staleness_days = 5; stale.inflation.data.pop();
  assert.throws(() => analyzeLocal(stale), /days old/);
  const mismatch = request(); mismatch.asset.currency = "USD";
  assert.throws(() => analyzeLocal(mismatch), /Currency mismatch/);
  const early = request(); early.base_date = "1986-01-01";
  assert.throws(() => analyzeLocal(early), /coverage gap/);
});

test("an empty cropped range is an error", () => {
  const input = request(); input.base_date = "2024-01-31"; input.start_date = "2024-04-01";
  assert.throws(() => analyzeLocal(input), /No observations/);
});

test("undefined annualization returns null rather than an infinite metric", () => {
  const input = request();
  input.asset.data = [{ date: "2024-01-31", value: 1 }, { date: "2024-02-01", value: 1e100 }];
  const result = analyzeLocal(input);
  assert.equal(result.metrics.nominal_cagr_pct, null);
  assert.equal(result.metrics.real_cagr_pct, null);
});

test("CSV parser honors quoting and rejects invalid values and duplicate dates", () => {
  const rows = parseCsv('date,value,available_date\n"2024-01-31","100.5","2024-02-03"\n"2024-02-29","105.5","2024-03-03"\n');
  assert.equal(rows[0].value, 100.5);
  assert.equal(rows[1].available_date, "2024-03-03");
  assert.throws(() => parseCsv('date,value\n2024-01-31,"1,000"\n2024-02-29,100'), /decimal point/);
  assert.throws(() => parseCsv('date,value\n2024-01-31,100\n2024-01-31,101'), /Duplicate/);
  assert.throws(() => validateRows([{ date: "2024-02-30", value: 100 }, { date: "2024-03-31", value: 105 }]), /real YYYY-MM-DD/);
  const unknownRelease = validateRows([{ date: "2024-01-31", value: 100, available_date: null }, { date: "2024-02-29", value: 105 }]);
  assert.equal(unknownRelease[0].available_date, undefined);
});

test("browser calculator matches the actual Python API across five reference cases", () => {
  const fixtures = JSON.parse(readFileSync(new URL("./fixtures/engine-reference.json", import.meta.url), "utf8")) as Array<{ name: string; request: AnalysisRequest; result: ReturnType<typeof analyzeLocal> }>;
  function compare(actual: unknown, expected: unknown, path: string) {
    if (typeof expected === "number") {
      assert.equal(typeof actual, "number", path);
      assert.ok(Math.abs((actual as number) - expected) <= Math.max(1e-9, Math.abs(expected) * 1e-10), `${path}: ${String(actual)} != ${expected}`);
    } else if (Array.isArray(expected)) {
      assert.ok(Array.isArray(actual), path);
      assert.equal((actual as unknown[]).length, expected.length, path);
      expected.forEach((value, index) => compare((actual as unknown[])[index], value, `${path}[${index}]`));
    } else if (expected !== null && typeof expected === "object") {
      assert.ok(actual !== null && typeof actual === "object", path);
      for (const [key, value] of Object.entries(expected)) compare((actual as Record<string, unknown>)[key], value, `${path}.${key}`);
    } else assert.equal(actual, expected, path);
  }
  assert.equal(fixtures.length, 5);
  for (const fixture of fixtures) compare(analyzeLocal(fixture.request), fixture.result, fixture.name);
});
