// SPDX-License-Identifier: 0BSD
import Papa from "papaparse";
import { validateRows, validateSeries, type Observation, type Series } from "./model.ts";

export async function readSeriesFile(file: File, fallback: Omit<Series, "data">): Promise<Series> {
  if (file.size > 12 * 1024 * 1024) throw new Error("File exceeds the 12 MB dashboard import limit.");
  const text = await file.text();
  if (file.name.toLowerCase().endsWith(".json")) {
    const json: unknown = JSON.parse(text);
    return Array.isArray(json) ? validateSeries({ ...fallback, data: json }) : validateSeries(json);
  }
  if (!file.name.toLowerCase().endsWith(".csv")) throw new Error("Choose a .csv or .json file.");
  return validateSeries({ ...fallback, data: parseCsv(text) });
}

export function parseCsv(text: string): Observation[] {
  const parsed = Papa.parse<Record<string, string>>(text.replace(/^\uFEFF/, ""), {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (header) => header.trim(),
  });
  if (parsed.errors.length) throw new Error(`CSV parse error: ${parsed.errors[0].message}.`);
  const columns = parsed.meta.fields || [];
  if (!columns.includes("date") || !columns.includes("value")) throw new Error("CSV needs date,value headers; available_date is optional.");
  if (columns.some((column) => !["date", "value", "available_date"].includes(column))) throw new Error("CSV supports only date,value,available_date. Use JSON for metadata.");
  return validateRows(parsed.data.map((row, index) => {
    const number = row.value?.trim();
    if (!number || !/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(number)) throw new Error(`CSV row ${index + 2}: value must use a decimal point and no thousands separators.`);
    return { date: row.date.trim(), value: Number(number), ...(row.available_date?.trim() ? { available_date: row.available_date.trim() } : {}) };
  }));
}

export function downloadFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function resultsCsv(rows: unknown[]) { return Papa.unparse(rows, { escapeFormulae: true }); }
