"""V2 reproducibility, physical dispatch and unsupported-model guardrails."""

import csv
import json
import math
import warnings
from dataclasses import FrozenInstanceError, replace
from html.parser import HTMLParser
from threading import Event

import numpy as np
import pytest

from noiz_transmission.application import assembly_services as service
from noiz_transmission.application.assemblies import AssemblyProject, Cavity, Layer, Panel
from noiz_transmission.application.assembly_services import (
    default_project,
    export_assembly_csv,
    export_assembly_html,
    layer_from_entry,
    load_assembly,
    migrate_legacy_project,
    predict_assembly,
    project_from_dict,
    project_to_dict,
    save_assembly,
)
from noiz_transmission.application.materials import list_materials
from noiz_transmission.application.services import Project, save_project
from noiz_transmission.catalog import CatalogEntry
from noiz_transmission.core.ratings import ISO717_FREQUENCIES_HZ, iso717_rw
from noiz_transmission.core.transfer import Plate, predict_multilayer


@pytest.fixture
def layer():
    return Layer("Placa sintética", 12.5, 800, 2.5e9, 0.03, 0.25)


@pytest.fixture
def single(layer):
    return AssemblyProject("Panel de referencia", (Panel((layer,)),))


@pytest.fixture(scope="module")
def double_prediction():
    return predict_assembly(default_project())


@pytest.fixture
def catalog_entry():
    return CatalogEntry(
        "xml:" + "1" * 64 + ":1", "material", "Panel de prueba", "Gypsum", "Fabricante de prueba",
        ("Spain", "Colombia"),
        {"material_type": "Isotropic", "solid_model_eligible": True,
         "density_kg_m3": 800.0, "thickness_m": 0.0125, "young_modulus_pa": 2.5e9,
         "loss_factor": 0.03, "poisson_ratio": 0.25, "source_version": "9.0",
         "source_release": "22", "measurement_verified": False},
        {"SideA/Thickness": "0.0125", "Measurement/Source": "XXX"},
        "synthetic.xml", "1" * 64, "Material[1]", ("Fuente sin validar",),
    )


@pytest.mark.parametrize("field,value", [
    ("name", " "), ("thickness_mm", 0), ("thickness_mm", -2), ("thickness_mm", True),
    ("density_kg_m3", "800"), ("density_kg_m3", float("inf")),
    ("young_modulus_pa", float("nan")), ("young_modulus_pa", 0),
    ("loss_factor", -0.1), ("poisson_ratio", 0.5), ("poisson_ratio", -1),
    ("count", True), ("count", 0), ("count", 1.5), ("catalog_entry", {}), ("profile", {}),
])
def test_layer_rejects_nonphysical_or_untyped_inputs(layer, field, value):
    with pytest.raises(ValueError):
        replace(layer, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("panels", ()), ("panels", []), ("cavities", (Cavity(),)),
    ("width_m", 0), ("height_m", True), ("air_density_kg_m3", float("inf")),
    ("sound_speed_m_s", 0), ("leak_percentage", -0.1), ("leak_percentage", 100.1),
    ("leak_percentage", True), ("limiting_angle_deg", 91), ("limiting_angle_deg", 0),
    ("element_type", "other"), ("element_type", []), ("incidence", "oblique"), ("notes", None),
])
def test_project_rejects_invalid_fields(single, field, value):
    with pytest.raises(ValueError):
        replace(single, **{field: value})


def test_assembly_topology_and_frozen_domain(single, layer):
    with pytest.raises(ValueError):
        Panel(())
    with pytest.raises(ValueError):
        Panel((layer,) * 7)
    with pytest.raises(ValueError):
        replace(single, panels=single.panels * 4, cavities=(Cavity(),) * 3)
    with pytest.raises(FrozenInstanceError):
        single.name = "Changed"
    triple = replace(single, panels=single.panels * 3, cavities=(Cavity(),) * 2)
    assert len(triple.panels) == 3


