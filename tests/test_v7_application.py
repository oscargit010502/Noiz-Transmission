"""V7 construction routing, historical migration and exposed energy paths."""

import json
import math
from dataclasses import replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from noiz_transmission.application.assemblies import Cavity
from noiz_transmission.application.assembly_services import (
    DAVY_MODEL_ID,
    default_project_v7,
    export_assembly_csv,
    export_assembly_html,
    load_assembly,
    load_workspace,
    predict_assembly,
    save_workspace,
)
from noiz_transmission.core.finite_panel import FINITE_MODEL_ID


@pytest.fixture
def double():
    single = default_project_v7()
    return replace(single, panels=(single.panels[0], replace(single.panels[0], name="Panel 2")),
                   cavities=(Cavity(frame_type="timber", absorber_thickness_mm=40,
                                    flow_resistivity_pa_s_m2=10000),))


@pytest.mark.parametrize("frame", ["timber", "steel"])
def test_stud_wall_produces_two_energy_paths(double, frame):
    cavity = replace(double.cavities[0], frame_type=frame,
                     stud_attachment="point", point_compliance_m_n=1e-5 if frame == "steel" else None)
    result = predict_assembly(replace(double, cavities=(cavity,)))
    assert result.model_name == DAVY_MODEL_ID
    assert len(result.tl_db) == 21
    assert result.rw_db is not None and result.stc_db is not None
    assert np.isfinite(result.tl_db).all()
    air, stud = np.array(result.airborne_transmission), np.array(result.studborne_transmission)
    assert np.all(air > 0) and np.any(stud > 0)
    np.testing.assert_allclose(10 ** (-np.array(result.tl_db) / 10), air + stud, rtol=1e-12)
    # A shared structural path cannot improve the airborne-only transmission.
    assert np.all(np.array(result.tl_db) <= -10 * np.log10(air) + 1e-12)
    assert any("Miki" in message for message in result.warnings)


def test_zero_quantity_removes_infill_even_with_saved_resistivity_and_alpha(double):
    retained = replace(double.cavities[0], absorber_count=0, cavity_absorption=.8)
    empty = replace(double.cavities[0], absorber_thickness_mm=0, flow_resistivity_pa_s_m2=None)
    a = predict_assembly(replace(double, cavities=(retained,)))
    b = predict_assembly(replace(double, cavities=(empty,)))
    np.testing.assert_allclose(a.tl_db, b.tl_db, rtol=0, atol=0)


def test_explicit_separated_frames_have_no_studborne_path(double):
    cavity = replace(double.cavities[0], frame_type="steel", stud_configuration="independent")
    result = predict_assembly(replace(double, cavities=(cavity,)))
    assert result.studborne_transmission == (0.,) * 21
    assert any("soleras compartidas" in message for message in result.warnings)


def test_steel_gauge_is_not_guessed_from_catalogue_thickness(double):
    cavity = replace(double.cavities[0], frame_type="steel")
    with pytest.raises(ValueError, match="compliance|gauge"):
        predict_assembly(replace(double, cavities=(cavity,)))


@pytest.mark.parametrize("frame", ["timber", "steel"])
def test_shared_stud_bay_domain_uses_spacing_and_gates_rw_stc_independently(double, frame):
    project = replace(double, cavities=(replace(double.cavities[0], stud_spacing_mm=400,
                                               frame_type=frame, stud_attachment="point",
                                               point_compliance_m_n=1e-5 if frame == "steel" else None),))
    layer = project.panels[0].layers[0]
    thickness = layer.thickness_mm / 1000
    rigidity = layer.young_modulus_pa * thickness**3 / (12 * (1 - layer.poisson_ratio**2))
    mass = layer.density_kg_m3 * thickness
    interstud_mode = math.pi / (2 * .4**2) * math.sqrt(rigidity / mass)
    assert project.panel_mode_basis == "stud_bay"
    assert project.first_panel_modes_hz == pytest.approx((interstud_mode, interstud_mode))
    assert project.finite_validity_floor_hz == pytest.approx(1.5 * interstud_mode)
    # At 400 mm, the 100 Hz Rw band crosses the bay limit, while STC starts at 125 Hz.
    result = predict_assembly(project)
    assert result.rw_db is None and result.stc_db is not None
    assert "entre montantes" in result.rating_unavailable_reason("rw")
    assert project.rating_extrapolated_bands("rw") == (100.,)
    assert project.rating_extrapolated_bands("stc") == ()
    # Full wall dimensions do not lower the shared-bay applicability limit.
    assert replace(project, width_m=8, height_m=6).first_panel_modes_hz == project.first_panel_modes_hz
    independent = replace(project, cavities=(replace(project.cavities[0], stud_configuration="independent"),))
    assert independent.panel_mode_basis == "full_panel"
    assert independent.finite_validity_floor_hz < project.finite_validity_floor_hz


