"""Public V2 CLI workflows, independent of Qt and proprietary fixture files."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from noiz_transmission import cli
from noiz_transmission.application.assemblies import AssemblyProject, Layer, Panel
from noiz_transmission.application.assembly_services import save_assembly
from noiz_transmission.application.services import Project, save_project
from noiz_transmission.catalog import load_catalog
from noiz_transmission.core.transfer import NumericalConvergenceError

ROOT = Path(__file__).resolve().parents[1]


def _run(*arguments, env=None):
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})}
    return subprocess.run(
        [sys.executable, "-m", "noiz_transmission.cli", *map(str, arguments)],
        capture_output=True, text=True, encoding="utf-8", env=environment, timeout=30,
    )


@pytest.fixture
def project_path(tmp_path):
    project = AssemblyProject(
        "Placa sintética CLI", (Panel((Layer("Sintético", 12.5, 800, 2.5e9, 0.03),)),),
        incidence="normal", notes="Datos manuales sintéticos para verificación del CLI.",
    )
    destination = tmp_path / "single.noiz.json"
    save_assembly(project, destination)
    return destination


@pytest.fixture
def xml_files(tmp_path):
    # Synthetic records exercise the observed interchange structure; no vendor data.
    materials = tmp_path / "synthetic-materials.xml"
    materials.write_text('''<?xml version="1.0" encoding="utf-8"?>
<InsulMaterials xmlns="http://www.insul.co.nz" Version="9.0" Release="22">
 <Material><Name>Placa sintética CLI</Name><Category>Gypsum</Category>
 <Manufacturer>Sin fabricante</Manufacturer><Type>Isotropic</Type>
 <SideA><Thickness>0.0125</Thickness><Density>800</Density>
 <YoungsModulus>2500000000</YoungsModulus><Damping>0.03</Damping>
 <PoissonsRatio>0.25</PoissonsRatio></SideA>
 <Region><AllRegions>-1</AllRegions></Region></Material>
</InsulMaterials>''', encoding="utf-8")
    absorption = tmp_path / "synthetic-absorption.xml"
    absorption.write_text('''<InsulAbsorption Version="9.0" Release="22">
 <Absorption><Name>Relleno sintético CLI</Name><Category>Fibreglass</Category>
 <Properties><Density>20</Density><Thickness>0.05</Thickness><Damping>0.8</Damping>
 </Properties></Absorption></InsulAbsorption>''', encoding="utf-8")
    return materials, absorption


def test_assembly_cli_writes_complete_reproducible_reports(project_path, tmp_path):
    output = tmp_path / "results"
    command = ("assembly", project_path, project_path, "--output-dir", output)
    result = _run(*command)
    assert result.returncode == 0, result.stderr
    assert "sin Rw" in result.stdout
    assert not result.stderr
    first = (output / "result.json").read_bytes()
    payload = json.loads(first)
    assert payload["schema_version"] == 4
    assert set(payload["software"]) == {"noiz_transmission", "python", "numpy", "scipy"}
    assert len(payload["predictions"]) == 2
    predicted = payload["predictions"][0]
    assert predicted["model_name"] == "transfer-matrix-plate-1"
    assert predicted["total_mass_kg_m2"] == 10
    assert predicted["rw_db"] is None
    assert len(predicted["frequencies_hz"]) == len(predicted["tl_db"]) == 21
    assert predicted["warnings"]
    assert predicted["project"] == json.loads(project_path.read_text())["project"]
    with (output / "spectra.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 42
    assert {row["prediction_index"] for row in rows} == {"1", "2"}
    assert tuple(float(row["tl_db"]) for row in rows[:21]) == tuple(predicted["tl_db"])
    assert json.loads(rows[0]["project_json"]) == predicted["project"]
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "transfer-matrix-plate-1" in html
    assert _run(*command).returncode == 0
    assert (output / "result.json").read_bytes() == first


def test_assembly_failure_writes_no_partial_report(project_path, tmp_path):
    broken = tmp_path / "broken.noiz.json"
    broken.write_text('{"schema_version": 999}')
    output = tmp_path / "results"
    result = _run("assembly", project_path, broken, "--output-dir", output)
    assert result.returncode == 2
    assert "noiz:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


def test_assembly_supports_explicit_v1_migration_without_rewriting_source(tmp_path):
    old = tmp_path / "old.noiz.json"
    save_project(Project("Legacy CLI", "synthetic-light-panel", 12.5, "normal_mass_law"), old)
    before = old.read_bytes()
    result = _run("assembly", old, "--output-dir", tmp_path / "results")
    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "results" / "result.json").read_text())
    prediction = payload["predictions"][0]
    assert "Migrado desde V1" in prediction["project"]["notes"]
    assert "no reproduce la ley de masas V1" in prediction["project"]["notes"]
    snapshot = prediction["project"]["panels"][0]["layers"][0]["catalog_entry"]
    assert snapshot["raw_fields"]["source"]
    assert snapshot["source_sha256"]
    assert old.read_bytes() == before


def test_convergence_failure_is_a_clean_cli_error(project_path, tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise NumericalConvergenceError("La banda no converge")

    monkeypatch.setattr(cli, "predict_assembly", fail)
    output = tmp_path / "results"
    with pytest.raises(SystemExit) as error:
        cli.main(["assembly", str(project_path), "--output-dir", str(output)])
    assert error.value.code == 2
    assert "La banda no converge" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("failure", ["export", "publish"])
def test_failed_reports_preserve_previous_batch_and_unrelated_files(
    project_path, tmp_path, monkeypatch, failure,
):
    output = tmp_path / "previous-results"
    output.mkdir()
    originals = {name: f"Previous {name}".encode() for name in (
        "spectra.csv", "report.html", "result.json", "user-notes.txt",
    )}
    for name, content in originals.items():
        (output / name).write_bytes(content)
    if failure == "export":
        def fail_export(*args):
            raise OSError("Injected HTML failure")

        monkeypatch.setattr(cli, "export_assembly_html", fail_export)
    else:
        original_replace = cli.os.replace

        def fail_publish(source, target):
            if Path(source).parent.name.startswith(".noiz-reports-") and (
                Path(target) == output / "report.html"
            ):
                raise OSError("Injected publication failure")
            return original_replace(source, target)

        monkeypatch.setattr(cli.os, "replace", fail_publish)
    with pytest.raises(SystemExit) as error:
        cli.main(["assembly", str(project_path), "--output-dir", str(output)])
    assert error.value.code == 2
    assert {path.name: path.read_bytes() for path in output.iterdir()} == originals
    assert not list(tmp_path.glob(".noiz-reports-*"))


def test_catalog_import_batch_is_idempotent_and_lists_sources(xml_files, tmp_path):
    destination = tmp_path / "library" / "catalog.json"
    command = ("catalog", "import", *xml_files, "--output", destination)
    first = _run(*command)
    assert first.returncode == 0, first.stderr
    entries = load_catalog(destination)
    assert len(entries) == 2
    assert {entry.kind for entry in entries} == {"material", "absorption"}
    snapshot = destination.read_bytes()
    repeated = _run(*command)
    assert repeated.returncode == 0, repeated.stderr
    assert "0 nuevos" in repeated.stdout
    assert destination.read_bytes() == snapshot
    summary = _run("catalog", "list", "--input", destination)
    assert summary.returncode == 0, summary.stderr
    payload = json.loads(summary.stdout)
    assert payload["entry_count"] == 2
    assert payload["kinds"] == {"absorption": 1, "material": 1}
    assert set(payload["source_files"]) == {path.name for path in xml_files}
    assert "SHA-256" in first.stdout


def test_catalog_uses_configured_default_path(xml_files, tmp_path):
    destination = tmp_path / "portable" / "catalog.json"
    environment = {"NOIZ_CATALOG_PATH": str(destination)}
    result = _run("catalog", "import", xml_files[0], env=environment)
    assert result.returncode == 0, result.stderr
    assert len(load_catalog(destination)) == 1
    summary = _run("catalog", "list", env=environment)
    assert json.loads(summary.stdout)["path"] == str(destination)


@pytest.mark.parametrize("existing", [False, True])
def test_invalid_xml_batch_cannot_partially_mutate_catalog(xml_files, tmp_path, existing):
    destination = tmp_path / "library" / "catalog.json"
    if existing:
        assert _run("catalog", "import", xml_files[0], "--output", destination).returncode == 0
    before = destination.read_bytes() if existing else None
    malformed = tmp_path / "broken.xml"
    malformed.write_text("<InsulMaterials><Material>")
    result = _run("catalog", "import", xml_files[1], malformed, "--output", destination)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    if existing:
        assert destination.read_bytes() == before
    else:
        assert not destination.parent.exists()


def test_cli_import_does_not_load_qt():
    result = subprocess.run([
        sys.executable, "-c",
        "import sys; import noiz_transmission.cli; "
        "assert not any(name.startswith(('PySide6', 'pyqtgraph')) for name in sys.modules)",
    ], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_shipped_v2_examples_load_with_catalog_provenance():
    from noiz_transmission.application.assembly_services import load_assembly

    single = load_assembly(ROOT / "examples" / "single_plate.noiz.json")
    double = load_assembly(ROOT / "examples" / "double_leaf.noiz.json")
    assert len(single.panels) == 1 and not single.cavities
    assert len(double.panels) == 2 and len(double.cavities) == 1
    assert all(layer.catalog_entry.properties["data_status"] == "synthetic"
               for project in (single, double) for panel in project.panels for layer in panel.layers)
    assert single.panels == (double.panels[0],)