@pytest.mark.parametrize("kwargs", [
    {"depth_mm": -1}, {"absorber_thickness_mm": -1}, {"absorber_thickness_mm": 101},
    {"flow_resistivity_pa_s_m2": 0}, {"flow_resistivity_pa_s_m2": True},
    {"stud_spacing_mm": 0}, {"stud_width_mm": float("nan")}, {"frame_type": ""},
])
def test_cavity_rejects_impossible_inputs(kwargs):
    with pytest.raises(ValueError):
        Cavity(**kwargs)


def test_catalog_layer_converts_si_length_and_detaches_snapshot(catalog_entry):
    layer = layer_from_entry(catalog_entry)
    assert layer.thickness_mm == 12.5
    assert layer.young_modulus_pa == 2.5e9
    assert layer.loss_factor == 0.03
    catalog_entry.properties["density_kg_m3"] = 1
    assert layer.density_kg_m3 == 800
    assert layer.catalog_entry.properties["density_kg_m3"] == 800


@pytest.mark.parametrize("kind,properties", [
    ("core", {}), ("material", {"solid_model_eligible": False}),
    ("material", {"material_type": "Orthotropic"}),
    ("material", {"anisotropic_ratio": 0.03}),
    ("material", {"orthotropic_ratio": True}),
    ("material", {"loss_factor": None}),
    ("material", {"poisson_ratio": True}),
])
def test_no_guessing_ineligible_or_missing_material_properties(catalog_entry, kind, properties):
    entry = replace(catalog_entry, kind=kind, properties={**catalog_entry.properties, **properties})
    with pytest.raises(ValueError):
        layer_from_entry(entry)


def test_default_has_reproducible_airborne_results_and_diagnostics(double_prediction):
    result = double_prediction
    assert result.frequencies_hz[0] == 50
    assert result.frequencies_hz[-1] == 5000
    assert len(result.frequencies_hz) == len(result.tl_db) == 21
    assert result.total_mass_kg_m2 == 20
    assert result.total_thickness_mm == 125
    expected_resonance = math.sqrt(1.21 * 343**2 / 0.1 * (1 / 10 + 1 / 10)) / (2 * math.pi)
    assert result.resonance_frequencies_hz == pytest.approx((expected_resonance,))
    selection = [value for frequency, value in zip(result.frequencies_hz, result.tl_db, strict=True)
                 if frequency in ISO717_FREQUENCIES_HZ]
    assert result.rw_db == iso717_rw(ISO717_FREQUENCIES_HZ, selection).rw_db
    text = " ".join(result.warnings)
    assert all(word in text for word in ("sintéticos", "ISO 12354", "infinito", "orientativo"))


def test_unbonded_layers_sum_mass_and_individual_rigidity(layer, single):
    panel = Panel((replace(layer, count=2),))
    project = replace(single, panels=(panel,), incidence="normal")
    result = predict_assembly(project)
    stiffness = layer.young_modulus_pa * (layer.thickness_mm / 1000)**3 / (
        12 * (1 - layer.poisson_ratio**2)
    )
    expected = predict_multilayer((Plate(20, 2 * stiffness, layer.loss_factor),), incidence="normal")
    assert result.tl_db == pytest.approx(expected)
    assert result.total_mass_kg_m2 == 20
    assert result.total_thickness_mm == 25
    assert result.rw_db is None
    critical = 343**2 / (2 * math.pi) * math.sqrt(20 / (2 * stiffness))
    assert result.critical_frequencies_hz == pytest.approx((critical,))


def test_geometry_does_not_invent_finite_panel_physics(single):
    normal = replace(single, incidence="normal")
    before = predict_assembly(normal)
    after = predict_assembly(replace(normal, width_m=5, height_m=4))
    assert after.tl_db == before.tl_db
    assert any("no modifican la curva" in warning for warning in after.warnings)


