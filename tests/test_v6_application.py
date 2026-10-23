"""V6 model choice, historical reproducibility and finite-input propagation."""

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from noiz_transmission.application.assemblies import Cavity, Panel
from noiz_transmission.application.assembly_services import (
    default_project,
    default_project_v3,
    default_project_v6,
    export_assembly_csv,
    export_assembly_html,
    load_assembly,
    load_workspace,
    predict_assembly,
    project_from_dict,
    project_to_dict,
    save_assembly,
    save_workspace,
)
from noiz_transmission.core.finite_panel import FINITE_MODEL_ID
from noiz_transmission.core.transfer import MODEL_ID


def _historical_snapshot(project):
    data = project_to_dict(project)
    del data["calculation_model"]
    for panel in data["panels"]:
        del panel["edge_loss_factor"]
    return data


def test_new_projects_choose_finite_without_guessing_boundary_damping():
    project = default_project_v6()
    assert project.calculation_model == "finite"
    assert project.panels[0].edge_loss_factor == 0
    assert default_project_v3().calculation_model == "infinite"
    assert default_project_v6("porous").calculation_model == "infinite"


@pytest.mark.parametrize("invalid", [-.01, True, float("inf"), "0.02"])
def test_edge_loss_is_typed_nonnegative_and_finite(invalid):
    with pytest.raises(ValueError, match="edge_loss_factor"):
        replace(default_project_v6().panels[0], edge_loss_factor=invalid)


@pytest.mark.parametrize("invalid", ["sewell", "", None, True, 1])
def test_unknown_model_never_silently_falls_back(invalid):
    with pytest.raises(ValueError, match="calculation_model"):
        replace(default_project_v6(), calculation_model=invalid)


def test_schema4_roundtrip_retains_model_per_panel_losses_and_variants(tmp_path):
    single = default_project_v6()
    active = replace(single, width_m=3.1, height_m=2.8,
                     panels=(replace(single.panels[0], edge_loss_factor=.015),))
    legacy = default_project()
    path = tmp_path / "finite.noiz.json"
    save_workspace(active, (legacy,), path)
    encoded = path.read_bytes()
    loaded, variants = load_workspace(path)
    assert loaded == active
    assert variants == (legacy,)
    payload = json.loads(encoded)
    assert payload["schema_version"] == 4
    assert payload["model_name"] == FINITE_MODEL_ID
    assert payload["project"]["panels"][0]["edge_loss_factor"] == .015
    save_workspace(loaded, variants, path)
    assert path.read_bytes() == encoded


def test_schema3_workspace_migration_preserves_equations_and_file(tmp_path):
    single, double = default_project_v3(), default_project()
    payload = {"schema_version": 3, "model_name": MODEL_ID,
               "project": _historical_snapshot(single),
               "variants": [_historical_snapshot(double)]}
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    active, variants = load_workspace(path)
    assert active == single
    assert variants == (double,)
    assert path.read_bytes() == original
    before = predict_assembly(single)
    after = predict_assembly(active)
    assert after == before
    assert after.model_name == MODEL_ID


@pytest.mark.parametrize("mutation", [
    lambda p: p["project"].update(calculation_model="finite"),
    lambda p: p["project"]["panels"][0].update(edge_loss_factor=.01),
    lambda p: p["project"].pop("width_m"),
    lambda p: p.update(model_name=FINITE_MODEL_ID),
])
def test_old_schema_does_not_accept_unrecorded_finite_settings(tmp_path, mutation):
    payload = {"schema_version": 3, "model_name": MODEL_ID,
               "project": _historical_snapshot(default_project_v3())}
    mutation(payload)
    path = tmp_path / "old.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_assembly(path)


def test_model_header_must_match_actual_project(tmp_path):
    path = tmp_path / "tampered.json"
    save_assembly(default_project_v6(), path)
    data = json.loads(path.read_text())
    data["model_name"] = MODEL_ID
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="no coincide"):
        load_assembly(path)


def test_current_project_requires_explicit_new_fields():
    data = project_to_dict(default_project_v6())
    del data["panels"][0]["edge_loss_factor"]
    with pytest.raises(ValueError, match="campos"):
        project_from_dict(data)


def test_committed_v3_examples_load_with_legacy_equations():
    examples = Path(__file__).resolve().parents[1] / "examples"
    for path in examples.glob("v3*.noiz.json"):
        active, variants = load_workspace(path)
        for project in (active, *variants):
            assert project.calculation_model == "infinite"
            assert all(panel.edge_loss_factor == 0 for panel in project.panels)


def test_geometry_changes_finite_diffuse_curve_but_not_legacy_curve():
    project = default_project_v6()
    enlarged = replace(project, width_m=6, height_m=6)
    small, large = predict_assembly(project), predict_assembly(enlarged)
    assert small.model_name == large.model_name == FINITE_MODEL_ID
    assert abs(small.tl_db[0] - large.tl_db[0]) > .1
    historical = predict_assembly(replace(project, calculation_model="infinite"))
    historical_large = predict_assembly(replace(enlarged, calculation_model="infinite"))
    assert historical.tl_db == historical_large.tl_db


def test_edge_loss_changes_coincidence_response_without_changing_mass():
    project = default_project_v6("glazing")
    changed = replace(project, panels=(replace(project.panels[0], edge_loss_factor=.08),))
    base, damped = predict_assembly(project), predict_assembly(changed)
    assert max(abs(a - b) for a, b in zip(base.tl_db, damped.tl_db, strict=True)) > .1
    assert base.total_mass_kg_m2 == damped.total_mass_kg_m2
    assert base.critical_frequencies_hz == damped.critical_frequencies_hz
    assert any("doble conteo" in item for item in damped.warnings)


