"""Command line workflows. SPDX-License-Identifier: 0BSD."""

import argparse
import json
import os
import sys
from pathlib import Path

import polars as pl

from . import __version__
from .engine import analyze, chain_monthly_rates, convert_currency, deposit_curve, splice_cpi
from .providers import fetch_evds, fetch_fred, fetch_oecd, read_csv, write_csv
from .report import write_report
from .store import SeriesStore


def _series(path, args, kind=None, identifier=None, currency=None):
    sidecar = Path(path).with_suffix(Path(path).suffix + ".metadata.json")
    metadata = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    return read_csv(path, series_id=identifier or metadata.get("series_id", Path(path).stem),
                    kind=kind or metadata.get("kind", "price"),
                    currency=currency or args.currency or metadata.get("currency", "TRY"),
                    source=args.source or metadata.get("source", "user"),
                    synthetic=args.synthetic if args.synthetic is not None else metadata.get("synthetic", False))


def _options(args):
    return {key: getattr(args, key) for key in
            ("base_date", "start_date", "end_date", "alignment", "max_staleness_days")}


def _metadata(parser):
    parser.add_argument("--currency", help="Currency; default TRY or verified CSV sidecar metadata")
    parser.add_argument("--source", help="Source; default user or verified CSV sidecar metadata")
    parser.add_argument("--synthetic", action="store_true", default=None,
                        help="Mark supplied inputs as synthetic")


def _analysis_options(parser):
    parser.add_argument("--base-date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--alignment", choices=["observation", "released"], default="observation")
    parser.add_argument("--max-staleness-days", type=int, default=62)


def run_update(manifest_path, store_path):
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("series"), list):
        raise ValueError("Manifest needs schema_version=1 and a series array")
    store = SeriesStore(store_path)
    results = []
    for entry in manifest["series"]:
        provider = entry.get("provider", "csv")
        common = {"kind": entry.get("kind", "price"), "currency": entry.get("currency", "TRY")}
        if provider == "csv":
            series = read_csv(path.parent / entry["path"], entry["series_id"],
                              source=entry.get("source", "user"), synthetic=entry.get("synthetic", False),
                              **common)
        elif provider == "fred":
            series = fetch_fred(entry["series_id"], entry["start"], entry["end"], **common)
        elif provider == "evds":
            series = fetch_evds(entry["series_id"], entry["start"], entry["end"], **common)
        elif provider == "oecd":
            series = fetch_oecd(entry["url"], entry["series_id"], entry.get("filters", {}), **common)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        results.append(store.write(series, mode=entry.get("mode", "error")))
    return results