def test_cancellation_is_forwarded_without_losing_the_event(single, monkeypatch):
    event = Event()
    received = []

    def solver(*args, cancel_event=None, **kwargs):
        received.append(cancel_event)
        return np.zeros(21)

    monkeypatch.setattr(service, "predict_multilayer", solver)
    predict_assembly(single, cancel_event=event)
    assert received == [event]
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        predict_assembly(single, cancel_event=event)
    assert received == [event]


def test_plate_rigidity_and_damping_change_diffuse_curve(single, layer):
    before = predict_assembly(single)
    changed = predict_assembly(replace(single, panels=(Panel((replace(
        layer, young_modulus_pa=5e9, loss_factor=0.1,
    ),)),)))
    assert changed.critical_frequencies_hz != before.critical_frequencies_hz
    assert not np.allclose(changed.tl_db, before.tl_db)


def test_cavity_depth_changes_airborne_curve_and_resonance():
    first = replace(default_project(), incidence="normal")
    deeper = replace(first, cavities=(replace(first.cavities[0], depth_mm=200),))
    a, b = predict_assembly(first), predict_assembly(deeper)
    assert not np.allclose(a.tl_db, b.tl_db)
    assert b.resonance_frequencies_hz[0] == pytest.approx(a.resonance_frequencies_hz[0] / math.sqrt(2))


def test_triple_panel_coupled_modes(layer):
    project = AssemblyProject("Tres placas", (Panel((layer,)),) * 3, (Cavity(),) * 2,
                              incidence="normal", leak_percentage=0.1)
    result = predict_assembly(project)
    expected = math.sqrt(1.21 * 343**2 / 0.1 / 10) / (2 * math.pi)
    assert result.resonance_frequencies_hz == pytest.approx((expected, math.sqrt(3) * expected))


def test_leak_is_area_weighted_energy_transmission(single):
    normal = replace(single, incidence="normal")
    sealed = predict_assembly(normal)
    leaky = predict_assembly(replace(normal, leak_percentage=1))
    expected = -10 * np.log10(0.99 * 10 ** (-np.array(sealed.tl_db) / 10) + 0.01)
    assert leaky.tl_db == pytest.approx(expected)
    assert max(leaky.tl_db) <= 20
    opened = predict_assembly(replace(normal, leak_percentage=100))
    assert opened.tl_db == pytest.approx(np.zeros(21))


@pytest.mark.parametrize("frame_type", ["timber", "steel", "resilient", "unknown"])
def test_frame_bridges_can_be_saved_but_not_silently_calculated(tmp_path, frame_type):
    project = replace(default_project(), cavities=(Cavity(frame_type=frame_type),))
    path = tmp_path / "framed.json"
    save_assembly(project, path)
    assert load_assembly(path) == project
    with pytest.raises(ValueError, match="puentes estructurales"):
        predict_assembly(project)


def test_other_unsupported_modes_can_be_saved_but_not_predicted(single, catalog_entry):
    floor_cover = replace(catalog_entry, kind="floor_cover")
    with pytest.raises(ValueError, match="impacto"):
        predict_assembly(replace(single, floor_cover=floor_cover))
    profile = replace(catalog_entry, kind="profile")
    profiled = replace(single.panels[0].layers[0], profile=profile)
    with pytest.raises(ValueError, match="perfiles"):
        predict_assembly(replace(single, panels=(Panel((profiled,)),)))
    with pytest.raises(ValueError, match="poroso independiente"):
        predict_assembly(replace(single, element_type="porous"))


@pytest.mark.parametrize("kwargs", [
    {"absorber_thickness_mm": 50}, {"flow_resistivity_pa_s_m2": 10_000},
])
def test_porous_data_must_be_explicit(kwargs):
    project = replace(default_project(), cavities=(Cavity(**kwargs),))
    with pytest.raises(ValueError, match="resistividad"):
        predict_assembly(project)


def test_absorption_damping_is_never_inferred_as_flow_resistivity(catalog_entry):
    absorber = replace(catalog_entry, kind="absorption", properties={"damping_raw": 15_000})
    project = replace(default_project(), cavities=(Cavity(absorber=absorber,
                                                         absorber_thickness_mm=50),))
    with pytest.raises(ValueError, match="Damping del XML no es resistividad"):
        predict_assembly(project)