def test_legacy_rejects_requested_edge_damping_instead_of_ignoring_it():
    project = default_project_v3()
    changed = replace(project, panels=(replace(project.panels[0], edge_loss_factor=.01),))
    with pytest.raises(ValueError, match="modelo histórico infinito"):
        predict_assembly(changed)


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_all_topologies_have_finite_model_and_expected_air_spring_diagnostics(count):
    single = default_project_v6()
    project = replace(single, incidence="normal", panels=single.panels * count,
                      cavities=(Cavity(),) * (count - 1))
    result = predict_assembly(project)
    assert result.model_name == FINITE_MODEL_ID
    assert len(result.resonance_frequencies_hz) == count - 1
    assert len(result.critical_frequencies_hz) == count
    assert len(result.tl_db) == 21 and np.all(np.isfinite(result.tl_db))
    assert result.rw_db is None
    if count > 1:
        assert any("extensión propia" in item for item in result.warnings)


def test_submodal_frequency_range_is_reported_as_extrapolation():
    project = replace(default_project_v6(), width_m=.3, height_m=.3)
    result = predict_assembly(project)
    assert any("1.5 f₁₁" in item and "extrapolados" in item for item in result.warnings)


def test_normal_geometry_and_edge_loss_do_not_invent_modal_response():
    project = replace(default_project_v6(), incidence="normal")
    changed = replace(project, width_m=.8, height_m=1,
                      panels=(replace(project.panels[0], edge_loss_factor=.1),))
    baseline, edited = predict_assembly(project), predict_assembly(changed)
    assert baseline.tl_db == edited.tl_db
    assert any("tampoco actúan" in warning for warning in edited.warnings)


def test_finite_mode_does_not_turn_studs_into_independent_leaves():
    single = default_project_v6()
    project = replace(single, panels=single.panels * 2,
                      cavities=(Cavity(frame_type="steel"),))
    with pytest.raises(ValueError, match="puentes estructurales"):
        predict_assembly(project)


def test_reports_record_model_size_and_explicit_boundary_losses(tmp_path):
    single = default_project_v6()
    project = replace(single, panels=(Panel(single.panels[0].layers, "P1", .025),))
    result = predict_assembly(project)
    html, csv = tmp_path / "report.html", tmp_path / "spectra.csv"
    export_assembly_html((result,), html)
    export_assembly_csv((result,), csv)
    assert FINITE_MODEL_ID in html.read_text()
    assert "η de borde adicional" in html.read_text()
    assert "0.025" in html.read_text()
    assert "panel_edge_loss_factors" in csv.read_text()
    assert "panel_width_m" in csv.read_text()


def test_export_rejects_a_finite_result_falsely_labelled_as_legacy(tmp_path):
    prediction = predict_assembly(default_project_v6())
    with pytest.raises(ValueError, match="incompatible"):
        export_assembly_html((replace(prediction, model_name=MODEL_ID),), tmp_path / "bad.html")


def _project_with_validity_floor(frequency_hz):
    project = replace(default_project_v6(), width_m=1, height_m=1)
    side = math.sqrt(project.finite_validity_floor_hz / frequency_hz)
    return replace(project, width_m=side, height_m=side)


def test_validity_uses_exact_lower_band_edge_not_nominal_centre():
    exact_125_lower = 1000 * 10 ** (-.95)
    just_inside = _project_with_validity_floor(exact_125_lower * (1 - 1e-6))
    just_outside = _project_with_validity_floor(exact_125_lower * (1 + 1e-6))
    assert just_inside.rating_extrapolated_bands("stc") == ()
    assert just_outside.rating_extrapolated_bands("stc") == (125.,)
    assert just_outside.rating_extrapolated_bands("rw") == (100., 125.)
    assert just_outside.finite_validity_floor_hz < 125


def test_rw_and_stc_are_gated_independently():
    # The 100 Hz Rw band crosses the model limit, but the first STC band does not.
    result = predict_assembly(_project_with_validity_floor(100))
    assert result.rw_db is None
    assert result.stc_db is not None
    assert "100 Hz" in result.rating_unavailable_reason("rw")
    assert result.rating_unavailable_reason("stc") == ""
    assert any("Rw no emitido" in item for item in result.warnings)


def test_extrapolation_below_rating_bands_does_not_remove_valid_indices():
    result = predict_assembly(_project_with_validity_floor(60))
    assert result.project.extrapolated_bands_hz(result.frequencies_hz) == (50., 63.)
    assert result.rw_db is not None and result.stc_db is not None


def test_any_leaf_can_put_required_bands_outside_the_finite_range():
    single = _project_with_validity_floor(60)
    original = single.panels[0]
    thick_layer = replace(original.layers[0], thickness_mm=original.layers[0].thickness_mm * 3)
    project = replace(single, panels=(original, Panel((thick_layer,), "Thick")), cavities=(Cavity(),))
    assert project.finite_validity_floor_hz == pytest.approx(180)
    assert project.rating_extrapolated_bands("rw") == (100., 125., 160., 200.)
    assert project.rating_extrapolated_bands("stc") == (125., 160., 200.)


def test_unavailable_ratings_keep_tl_and_explain_reason_in_reports(tmp_path):
    result = predict_assembly(_project_with_validity_floor(120))
    assert result.rw_db is None and result.stc_db is None
    assert len(result.tl_db) == 21
    path = tmp_path / "extrapolation.html"
    export_assembly_html((result,), path)
    text = path.read_text()
    assert "Rw no emitido" in text and "STC no emitido" in text
    assert "1.5 f₁₁" in text
    with pytest.raises(ValueError, match="fuera del dominio"):
        export_assembly_html((replace(result, rw_db=50),), path)
