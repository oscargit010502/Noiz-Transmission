"""Application tests emphasize reproducibility, hostile inputs and export integrity."""

import csv
import json
from dataclasses import asdict, replace
from html.parser import HTMLParser

import pytest

from noiz_transmission.application import services
from noiz_transmission.application.materials import list_materials
from noiz_transmission.application.services import (
    Project,
    export_csv,
    export_html,
    load_project,
    predict,
    save_project,
)


@pytest.fixture
def project():
    return Project("Panel de referencia", "synthetic-light-panel", 12.5)


def test_prediction_resolves_snapshot_and_explains_limits(project):
    result = predict(project)
    assert result.surface_density_kg_m2 == 10.0
    assert len(result.frequencies_hz) == len(result.tl_db) == 18
    assert result.frequencies_hz[0] == 100
    assert result.frequencies_hz[-1] == 5000
    assert isinstance(result.rw_db, int)
    assert result.project.material_snapshot == list_materials()[0]
    assert result.project.catalog_version == "2026.10-synthetic-1"
    assert project.material_snapshot is None
    warnings = " ".join(result.warnings)
    assert "sintéticos" in warnings
    assert "coincidencia" in warnings
    assert "ISO 12354" in warnings
    assert "no constituye un ensayo" in warnings


def test_normal_incidence_has_no_rw_and_differs_from_diffuse(project):
    diffuse = predict(project)
    normal = predict(replace(project, model="normal_mass_law"))
    assert normal.rw_db is None
    assert all(a > b for a, b in zip(normal.tl_db, diffuse.tl_db, strict=True))


def test_full_hemisphere_project_roundtrip(project, tmp_path):
    hemisphere = replace(project, limiting_angle_deg=90)
    destination = tmp_path / "hemisphere.json"
    save_project(hemisphere, destination)
    result = predict(load_project(destination))
    assert result.project.limiting_angle_deg == 90
    assert all(a < b for a, b in zip(result.tl_db, predict(project).tl_db, strict=True))


def test_serialization_preserves_every_physical_input_and_is_deterministic(project, tmp_path):
    project = replace(
        project, air_density_kg_m3=1.18, sound_speed_m_s=340, limiting_angle_deg=70,
    )
    expected = predict(project)
    destination = tmp_path / "example.noiz.json"
    save_project(project, destination)
    first = destination.read_bytes()
    loaded = load_project(destination)
    assert predict(loaded) == expected
    save_project(loaded, destination)
    assert destination.read_bytes() == first
    payload = json.loads(first)
    assert payload["schema_version"] == 1
    assert payload["project"]["material_snapshot"] == asdict(list_materials()[0])
    assert payload["project"]["model_version"] == services.MODEL_VERSION


def test_saved_snapshot_survives_catalog_changes_and_removed_material(project, tmp_path, monkeypatch):
    destination = tmp_path / "snapshot.json"
    expected = predict(project)
    save_project(project, destination)
    altered = replace(list_materials()[0], density_kg_m3=1600)
    monkeypatch.setattr(services, "list_materials", lambda: (altered,))
    assert predict(project).surface_density_kg_m2 == 20
    assert predict(load_project(destination)) == expected
    monkeypatch.setattr(services, "list_materials", lambda: ())
    assert predict(load_project(destination)) == expected


@pytest.mark.parametrize("field,value", [
    ("name", ""),
    ("material_id", None),
    ("thickness_mm", 0),
    ("thickness_mm", -3),
    ("thickness_mm", True),
    ("thickness_mm", "12.5"),
    ("thickness_mm", float("nan")),
    ("air_density_kg_m3", 0),
    ("sound_speed_m_s", float("inf")),
    ("limiting_angle_deg", 0),
    ("limiting_angle_deg", 90.1),
    ("model", "unsupported-model"),
    ("model_version", "future-model"),
    ("material_snapshot", {}),
])
def test_invalid_projects_are_rejected(project, field, value):
    with pytest.raises(ValueError):
        replace(project, **{field: value})


