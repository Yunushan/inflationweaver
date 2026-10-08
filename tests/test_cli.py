# SPDX-License-Identifier: 0BSD
import json

from inflationweaver.cli import main


def test_demo_generates_portable_report(tmp_path):
    assert main(["demo", "--out", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / "analysis.json").read_text())
    assert payload["metadata"]["synthetic"] is True
    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / "analysis.csv").is_file()


def test_analyze_does_not_fabricate_1986_base(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path / "demo")]) == 0
    assert main(["analyze", "--asset", str(tmp_path / "demo/demo_asset.csv"),
                 "--inflation", str(tmp_path / "demo/demo_cpi.csv"), "--base-date", "1986-01-01",
                 "--synthetic", "--out", str(tmp_path / "report")]) == 2
    assert "1986" in capsys.readouterr().err or not (tmp_path / "report").exists()


def test_import_no_silent_overwrite(tmp_path):
    main(["demo", "--out", str(tmp_path / "demo")])
    args = ["import", "--file", str(tmp_path / "demo/demo_asset.csv"), "--id", "DEMO_ASSET",
            "--synthetic", "--store", str(tmp_path / "store")]
    assert main(args) == 0
    assert main(args) == 2
    assert main([*args, "--mode", "replace"]) == 0


def test_pine_export_released(tmp_path):
    main(["demo", "--out", str(tmp_path / "demo")])
    path = tmp_path / "demo.pine"
    assert main(["pine", "--inflation", str(tmp_path / "demo/demo_cpi.csv"), "--synthetic",
                 "--alignment", "released", "--out", str(path)]) == 0
    assert "//@version=6" in path.read_text()


def test_fx_cli_records_explicit_quote_direction(tmp_path):
    asset = tmp_path / "asset.csv"
    fx = tmp_path / "fx.csv"
    asset.write_text("date,value\n2023-01-01,100\n2023-01-02,120\n")
    fx.write_text("date,value\n2023-01-01,20\n2023-01-02,24\n")
    path = tmp_path / "usd.csv"
    assert main(["fx", "--asset", str(asset), "--fx", str(fx), "--currency", "TRY",
                 "--target-currency", "USD", "--operation", "divide", "--out", str(path)]) == 0
    from inflationweaver.providers import read_csv
    metadata = json.loads(path.with_suffix(".csv.metadata.json").read_text())
    result = read_csv(path, metadata["series_id"], metadata["kind"], metadata["currency"],
                      metadata["source"], metadata["synthetic"])
    assert result.data["value"].to_list() == [5, 5]