def test_miki_warning_uses_exact_band_edges_and_is_preserved_not_emitted():
    # Nominal centres alone fit 0.01 <= f/sigma <= 1, but exact band edges
    # extend beyond that interval. The model's empirical interval is open.
    filled = replace(default_project(), incidence="normal", cavities=(Cavity(
        absorber_thickness_mm=50, flow_resistivity_pa_s_m2=5000,
    ),))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = predict_assembly(filled)
    assert any("Extrapolación Miki" in warning and "50 < f < 5000" in warning
               for warning in result.warnings)
    empty = predict_assembly(replace(filled, cavities=(Cavity(),)))
    assert not np.allclose(result.tl_db, empty.tl_db)


def test_horizontal_elements_remain_airborne(single):
    result = predict_assembly(replace(single, element_type="floor", incidence="normal"))
    assert any("no se predice impacto" in warning for warning in result.warnings)
    assert result.rw_db is None


def test_roundtrip_full_snapshot_and_manual_overrides(single, catalog_entry, tmp_path):
    source_layer = layer_from_entry(catalog_entry)
    layer = replace(source_layer, thickness_mm=15, count=2)
    project = replace(single, panels=(Panel((layer,), "Exterior"),), notes="Notas <usuario>")
    path = tmp_path / "snapshot.noiz.json"
    save_assembly(project, path)
    first = path.read_bytes()
    loaded = load_assembly(path)
    assert loaded == project
    assert loaded.panels[0].layers[0].catalog_entry.properties["thickness_m"] == 0.0125
    assert loaded.panels[0].layers[0].thickness_mm == 15
    save_assembly(loaded, path)
    assert path.read_bytes() == first
    payload = json.loads(first)
    assert payload["schema_version"] == 2
    assert payload["model_name"] == "transfer-matrix-plate-1"
    assert payload["project"]["panels"][0]["layers"][0]["catalog_entry"]["raw_fields"] == catalog_entry.raw_fields
    result = predict_assembly(replace(loaded, incidence="normal"))
    assert any("valores editados" in warning for warning in result.warnings)
    assert any("9.0/22" in warning for warning in result.warnings)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=True),
    lambda d: d.update(schema_version=3),
    lambda d: d.update(model_name="future"),
    lambda d: d.update(extra=1),
    lambda d: d["project"].update(extra=1),
    lambda d: d["project"].pop("width_m"),
    lambda d: d["project"].update(width_m=True),
    lambda d: d["project"].update(air_density_kg_m3=float("inf")),
    lambda d: d["project"]["panels"][0].update(extra=1),
    lambda d: d["project"]["panels"][0]["layers"][0].update(count=True),
    lambda d: d["project"]["panels"][0]["layers"][0].update(thickness_mm="12.5"),
    lambda d: d["project"]["panels"][0]["layers"][0]["catalog_entry"].update(extra=1),
    lambda d: d["project"]["cavities"][0].update(depth_mm=None),
])
def test_project_file_rejects_tampering(tmp_path, mutation):
    path = tmp_path / "tampered.json"
    save_assembly(default_project(), path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_assembly(path)


def test_duplicate_json_keys_and_nonfinite_literals_are_rejected(single, tmp_path):
    path = tmp_path / "tampered.json"
    save_assembly(single, path)
    original = path.read_text()
    path.write_text(original.replace('"schema_version": 2', '"schema_version": 2, "schema_version": 2'))
    with pytest.raises(ValueError, match="repetido"):
        load_assembly(path)
    path.write_text(original.replace('"width_m": 2.4', '"width_m": NaN'))
    with pytest.raises(ValueError, match="no finita"):
        load_assembly(path)


def test_serialization_failure_preserves_existing_project(single, tmp_path, monkeypatch):
    path = tmp_path / "safe.json"
    save_assembly(single, path)
    before = path.read_bytes()

    def fail(*args):
        raise OSError("Injected replacement failure")

    monkeypatch.setattr(service.os, "replace", fail)
    with pytest.raises(OSError):
        save_assembly(replace(single, name="New"), path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_project_dictionary_conversion_is_detached(catalog_entry, single):
    project = replace(single, panels=(Panel((layer_from_entry(catalog_entry),)),))
    data = project_to_dict(project)
    restored = project_from_dict(data)
    data["panels"][0]["layers"][0]["catalog_entry"]["raw_fields"]["SideA/Thickness"] = "99"
    assert restored.panels[0].layers[0].catalog_entry.raw_fields["SideA/Thickness"] == "0.0125"
    assert project.panels[0].layers[0].catalog_entry.raw_fields["SideA/Thickness"] == "0.0125"


def test_legacy_migration_preserves_snapshot_and_declares_model_change(tmp_path, monkeypatch):
    material = list_materials()[0]
    legacy = Project("Legacy", material.id, 18, model="normal_mass_law", material_snapshot=material)
    path = tmp_path / "v1.json"
    save_project(legacy, path)
    monkeypatch.setattr(service, "list_materials", lambda: ())
    migrated = load_assembly(path)
    assert migrated == migrate_legacy_project(service.load_project(path))
    layer = migrated.panels[0].layers[0]
    assert layer.thickness_mm == 18
    assert layer.density_kg_m3 == material.density_kg_m3
    assert layer.loss_factor == 0.01
    assert "no reproduce la ley de masas V1" in migrated.notes
    assert "Factor de pérdidas supuesto" in migrated.notes
    assert json.loads(layer.catalog_entry.raw_fields["source"]) == material.source
    assert migrated.incidence == "normal"
    assert json.loads(path.read_text())["schema_version"] == 1


def test_unknown_legacy_material_fails():
    with pytest.raises(ValueError, match="desconocido"):
        migrate_legacy_project(Project("Old", "missing", 12.5))


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def test_export_preserves_full_results_and_escapes_sources(double_prediction, tmp_path):
    result = replace(double_prediction, project=replace(
        double_prediction.project, name='<img src=x onerror="alert(1)">', notes="<script>bad</script>",
    ))
    path = tmp_path / "report.html"
    export_assembly_html([result, double_prediction], path)
    text = path.read_text()
    parser = _Tags()
    parser.feed(text)
    assert "script" not in parser.tags and "img" not in parser.tags
    assert "&lt;img" in text and "&lt;script&gt;" in text
    assert parser.tags.count("section") == 2
    assert "source_sha256" in text and "software_versions" in text and "5000" in text


@pytest.mark.parametrize("name", ["=1+2", " @SUM(A1)", "+SUM(A1)", "\t=1", "-cmd"])
def test_csv_formula_injection_and_snapshot(double_prediction, name, tmp_path):
    result = replace(double_prediction, project=replace(double_prediction.project, name=name))
    path = tmp_path / "report.csv"
    export_assembly_csv([result, double_prediction], path)
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 42
    assert rows[0]["project_name"] == "'" + name
    assert json.loads(rows[0]["project_json"])["name"] == name
    assert tuple(float(row["tl_db"]) for row in rows[:21]) == result.tl_db
    assert {row["prediction_index"] for row in rows} == {"1", "2"}
    assert json.loads(rows[0]["software_versions"])["numpy"]


@pytest.mark.parametrize("exporter", [export_assembly_csv, export_assembly_html])
def test_export_rejects_invalid_results(double_prediction, tmp_path, exporter):
    with pytest.raises(ValueError, match="al menos"):
        exporter([], tmp_path / "empty")
    with pytest.raises(ValueError, match="longitud"):
        exporter([replace(double_prediction, tl_db=(1.0,))], tmp_path / "bad")
    with pytest.raises(ValueError, match="finito"):
        exporter([replace(double_prediction, tl_db=(float("nan"),) * 21)], tmp_path / "bad")
