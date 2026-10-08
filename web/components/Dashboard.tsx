"use client";
// SPDX-License-Identifier: 0BSD
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { analyze } from "@/lib/analyze";
import { demoAssets, demoInflation } from "@/lib/demo";
import { downloadFile, readSeriesFile, resultsCsv } from "@/lib/files";
import type { AnalysisRequest, AnalysisResult, Series } from "@/lib/model";
import { day } from "@/lib/model";

const ReturnChart = dynamic(() => import("./ReturnChart"), { ssr: false, loading: () => <div className="chart-loading">Preparing chart…</div> });
const percent = (value: number | null | undefined) => value == null ? "—" : `${value > 0 ? "+" : ""}${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
const number = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2 });
const friendly = (id: string) => id.replace(/^DEMO_/, "").replace(/_/g, " ");
const decisionDates = (asset: Series, alignment: AnalysisRequest["alignment"]) => asset.data.map((row) => alignment === "released" ? row.available_date || "" : row.date).filter(Boolean).sort();

function Icon({ name }: { name: "weave" | "chart" | "data" | "down" | "up" | "arrow" | "check" }) {
  const paths = { weave: "M4 5h7l9 14M4 12h16M4 19h7L20 5", chart: "M4 19h16M6 15l4-5 4 3 5-9", data: "M4 6c0-4 16-4 16 0s-16 4-16 0zm0 0v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0", down: "M12 4v12m-5-5 5 5 5-5M5 20h14", up: "M12 16V4m-5 5 5-5 5 5M5 20h14", arrow: "M5 12h14m-6-6 6 6-6 6", check: "m5 12 4 4L19 6" };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

export default function Dashboard() {
  const [assets, setAssets] = useState<Series[]>(demoAssets);
  const [inflations, setInflations] = useState<Series[]>([demoInflation]);
  const [assetId, setAssetId] = useState(demoAssets[0].series_id);
  const [inflationId, setInflationId] = useState(demoInflation.series_id);
  const [compareId, setCompareId] = useState("");
  const [baseDate, setBaseDate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [alignment, setAlignment] = useState<AnalysisRequest["alignment"]>("observation");
  const [maxAge, setMaxAge] = useState(62);
  const [mode, setMode] = useState<"index" | "drawdown">("index");
  const [result, setResult] = useState<AnalysisResult>();
  const [comparison, setComparison] = useState<AnalysisResult>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [importError, setImportError] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [target, setTarget] = useState<"asset" | "inflation">("asset");
  const [importId, setImportId] = useState("");
  const [importSource, setImportSource] = useState("");
  const [currency, setCurrency] = useState("TRY");
  const [importKind, setImportKind] = useState("price");
  const [synthetic, setSynthetic] = useState(false);
  const [tablePage, setTablePage] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const asset = assets.find((item) => item.series_id === assetId)!;
  const inflation = inflations.find((item) => item.series_id === inflationId)!;
  const compareAsset = assets.find((item) => item.series_id === compareId);
  const apiConfigured = !!process.env.NEXT_PUBLIC_API_URL;

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError("");
    setResult(undefined);
    setComparison(undefined);
    setTablePage(0);
    const run = async () => {
      try {
        let requestBase = baseDate || undefined;
        let requestEnd = endDate || undefined;
        if (compareAsset) {
          const primaryDates = decisionDates(asset, alignment);
          const otherDates = new Set(decisionDates(compareAsset, alignment));
          const eligible = primaryDates.filter((date) => otherDates.has(date) && date >= (baseDate || startDate || primaryDates[0]) && (!endDate || date <= endDate));
          if (eligible.length < 2) throw new Error("Comparison requires at least two shared observation dates in the selected range. Upload compatible histories or adjust dates.");
          const requestedAnchor = baseDate || startDate;
          if (requestedAnchor && (Date.parse(eligible[0]) - Date.parse(requestedAnchor)) / day > maxAge) throw new Error(`Comparison coverage gap: first shared date is more than ${maxAge} days after the requested base.`);
          requestBase = eligible[0];
          requestEnd = eligible.at(-1);
        }
        const request: AnalysisRequest = { asset, inflation, alignment, max_staleness_days: maxAge, ...(requestBase ? { base_date: requestBase } : {}), ...(startDate ? { start_date: startDate } : {}), ...(requestEnd ? { end_date: requestEnd } : {}) };
        const [primary, secondary] = await Promise.all([analyze(request), compareAsset ? analyze({ ...request, asset: compareAsset }) : Promise.resolve(undefined)]);
        if (cancelled) return;
        setResult(primary);
        setComparison(secondary);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Analysis failed.");
      } finally { if (!cancelled) setBusy(false); }
    };
    void run();
    return () => { cancelled = true; };
  }, [asset, inflation, compareAsset, baseDate, startDate, endDate, alignment, maxAge]);

  async function importFile(file: File) {
    setImportBusy(true);
    setImportError("");
    try {
      const parsed = await readSeriesFile(file, { series_id: importId.trim() || file.name.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_").toUpperCase(), kind: target === "inflation" ? "cpi" : importKind, currency, source: importSource.trim() || `User upload: ${file.name}`, synthetic });
      if (target === "inflation" && parsed.kind !== "cpi") throw new Error("Inflation imports must contain index levels with kind cpi. Convert monthly rates with the CLI before importing.");
      if (target === "asset" && !["price", "wealth"].includes(parsed.kind)) throw new Error("Asset imports need kind price or wealth. Use a value or total-return index, not individual return rates.");
      if ([...assets, ...inflations].some((item) => item.series_id === parsed.series_id)) throw new Error("That series ID already exists. Enter a distinct series ID before importing, or rename series_id in JSON.");
      if (target === "asset") { setAssets((old) => [...old, parsed]); setAssetId(parsed.series_id); setCompareId(""); }
      else { setInflations((old) => [...old, parsed]); setInflationId(parsed.series_id); }
      setBaseDate(""); setStartDate(""); setEndDate("");
      setImportId(""); setImportSource("");
    } catch (err) { setImportError(err instanceof Error ? err.message : "Could not import the file."); }
    finally { setImportBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  function exportResult(format: "json" | "csv") {
    if (!result) return;
    const title = asset.series_id.replace(/[^a-zA-Z0-9_-]/g, "_");
    if (format === "json") downloadFile(`${title}-real-return.json`, JSON.stringify({ analysis: result, comparison, provenance: { asset: { ...asset, data: undefined }, inflation: { ...inflation, data: undefined }, comparison: compareAsset ? { ...compareAsset, data: undefined } : undefined } }, null, 2), "application/json");
    else downloadFile(`${title}-real-return.csv`, resultsCsv(result.points.map((point) => ({ asset_id: asset.series_id, inflation_id: inflation.series_id, synthetic: asset.synthetic || inflation.synthetic, ...point }))), "text/csv;charset=utf-8");
  }

  function reset() {
    setAssets(demoAssets); setInflations([demoInflation]); setAssetId(demoAssets[0].series_id); setInflationId(demoInflation.series_id); setCompareId(""); setBaseDate(""); setStartDate(""); setEndDate(""); setAlignment("observation"); setMaxAge(62); setImportError("");
  }
  const isSynthetic = asset.synthetic || inflation.synthetic || !!compareAsset?.synthetic;
  const last = result?.points.at(-1);
  const actualBase = result?.metadata.actual_base_date;
  const actualEnd = result?.metadata.actual_end_date;
  const rows = result?.points.slice(tablePage * 12, (tablePage + 1) * 12) || [];

  return <>
    <a href="#workspace" className="skip-link">Skip to workspace</a>
    <header className="topbar"><div className="topbar-inner"><a className="brand" href="/" aria-label="InflationWeaver home"><span className="brand-mark"><Icon name="weave" /></span><span>Inflation<span className="brand-light">Weaver</span></span></a><nav aria-label="Workspace navigation"><a href="#workspace" className="active">Workspace</a><a href="#data">Data sources</a><a href="#methodology">Methodology</a></nav><span className="version">v0.1.0 <span>0BSD</span></span></div></header>
    <main>
      <div className="page-heading" id="workspace"><div><p className="eyebrow">THE REAL RETURN WORKSPACE</p><h1>See what your money <em>actually earned.</em></h1><p className="intro">Separate market growth from inflation. Measure performance in purchasing power.</p></div><button className="button ghost reset-button" onClick={reset}>Reset to demo</button></div>
      <div className={`status-strip ${isSynthetic ? "demo-strip" : "uploaded-strip"}`}><span className="status-dot" /><strong>{isSynthetic ? "Synthetic demonstration" : "Uploaded data"}</strong><span>{isSynthetic ? "Fictional prices and CPI. No values on this screen represent XU100, ENAG or real market history." : "Source descriptions are provided by the uploader. Verify histories and revisions before drawing conclusions."}</span></div>
      <section className="panel controls" aria-labelledby="analysis-title"><div className="panel-caption"><span className="small-icon"><Icon name="chart" /></span><h2 id="analysis-title">Analysis settings</h2><span className="auto-label">Updates automatically</span></div><div className="controls-grid">
        <label>Asset<select value={assetId} onChange={(event) => { setAssetId(event.target.value); if (event.target.value === compareId) setCompareId(""); }} >{assets.map((item) => <option key={item.series_id} value={item.series_id}>{friendly(item.series_id)}{item.synthetic ? " · demo" : ""}</option>)}</select></label>
        <label>Inflation benchmark<select value={inflationId} onChange={(event) => setInflationId(event.target.value)}>{inflations.map((item) => <option key={item.series_id} value={item.series_id}>{friendly(item.series_id)}{item.synthetic ? " · demo" : ""}</option>)}</select></label>
        <label>Compare another asset<select value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">No comparison</option>{assets.filter((item) => item.series_id !== assetId).map((item) => <option key={item.series_id} value={item.series_id}>{friendly(item.series_id)}{item.synthetic ? " · demo" : ""}</option>)}</select></label>
        <label>Inflation alignment<select value={alignment} onChange={(event) => setAlignment(event.target.value as AnalysisRequest["alignment"])}><option value="observation">Observation date · retrospective</option><option value="released">Release date · known information</option></select></label>
        <label>Base date<input type="date" value={baseDate} onChange={(event) => setBaseDate(event.target.value)} aria-describedby="date-help" /></label>
        <label>Display start<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} aria-describedby="date-help" /></label>
        <label>End date<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} aria-describedby="date-help" /></label>
        <label>Maximum CPI age · days<input type="number" min="0" max="3660" step="1" value={maxAge} onChange={(event) => setMaxAge(Number(event.target.value))} /></label>
      </div><div className="control-notes"><p id="date-help">Empty dates use available history. Indices, returns and drawdowns start at the effective base; display start only crops the chart. Comparison uses shared base and end dates.</p><p>{alignment === "released" ? "Released mode requires available_date for both series and rejects unavailable or stale observations." : "Observation mode can use CPI published later. Use released mode for information available at the time."}</p></div></section>
      {error && <div className="error-panel" role="alert"><strong>Analysis could not be completed</strong><p>{error}</p></div>}
      <section className="metric-grid" aria-label="Performance metrics" aria-busy={busy}>
        <Metric label="Real return" value={percent(result?.metrics.real_return_pct)} detail="Growth in purchasing power" featured positive={(result?.metrics.real_return_pct || 0) >= 0} />
        <Metric label="Nominal return" value={percent(result?.metrics.nominal_return_pct)} detail="Growth before inflation" />
        <Metric label="Cumulative inflation" value={percent(result?.metrics.inflation_return_pct)} detail="Change in the selected CPI" />
        <Metric label="Real CAGR" value={percent(result?.metrics.real_cagr_pct)} detail="Annualized purchasing power growth" />
      </section>
      <section className="panel chart-panel" aria-labelledby="chart-title" aria-busy={busy}><div className="chart-heading"><div><p className="eyebrow">PERFORMANCE OVER TIME</p><h2 id="chart-title">{friendly(asset.series_id)} <span>/ {asset.currency}</span></h2><p className="chart-subtitle">{result ? `${String(actualBase)} — ${String(actualEnd)} · ${result.metrics.observations} baseline-period observations` : "Choose valid asset and inflation histories to begin."}</p></div><div className="segmented" aria-label="Chart view"><button aria-pressed={mode === "index"} className={mode === "index" ? "selected" : ""} onClick={() => setMode("index")}>Indexed to 100</button><button aria-pressed={mode === "drawdown"} className={mode === "drawdown" ? "selected" : ""} onClick={() => setMode("drawdown")}>Drawdown</button></div></div>
        <div className="legend"><span><i className="nominal" />Nominal asset</span><span><i className="real" />Real asset</span>{mode === "index" && <span><i className="cpi" />Inflation index</span>}{compareAsset && <span><i className="compare" />{friendly(compareAsset.series_id)} · real</span>}</div>
        {busy ? <div className="chart-loading" role="status">Calculating aligned observations…</div> : result ? <ReturnChart result={result} comparison={comparison} mode={mode} /> : <div className="chart-loading">The chart will appear when the selected series pass validation.</div>}
        <div className="chart-footer"><span><Icon name="check" />Backward alignment · no interpolation</span><span>{last ? `Last real index ${number(last.real_index)}` : ""}</span><div className="export-actions"><button disabled={!result || busy} onClick={() => exportResult("csv")}><Icon name="down" />CSV</button><button disabled={!result || busy} onClick={() => exportResult("json")}><Icon name="down" />JSON report</button></div></div>
      </section>
      <div className="detail-grid"><section className="panel small-panel"><h2>Risk & annualized performance</h2><dl className="stat-list"><div><dt>Nominal CAGR</dt><dd>{percent(result?.metrics.nominal_cagr_pct)}</dd></div><div><dt>Nominal maximum drawdown</dt><dd>{percent(result?.metrics.nominal_max_drawdown_pct)}</dd></div><div><dt>Real maximum drawdown</dt><dd>{percent(result?.metrics.real_max_drawdown_pct)}</dd></div><div><dt>Purchasing power of 100 at base</dt><dd>{last ? number(100 * 100 / last.inflation_index) : "—"}</dd></div></dl><p className="muted small">Drawdowns include the full base-to-end history, including periods before the display start. CAGR uses elapsed calendar time.</p></section>
      <section className="panel small-panel"><h2>{comparison ? "Asset comparison" : "The return that matters"}</h2>{comparison && compareAsset ? <div className="comparison-summary"><span className="compare-text">{friendly(compareAsset.series_id)}</span><strong>{percent(comparison.metrics.real_return_pct)}</strong><p>Real return over the same base and end dates as the primary asset.</p></div> : <><div className="formula">Real growth = <span>Nominal growth ÷ CPI growth</span></div><p className="muted">A 100% price gain with 150% inflation is a 20% loss in purchasing power. Subtracting inflation percentages would give the wrong answer.</p></>}<p className="muted small">Returns reflect the input series. Include reinvested dividends, fees and cash flows in a wealth index when those matter to your analysis.</p></section></div>
      <section className="panel import-panel" id="data" aria-labelledby="data-title"><div className="panel-caption"><span className="small-icon"><Icon name="data" /></span><h2 id="data-title">Bring your own history</h2><span className="auto-label">CSV or JSON</span></div><p className="muted">Analyze BIST indices and shares, foreign markets, gold, crypto, funds, interest-bearing wealth or property indices. Supply positive price or wealth levels in the same currency as your CPI basket.</p><div className="import-grid"><label>Import as<select value={target} onChange={(event) => setTarget(event.target.value as "asset" | "inflation")}><option value="asset">Asset series</option><option value="inflation">CPI index series</option></select></label><label>Series ID<input value={importId} onChange={(event) => setImportId(event.target.value)} placeholder="e.g. XU100_TRY" /></label><label>Currency<select value={currency} onChange={(event) => setCurrency(event.target.value)}>{["TRY", "USD", "EUR", "GBP", "CHF", "JPY"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Value type<select value={target === "inflation" ? "cpi" : importKind} disabled={target === "inflation"} onChange={(event) => setImportKind(event.target.value)}>{target === "inflation" ? <option value="cpi">CPI index levels</option> : <><option value="price">Price or index level</option><option value="wealth">Wealth / total-return index</option></>}</select></label><label className="source-input">Source description<input value={importSource} onChange={(event) => setImportSource(event.target.value)} placeholder="Provider, series code, export date, adjustment policy" /></label><label className="checkbox-label"><input type="checkbox" checked={synthetic} onChange={(event) => setSynthetic(event.target.checked)} />This import contains synthetic values</label></div><div className="upload-actions"><input ref={fileRef} type="file" accept=".csv,.json,text/csv,application/json" id="series-upload" disabled={importBusy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); }} /><label htmlFor="series-upload" className={`button primary ${importBusy ? "disabled" : ""}`}><Icon name="up" />{importBusy ? "Validating file…" : "Choose data file"}</label><button className="button ghost" onClick={() => downloadFile("inflationweaver-example-asset.json", JSON.stringify(demoAssets[0], null, 2), "application/json")}>Download example JSON</button><button className="button ghost" onClick={() => downloadFile("inflationweaver-example-cpi.csv", resultsCsv(demoInflation.data), "text/csv;charset=utf-8")}>Download example CPI CSV</button></div>{importError && <p className="import-error" role="alert">{importError}</p>}<details className="import-help"><summary>File format & import rules</summary><p>CSV requires <code>date,value</code>; optional <code>available_date</code>. Dates must be YYYY-MM-DD, values positive decimal numbers without thousands separators, and dates unique. Quoted CSV fields are parsed correctly. JSON accepts a full series object or an observation array. Full JSON metadata overrides the form.</p><pre>{`date,value,available_date\n2024-01-31,100.0,2024-02-03\n2024-02-29,105.5,2024-03-03`}</pre><p>CPI means an index level, not a YoY or monthly percentage. Convert monthly inflation rates with the Python CLI. For released mode, every observation in both series needs an availability date. Imports are limited to 12 MB and 50,000 rows per series.</p></details><div className="privacy-note"><span className="status-dot" />{apiConfigured ? `Uploads are sent to the configured analysis API: ${process.env.NEXT_PUBLIC_API_URL}. Only use a server you trust.` : "Your uploaded data stays in this browser. Reloading clears uploads; export your report before leaving."}</div></section>
      <section className="panel provenance-panel" aria-labelledby="provenance-title"><h2 id="provenance-title">Source provenance</h2><div className="source-list">{[asset, inflation, ...(compareAsset ? [compareAsset] : [])].map((item) => <div key={item.series_id}><div><strong>{item.series_id}</strong><span className={`badge ${item.synthetic ? "synthetic" : ""}`}>{item.synthetic ? "SYNTHETIC" : "UPLOADED"}</span></div><p>{item.source}</p><span className="muted small">{item.currency} · {item.kind} · {item.data.length} observations · {item.data[0].date} — {item.data.at(-1)!.date}</span></div>)}</div></section>
      <section className="panel observations-panel" aria-labelledby="observations-title"><div className="panel-caption"><h2 id="observations-title">Aligned observations</h2><span className="auto-label">Exact values behind the chart</span></div><div className="table-scroll"><table><thead><tr><th scope="col">Date</th><th scope="col">Nominal index</th><th scope="col">CPI index</th><th scope="col">Real index</th><th scope="col">Real value · {asset.currency}</th><th scope="col">Real drawdown</th></tr></thead><tbody>{rows.length ? rows.map((point) => <tr key={point.date}><td>{point.date}</td><td>{number(point.nominal_index)}</td><td>{number(point.inflation_index)}</td><td className="positive">{number(point.real_index)}</td><td>{number(point.real_value)}</td><td>{percent(point.real_drawdown)}</td></tr>) : <tr><td colSpan={6}>No validated observations to display.</td></tr>}</tbody></table></div><div className="pagination"><span>{result ? `${tablePage * 12 + 1}–${Math.min((tablePage + 1) * 12, result.points.length)} of ${result.points.length} displayed observations` : ""}</span><div><button disabled={tablePage === 0} onClick={() => setTablePage((page) => page - 1)}>Previous</button><button disabled={!result || (tablePage + 1) * 12 >= result.points.length} onClick={() => setTablePage((page) => page + 1)}>Next</button></div></div></section>
      <section className="methodology" id="methodology"><p className="eyebrow">A TRANSPARENT CALCULATION</p><h2>Purchasing power, with the assumptions visible.</h2><div className="method-grid"><div><span className="step">01</span><h3>Align observations</h3><p>Each asset date uses the latest eligible CPI period at or before it. Released mode also checks publication dates. Missing or stale CPI causes an explicit error.</p></div><div><span className="step">02</span><h3>Normalize the baseline</h3><p>Nominal and CPI indices start at 100 on the effective base date. Real index = 100 × nominal index ÷ CPI index. Real value is expressed in base-date currency.</p></div><div><span className="step">03</span><h3>Respect historical coverage</h3><p>Upload verified history from 1986 or any supported date. The dashboard never fabricates missing ENAG history or silently joins series with different bases.</p></div></div></section>
    </main><footer className="site-footer"><a className="brand" href="/"><span className="brand-mark"><Icon name="weave" /></span><span>InflationWeaver</span></a><span>Open source · 0BSD · First-party code</span><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">Charts by TradingView</a></footer>
  </>;
}

function Metric({ label, value, detail, featured, positive }: { label: string; value: string; detail: string; featured?: boolean; positive?: boolean }) {
  return <div className={`metric-card ${featured ? "featured" : ""}`}><p>{label}{featured && <span>INFLATION ADJUSTED</span>}</p><strong className={featured ? positive ? "positive" : "negative" : ""}>{value}</strong><small>{detail}</small></div>;
}