def build_parser():
    parser = argparse.ArgumentParser(prog="inflationweaver", description="Inflation and real-return analytics")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="Generate a clearly synthetic working example")
    demo.add_argument("--out", default="reports/demo")

    calc = commands.add_parser("analyze", help="Analyze asset levels against CPI index levels")
    calc.add_argument("--asset", required=True)
    calc.add_argument("--inflation", required=True)
    calc.add_argument("--out", default="reports/analysis")
    _metadata(calc)
    _analysis_options(calc)

    ingest = commands.add_parser("import", help="Validate CSV and persist Parquet with provenance")
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--id", required=True)
    ingest.add_argument("--kind", choices=["price", "cpi", "monthly_rate", "wealth", "fx"], default="price")
    ingest.add_argument("--store", default=os.getenv("INFLATIONWEAVER_STORE", "data/local"))
    ingest.add_argument("--mode", choices=["error", "replace", "append", "update"], default="error")
    _metadata(ingest)

    update = commands.add_parser("update", help="Fetch/import an explicit, versioned update manifest")
    update.add_argument("--manifest", required=True)
    update.add_argument("--store", default=os.getenv("INFLATIONWEAVER_STORE", "data/local"))

    pine = commands.add_parser("pine", help="Embed verified CPI data into Pine Script v6")
    pine.add_argument("--inflation", required=True)
    pine.add_argument("--symbol", default="BIST:XU100")
    pine.add_argument("--out", default="reports/inflationweaver.pine")
    _metadata(pine)
    _analysis_options(pine)

    chain = commands.add_parser("chain", help="Compound contiguous monthly inflation percentages")
    chain.add_argument("--rates", required=True)
    chain.add_argument("--anchor-date", required=True)
    chain.add_argument("--anchor-value", type=float, default=100)
    chain.add_argument("--out", required=True)
    _metadata(chain)

    splice = commands.add_parser("splice", help="Link two CPI levels at an explicit common observation")
    splice.add_argument("--left", required=True)
    splice.add_argument("--right", required=True)
    splice.add_argument("--splice-date", required=True)
    splice.add_argument("--out", required=True)
    _metadata(splice)

    fx = commands.add_parser("fx", help="Convert a price/wealth series using an explicit FX quote")
    fx.add_argument("--asset", required=True)
    fx.add_argument("--fx", required=True)
    fx.add_argument("--target-currency", required=True)
    fx.add_argument("--fx-currency", help="Quote units TARGET/SOURCE for multiply; SOURCE/TARGET for divide")
    fx.add_argument("--operation", choices=["multiply", "divide"], default="multiply")
    fx.add_argument("--max-staleness-days", type=int, default=7)
    fx.add_argument("--out", required=True)
    _metadata(fx)

    deposit = commands.add_parser("deposit", help="Model a constant contractual nominal annual interest rate")
    deposit.add_argument("--principal", type=float, required=True)
    deposit.add_argument("--annual-rate", type=float, required=True, help="Percentage, e.g. 40 for 40%%")
    deposit.add_argument("--start-date", required=True)
    deposit.add_argument("--end-date", required=True)
    deposit.add_argument("--compounding", choices=["daily", "monthly", "annual"], default="daily")
    deposit.add_argument("--currency", default="TRY")
    deposit.add_argument("--out", required=True)

    backtest = commands.add_parser("backtest", help="Deflate strategy equity; optional beginning-of-period cashflows")
    backtest.add_argument("--equity", required=True, help="CSV date,value,optional cashflow/available_date")
    backtest.add_argument("--inflation", required=True)
    backtest.add_argument("--cashflow-column")
    backtest.add_argument("--out", default="reports/backtest")
    _metadata(backtest)
    _analysis_options(backtest)

    catalog = commands.add_parser("catalog", help="List supported import categories and illustrative instruments")
    catalog.add_argument("--json", action="store_true")

    serve = commands.add_parser("serve", help="Start the local API (OpenAPI docs at /docs)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import demo_series
            asset, inflation = demo_series()
            result = analyze(asset, inflation)
            path = write_report(result, args.out)
            write_csv(asset, path / "demo_asset.csv")
            write_csv(inflation, path / "demo_cpi.csv")
            print(f"SYNTHETIC demo saved to {path}")
        elif args.command == "analyze":
            result = analyze(_series(args.asset, args), _series(args.inflation, args, "cpi"), **_options(args))
            print(f"Analysis saved to {write_report(result, args.out)}")
        elif args.command == "import":
            series = _series(args.file, args, args.kind, args.id)
            print(json.dumps(SeriesStore(args.store).write(series, mode=args.mode), indent=2, default=str))
        elif args.command == "update":
            print(json.dumps(run_update(args.manifest, args.store), indent=2, default=str))
        elif args.command == "pine":
            from .pine import generate_pine
            if args.start_date or args.end_date:
                raise ValueError("Pine uses all supplied CPI rows; filter your input explicitly before generation")
            script = generate_pine(_series(args.inflation, args, "cpi"), args.symbol, args.base_date,
                                   args.alignment, args.max_staleness_days)
            destination = Path(args.out)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(script, encoding="utf-8")
            print(f"Pine v6 saved to {destination}; verify compilation in TradingView")
        elif args.command == "chain":
            result = chain_monthly_rates(_series(args.rates, args, "monthly_rate"),
                                         args.anchor_date, args.anchor_value)
            print(write_csv(result, args.out))
        elif args.command == "splice":
            result = splice_cpi(_series(args.left, args, "cpi"), _series(args.right, args, "cpi"),
                               args.splice_date)
            print(write_csv(result, args.out))
        elif args.command == "fx":
            asset = _series(args.asset, args)
            pair = args.fx_currency or (f"{args.target_currency}/{asset.currency}" if args.operation == "multiply"
                                       else f"{asset.currency}/{args.target_currency}")
            result = convert_currency(asset, _series(args.fx, args, "fx", currency=pair),
                                      args.target_currency, args.operation, args.max_staleness_days)
            print(write_csv(result, args.out))
        elif args.command == "deposit":
            print(write_csv(deposit_curve(args.principal, args.annual_rate, args.start_date,
                                          args.end_date, args.compounding, args.currency), args.out))
        elif args.command == "backtest":
            from .backtest import analyze_backtest
            result = analyze_backtest(pl.read_csv(args.equity, try_parse_dates=True),
                                      _series(args.inflation, args, "cpi"), currency=args.currency or "TRY",
                                      cashflow_column=args.cashflow_column, **_options(args))
            print(f"Backtest saved to {write_report(result, args.out)}")
        elif args.command == "catalog":
            from .catalog import get_catalog
            print(json.dumps(get_catalog(), indent=2, ensure_ascii=False))
        elif args.command == "serve":
            import uvicorn
            uvicorn.run("inflationweaver.api:app", host=args.host, port=args.port)
        return 0
    except (ValueError, TypeError, KeyError, OSError, pl.exceptions.PolarsError) as exc:
        print(f"inflationweaver: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
