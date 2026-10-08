// SPDX-License-Identifier: 0BSD
import { day, validateSeries, validDate, type AnalysisRequest, type AnalysisResult, type Observation } from "./model.ts";

const timestamp = (date: string) => Date.parse(`${date}T00:00:00Z`);

/** Local reference calculator. A configured API origin uses the Python engine instead. */
export function analyzeLocal(request: AnalysisRequest): AnalysisResult {
  const asset = validateSeries(request.asset);
  const inflation = validateSeries(request.inflation);
  if (!["price", "wealth"].includes(asset.kind)) throw new Error("Asset series kind must be price or wealth. Convert FX quotes, return rates or portfolio contributions into a positive value series first.");
  if (asset.currency !== inflation.currency) throw new Error(`Currency mismatch: ${asset.currency} asset and ${inflation.currency} inflation. Convert prices into the inflation basket's currency first.`);
  if (inflation.kind !== "cpi") throw new Error("The inflation series must contain CPI index levels with kind cpi. Monthly or annual rates need conversion first.");
  if (request.alignment === "released" && [...inflation.data, ...asset.data].some((row) => !row.available_date)) throw new Error("Released alignment requires available_date for every asset and CPI observation.");
  for (const field of ["base_date", "start_date", "end_date"] as const) {
    if (request[field] && !validDate(request[field])) throw new Error(`${field} must be YYYY-MM-DD.`);
  }
  if (request.start_date && request.end_date && request.start_date > request.end_date) throw new Error("Start date must be on or before end date.");
  if (!Number.isInteger(request.max_staleness_days) || request.max_staleness_days < 0 || request.max_staleness_days > 3660) throw new Error("Maximum CPI age must be a whole number between 0 and 3660 days.");
  const lookup = inflation.data.map((row) => ({ key: request.alignment === "released" ? row.available_date! : row.date, row })).sort((a, b) => a.key.localeCompare(b.key) || a.row.date.localeCompare(b.row.date));
  let known: Observation | undefined;
  const eligible = lookup.map((entry) => {
    if (!known || entry.row.date > known.date) known = entry.row;
    return { key: entry.key, row: known };
  });
  const inflationAt = (date: string): Observation => {
    let low = 0;
    let high = eligible.length;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (eligible[mid].key <= date) low = mid + 1;
      else high = mid;
    }
    const latest = low ? eligible[low - 1].row : undefined;
    if (!latest) throw new Error(`No eligible CPI observation at ${date}. Restrict the range or upload earlier CPI history.`);
    const age = (timestamp(date) - timestamp(latest.date)) / day;
    if (age > request.max_staleness_days) throw new Error(`CPI observation is ${age} days old at ${date}; the limit is ${request.max_staleness_days}. Upload missing observations or change the explicit limit.`);
    return latest;
  };
  const timeline = asset.data.map((row) => ({ ...row, observed_date: row.date, date: request.alignment === "released" ? row.available_date! : row.date })).sort((a, b) => a.date.localeCompare(b.date));
  if (new Set(timeline.map((row) => row.date)).size !== timeline.length) throw new Error("Asset decision dates must be unique. Multiple observations share the same available_date.");
  const start = request.start_date || timeline[0].date;
  const end = request.end_date || timeline.at(-1)!.date;
  const baseRequested = request.base_date || start;
  const base = timeline.find((row) => row.date >= baseRequested);
  if (!base) throw new Error("No asset observation exists on or after the requested base date.");
  if ((timestamp(base.date) - timestamp(baseRequested)) / day > request.max_staleness_days) throw new Error(`Asset coverage gap: first eligible observation ${base.date} is more than ${request.max_staleness_days} days after the requested base ${baseRequested}.`);
  if (base.date > end) throw new Error("The base date falls after the end of the analysis range.");
  const baseInflation = inflationAt(base.date);
  const selected = timeline.filter((row) => row.date <= end && row.date >= base.date);
  if (!selected.length) throw new Error("The range contains no asset observations on or after the effective base date.");
  let nominalPeak = 100;
  let realPeak = 100;
  const points = selected.map((row) => {
    const cpi = inflationAt(row.date);
    const nominal_index = 100 * row.value / base.value;
    const inflation_index = 100 * cpi.value / baseInflation.value;
    const real_index = 100 * nominal_index / inflation_index;
    const real_value = row.value * baseInflation.value / cpi.value;
    if (![nominal_index, inflation_index, real_index, real_value].every((value) => Number.isFinite(value) && value > 0)) throw new Error("Index arithmetic overflowed or underflowed.");
    nominalPeak = Math.max(nominalPeak, nominal_index);
    realPeak = Math.max(realPeak, real_index);
    return { date: row.date, asset_observation_date: row.observed_date, asset_value: row.value, inflation_observation_date: cpi.date, inflation_available_date: cpi.available_date || null, inflation_value: cpi.value, nominal_index, inflation_index, real_index, real_value, nominal_drawdown: (nominal_index / nominalPeak - 1) * 100, real_drawdown: (real_index / realPeak - 1) * 100 };
  });
  const first = points[0];
  const last = points.at(-1)!;
  const years = (timestamp(last.date) - timestamp(first.date)) / (day * 365.2425);
  const nominalRatio = last.nominal_index / 100;
  const realRatio = last.real_index / 100;
  const cagr = (ratio: number) => { const value = years > 0 ? Math.expm1(Math.log(ratio) / years) * 100 : NaN; return Number.isFinite(value) ? value : null; };
  const displayed = points.filter((point) => point.date >= start);
  if (!displayed.length) throw new Error("No observations fall in the display range.");
  return {
    points: displayed,
    metrics: {
      nominal_return_pct: last.nominal_index - 100,
      real_return_pct: last.real_index - 100,
      inflation_return_pct: last.inflation_index - 100,
      nominal_cagr_pct: cagr(nominalRatio),
      real_cagr_pct: cagr(realRatio),
      inflation_cagr_pct: cagr(last.inflation_index / 100),
      nominal_max_drawdown_pct: points.reduce((min, row) => Math.min(min, row.nominal_drawdown), 0),
      real_max_drawdown_pct: points.reduce((min, row) => Math.min(min, row.real_drawdown), 0),
      elapsed_days: (timestamp(last.date) - timestamp(first.date)) / day,
      observations: points.length,
    },
    metadata: { requested_base_date: request.base_date || request.start_date || null, actual_base_date: base.date, actual_end_date: last.date, actual_display_start_date: displayed[0].date, display_observations: displayed.length, base_inflation_observation_date: baseInflation.date, asset_id: asset.series_id, inflation_id: inflation.series_id, asset_source: asset.source, inflation_source: inflation.source, asset_kind: asset.kind, alignment: request.alignment, retrospective: request.alignment === "observation", synthetic: asset.synthetic || inflation.synthetic, engine: "browser-reference", currency: asset.currency, max_staleness_days: request.max_staleness_days, staleness_basis: "observation_date", cagr_year_days: 365.2425, real_value_units: `${asset.currency} at base-date purchasing power` },
  };
}

export async function analyze(request: AnalysisRequest): Promise<AnalysisResult> {
  const origin = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (!origin) return analyzeLocal(request);
  const url = new URL(origin);
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("NEXT_PUBLIC_API_URL must be an HTTP or HTTPS origin.");
  const response = await fetch(`${origin}/v1/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: AbortSignal.timeout(30_000) });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Analysis API returned ${response.status}: ${detail.slice(0, 450)}`);
  }
  const result = await response.json() as AnalysisResult;
  if (!Array.isArray(result.points) || !result.metrics || !result.metadata) throw new Error("Analysis API returned an unexpected response.");
  return result;
}