def test_unknown_catalog_material_and_mismatched_snapshot_are_rejected(project):
    with pytest.raises(ValueError, match="desconocido"):
        predict(replace(project, material_id="does-not-exist"))
    with pytest.raises(ValueError, match="no coincide"):
        replace(project, material_snapshot=list_materials()[1])


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version=True),
    lambda data: data.update(schema_version=2),
    lambda data: data.update(extra=0),
    lambda data: data["project"].update(extra=0),
    lambda data: data["project"].pop("sound_speed_m_s"),
    lambda data: data["project"].update(thickness_mm=True),
    lambda data: data["project"].update(thickness_mm="12.5"),
    lambda data: data["project"].update(model_version="future-model"),
    lambda data: data["project"].update(material_snapshot=None),
    lambda data: data["project"].update(catalog_version=None),
    lambda data: data["project"]["material_snapshot"].update(density_kg_m3=-1),
    lambda data: data["project"]["material_snapshot"].update(id="different-id"),
])
def test_loading_rejects_schema_tampering(project, tmp_path, mutation):
    destination = tmp_path / "tampered.json"
    save_project(project, destination)
    payload = json.loads(destination.read_text())
    mutation(payload)
    destination.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_project(destination)


def test_loading_rejects_nonfinite_literal(project, tmp_path):
    destination = tmp_path / "nan.json"
    save_project(project, destination)
    text = destination.read_text().replace('"thickness_mm": 12.5', '"thickness_mm": NaN')
    destination.write_text(text)
    with pytest.raises(ValueError, match="no finita"):
        load_project(destination)


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def test_html_escapes_user_and_source_strings_and_contains_both_spectra(project, tmp_path):
    material = replace(list_materials()[0], source="<script>alert('source')</script>")
    result = predict(replace(
        project, name='<img src=x onerror="alert(1)">', material_snapshot=material,
    ))
    other = predict(replace(project, name="Segunda curva", model="normal_mass_law"))
    destination = tmp_path / "report.html"
    export_html([result, other], destination)
    text = destination.read_text(encoding="utf-8")
    parser = _TagCollector()
    parser.feed(text)
    assert "script" not in parser.tags and "img" not in parser.tags
    assert "&lt;script&gt;" in text and "&lt;img" in text
    assert parser.tags.count("section") == 2
    for name in ("density_kg_m3", "source", "version", "uncertainty"):
        assert f"material_{name}" in text
    assert "project_air_density_kg_m3" in text
    assert "project_limiting_angle_deg" in text
    assert "software_versions" in text
    assert "Segunda curva" in text
    assert "5000" in text


@pytest.mark.parametrize("name", ["=1+2", "+SUM(A1)", "-1+2", "@SUM(A1)", "  =1+2", "\t=1+2"])
def test_csv_neutralizes_spreadsheet_formulas_in_user_strings(project, tmp_path, name):
    destination = tmp_path / "report.csv"
    export_csv([predict(replace(project, name=name))], destination)
    with destination.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["project_name"] == "'" + name


def test_csv_preserves_multiple_spectra_and_complete_provenance(project, tmp_path):
    results = [predict(project), predict(replace(project, model="normal_mass_law"))]
    destination = tmp_path / "comparison.csv"
    export_csv(results, destination)
    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 36
    assert {row["prediction_index"] for row in rows} == {"1", "2"}
    for index, result in enumerate(results, start=1):
        selected = [row for row in rows if row["prediction_index"] == str(index)]
        assert tuple(float(row["frequency_hz"]) for row in selected) == result.frequencies_hz
        assert tuple(float(row["tl_db"]) for row in selected) == result.tl_db
        assert selected[0]["project_model"] == result.project.model
        assert selected[0]["material_source"] == result.project.material_snapshot.source
        assert "numpy" in json.loads(selected[0]["software_versions"])
    assert rows[18]["rw_db_illustrative"] == ""


@pytest.mark.parametrize("exporter", [export_csv, export_html])
def test_export_requires_a_nonempty_collection(project, tmp_path, exporter):
    with pytest.raises(ValueError, match="al menos"):
        exporter([], tmp_path / "empty")
    invalid = replace(predict(project), tl_db=(1.0,))
    with pytest.raises(ValueError, match="longitud"):
        exporter([invalid], tmp_path / "invalid")