@pytest.mark.parametrize("key,value", [
    ("fastener_spacing_mm", 0), ("fastener_spacing_mm", True),
    ("steel_gauge", -1), ("steel_gauge", "25"),
    ("point_compliance_m_n", float("nan")), ("line_compliance_m2_n", -1),
    ("cavity_absorption", 0), ("cavity_absorption", 1.1),
    ("stud_configuration", "staggered"), ("stud_attachment", "guessed"),
    ("steel_section", "made-up"),
])
def test_explicit_bridge_inputs_are_typed_and_bounded(key, value):
    with pytest.raises(ValueError):
        replace(Cavity(), **{key: value})


def test_schema5_roundtrip_preserves_bridge_parameters_and_old_model_variants(double, tmp_path):
    cavity = replace(double.cavities[0], frame_type="steel", steel_gauge=25,
                     fastener_spacing_mm=250, stud_attachment="point",
                     point_compliance_m_n=1.234567891e-5, cavity_absorption=.43)
    project = replace(double, cavities=(cavity,))
    legacy = load_assembly(Path(__file__).parents[1] / "examples/v6_single.noiz.json")
    path = tmp_path / "workspace.noiz.json"
    save_workspace(project, (legacy,), path)
    original = path.read_bytes()
    active, variants = load_workspace(path)
    assert active == project and variants == (legacy,)
    assert json.loads(original)["schema_version"] == 5
    assert variants[0].calculation_model == "finite"
    save_workspace(active, variants, path)
    assert path.read_bytes() == original


def test_schema4_migrates_without_converting_physics_or_rewriting_file(tmp_path):
    source = Path(__file__).parents[1] / "examples/v6_double.noiz.json"
    original = source.read_bytes()
    path = tmp_path / "v6.noiz.json"
    path.write_bytes(original)
    project = load_assembly(path)
    assert project.calculation_model == "finite"
    assert project.cavities[0].steel_gauge is None
    assert predict_assembly(project).model_name == FINITE_MODEL_ID
    assert path.read_bytes() == original
    payload = json.loads(original)
    payload["project"]["cavities"][0]["steel_gauge"] = 25
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Cavity V4"):
        load_assembly(path)


def test_v7_does_not_silently_route_triple_or_normal_to_other_models(double):
    triple = replace(double, panels=double.panels + (double.panels[1],),
                     cavities=double.cavities + (Cavity(),))
    with pytest.raises(ValueError, match="Single y Double"):
        predict_assembly(triple)
    with pytest.raises(ValueError, match="campo difuso"):
        predict_assembly(replace(double, incidence="normal"))


def test_cancellation_and_reports_keep_model_and_path_provenance(double, tmp_path):
    cancel = Event()
    cancel.set()
    with pytest.raises(ValueError, match="cancelado"):
        predict_assembly(double, cancel_event=cancel)
    result = predict_assembly(double)
    html, csv = tmp_path / "report.html", tmp_path / "spectra.csv"
    export_assembly_html((result,), html)
    export_assembly_csv((result,), csv)
    assert DAVY_MODEL_ID in html.read_text() and "V7" in html.read_text()
    assert "studborne_transmission" in html.read_text()
    assert "airborne_transmission" in csv.read_text()
