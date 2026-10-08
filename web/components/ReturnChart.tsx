"use client";
// SPDX-License-Identifier: 0BSD
import { useEffect, useRef, useState } from "react";
import { ColorType, createChart, LineSeries, type Time } from "lightweight-charts";
import type { AnalysisResult } from "@/lib/model";

const format = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2 });

export default function ReturnChart({ result, comparison, mode }: { result: AnalysisResult; comparison?: AnalysisResult; mode: "index" | "drawdown" }) {
  const container = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ date: string; nominal: number; real: number; cpi: number }>();
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      height: 390,
      layout: { background: { type: ColorType.Solid, color: "#0b1018" }, textColor: "#8b99ad", fontFamily: "Arial, sans-serif", attributionLogo: true },
      grid: { vertLines: { color: "#151e2b" }, horzLines: { color: "#151e2b" } },
      rightPriceScale: { borderColor: "#243043" },
      timeScale: { borderColor: "#243043", timeVisible: false },
      crosshair: { vertLine: { color: "#64748b" }, horzLine: { color: "#64748b" } },
      localization: { priceFormatter: (price: number) => mode === "drawdown" ? `${price.toFixed(1)}%` : format(price) },
    });
    const nominal = chart.addSeries(LineSeries, { color: "#6e8ee9", lineWidth: 2, title: "Nominal", priceLineVisible: false, lastValueVisible: false });
    const real = chart.addSeries(LineSeries, { color: "#48d7aa", lineWidth: 3, title: "Real", priceLineVisible: false, lastValueVisible: false });
    const cpi = mode === "index" ? chart.addSeries(LineSeries, { color: "#d5a76c", lineWidth: 1, lineStyle: 2, title: "CPI", priceLineVisible: false, lastValueVisible: false }) : undefined;
    nominal.setData(result.points.map((p) => ({ time: p.date as Time, value: mode === "index" ? p.nominal_index : p.nominal_drawdown })));
    real.setData(result.points.map((p) => ({ time: p.date as Time, value: mode === "index" ? p.real_index : p.real_drawdown })));
    cpi?.setData(result.points.map((p) => ({ time: p.date as Time, value: p.inflation_index })));
    if (comparison) {
      const compare = chart.addSeries(LineSeries, { color: "#cc91e3", lineWidth: 2, lineStyle: 1, title: "Comparison real", priceLineVisible: false, lastValueVisible: false });
      compare.setData(comparison.points.map((p) => ({ time: p.date as Time, value: mode === "index" ? p.real_index : p.real_drawdown })));
    }
    const byDate = new Map(result.points.map((point) => [point.date, point]));
    chart.subscribeCrosshairMove((event) => {
      if (!event.time) { setHover(undefined); return; }
      const date = typeof event.time === "string" ? event.time : typeof event.time === "object" ? `${event.time.year}-${String(event.time.month).padStart(2, "0")}-${String(event.time.day).padStart(2, "0")}` : "";
      const point = byDate.get(date);
      setHover(point ? { date, nominal: mode === "index" ? point.nominal_index : point.nominal_drawdown, real: mode === "index" ? point.real_index : point.real_drawdown, cpi: point.inflation_index } : undefined);
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [result, comparison, mode]);

  return <>
    <div className="chart-readout" aria-live="off">
      <span>{hover?.date || "Move over the chart to inspect values"}</span>
      {hover && <><span className="nominal-text">Nominal {format(hover.nominal)}{mode === "drawdown" ? "%" : ""}</span><span className="positive">Real {format(hover.real)}{mode === "drawdown" ? "%" : ""}</span>{mode === "index" && <span className="cpi-text">CPI {format(hover.cpi)}</span>}</>}
    </div>
    <div ref={container} className="chart-canvas" role="img" aria-label={mode === "index" ? "Nominal asset, inflation adjusted asset and CPI indices. Exact observations are available in the table below." : "Nominal and inflation adjusted drawdowns from their respective running peaks. Exact observations are available in the table below."} />
    <p className="chart-attribution"><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a> · Copyright (с) 2025 TradingView, Inc.</p>
  </>;
}
