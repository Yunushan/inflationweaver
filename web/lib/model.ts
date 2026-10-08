// SPDX-License-Identifier: 0BSD
export interface Observation {
  date: string;
  value: number;
  available_date?: string;
}

export interface Series {
  series_id: string;
  kind: string;
  currency: string;
  source: string;
  synthetic: boolean;
  data: Observation[];
}

export interface AnalysisRequest {
  asset: Series;
  inflation: Series;
  base_date?: string;
  start_date?: string;
  end_date?: string;
  alignment: "observation" | "released";
  max_staleness_days: number;
}

export interface AnalysisPoint {
  date: string;
  asset_observation_date?: string;
  asset_value?: number;
  inflation_observation_date?: string;
  inflation_available_date?: string | null;
  inflation_value?: number;
  nominal_index: number;
  inflation_index: number;
  real_index: number;
  real_value: number;
  nominal_drawdown: number;
  real_drawdown: number;
}

export interface AnalysisMetrics {
  nominal_return_pct: number;
  real_return_pct: number;
  inflation_return_pct: number;
  nominal_cagr_pct: number | null;
  real_cagr_pct: number | null;
  inflation_cagr_pct: number | null;
  nominal_max_drawdown_pct: number;
  real_max_drawdown_pct: number;
  elapsed_days: number;
  observations: number;
}

export interface AnalysisResult {
  points: AnalysisPoint[];
  metrics: AnalysisMetrics;
  metadata: Record<string, unknown>;
}

export const day = 86_400_000;
export function validDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}

export function validateRows(rows: unknown): Observation[] {
  if (!Array.isArray(rows) || rows.length < 2) throw new Error("A series needs at least two observations.");
  if (rows.length > 50_000) throw new Error("A series may contain at most 50,000 observations in this dashboard.");
  const seen = new Set<string>();
  const result = rows.map((row, index) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) throw new Error(`Row ${index + 1}: expected an observation object.`);
    const item = row as Record<string, unknown>;
    if (!validDate(item.date)) throw new Error(`Row ${index + 1}: date must be a real YYYY-MM-DD date.`);
    if (typeof item.value !== "number" || !Number.isFinite(item.value) || item.value <= 0) throw new Error(`Row ${index + 1}: value must be a finite positive number. Upload an index level, not an inflation rate.`);
    if (seen.has(item.date)) throw new Error(`Duplicate observation date: ${item.date}.`);
    seen.add(item.date);
    if (item.available_date !== undefined && item.available_date !== null && (!validDate(item.available_date) || item.available_date < item.date)) throw new Error(`Row ${index + 1}: available_date must be a date on or after the observation date.`);
    return { date: item.date, value: item.value, ...(item.available_date ? { available_date: item.available_date as string } : {}) };
  });
  return result.sort((a, b) => a.date.localeCompare(b.date));
}

export function validateSeries(input: unknown): Series {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Expected a JSON series object with metadata and data.");
  const row = input as Record<string, unknown>;
  for (const field of ["series_id", "kind", "currency", "source"]) {
    if (typeof row[field] !== "string" || !(row[field] as string).trim()) throw new Error(`Series metadata requires a non-empty ${field}.`);
  }
  if (typeof row.synthetic !== "boolean") throw new Error("Series metadata requires synthetic: true or false.");
  if ((row.series_id as string).length > 120) throw new Error("Series ID must contain at most 120 characters.");
  if ((row.currency as string).length < 3 || (row.currency as string).length > 8) throw new Error("Currency must contain 3–8 characters.");
  if ((row.source as string).length > 1000) throw new Error("Source description must contain at most 1,000 characters.");
  if (!["price", "cpi", "monthly_rate", "wealth", "fx"].includes(row.kind as string)) throw new Error("Unknown series kind. Use price, wealth, cpi, monthly_rate or fx.");
  return { series_id: row.series_id as string, kind: row.kind as string, currency: row.currency as string, source: row.source as string, synthetic: row.synthetic, data: validateRows(row.data) };
}
