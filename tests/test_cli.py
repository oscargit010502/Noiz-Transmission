"""Exercise the shipped example and actual exports through the public command line."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_example_exports_reproducible_curve(tmp_path):
    command = [
        sys.executable,
        "-m",
        "noiz_transmission.cli",
        "predict",
        str(ROOT / "examples" / "single_panel.noiz.json"),
        "--output-dir",
        str(tmp_path),
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stderr
    first = (tmp_path / "result.json").read_bytes()
    payload = json.loads(first)
    curve = payload["predictions"][0]
    assert curve["surface_density_kg_m2"] == 10.0
    assert len(curve["frequencies_hz"]) == len(curve["tl_db"]) == 18
    assert curve["tl_db"][-1] > curve["tl_db"][0]
    assert curve["project"]["material_snapshot"]["data_status"] == "synthetic"
    assert (tmp_path / "spectra.csv").stat().st_size > 100
    assert "<!doctype html>" in (tmp_path / "report.html").read_text(encoding="utf-8").lower()
    assert subprocess.run(command, capture_output=True, env=env).returncode == 0
    assert (tmp_path / "result.json").read_bytes() == first


def test_cli_invalid_project_fails_without_report(tmp_path):
    source = tmp_path / "bad.json"
    source.write_text('{"schema_version": 999}', encoding="utf-8")
    output = tmp_path / "results"
    result = subprocess.run(
        [sys.executable, "-m", "noiz_transmission.cli", "predict", str(source),
         "--output-dir", str(output)], capture_output=True,
    )
    assert result.returncode == 2
    assert not output.exists()
