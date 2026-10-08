// SPDX-License-Identifier: 0BSD
import type { Series } from "./model";

// Deterministic fictional values. These are not XU100, ENAG or any historical market data.
const months = Array.from({ length: 120 }, (_, i) => new Date(Date.UTC(2016, i + 1, 0)).toISOString().slice(0, 10));

export const demoAssets: Series[] = [
  {
    series_id: "DEMO_EQUITY_TRY", kind: "price", currency: "TRY", source: "InflationWeaver synthetic demonstration", synthetic: true,
    data: months.map((date, i) => ({ date, available_date: date, value: Number((100 * Math.exp(i * 0.028) * (1 + Math.sin(i / 5) * 0.16) * (i > 45 && i < 60 ? 0.7 : 1)).toFixed(6)) })),
  },
  {
    series_id: "DEMO_GOLD_TRY", kind: "price", currency: "TRY", source: "InflationWeaver synthetic demonstration", synthetic: true,
    data: months.map((date, i) => ({ date, available_date: date, value: Number((100 * Math.exp(i * 0.025) * (1 + Math.sin(i / 9) * 0.08)).toFixed(6)) })),
  },
];

export const demoInflation: Series = {
  series_id: "DEMO_CPI_TRY", kind: "cpi", currency: "TRY", source: "InflationWeaver synthetic demonstration", synthetic: true,
  data: [
    { date: "2015-12-31", value: 98.11804, available_date: "2016-01-03" },
    ...months.map((date, i) => ({ date, value: Number((100 * Math.exp(i * 0.019)).toFixed(6)), available_date: new Date(Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)), 3)).toISOString().slice(0, 10) })),
  ],
};
