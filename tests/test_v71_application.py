"""Automatic frame/fibre choices are usable, explicit and reproducible."""

import json
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from noiz_transmission.application.assemblies import Cavity
from noiz_transmission.application.assembly_services import (
    AUTO_MODEL_ID,
    DAVY_MODEL_ID,
    cavity_from_entry,
    default_project_v7,
    default_project_v71,
    export_assembly_csv,
    export_assembly_html,
    load_workspace,
    predict_assembly,
    save_workspace,
)
from noiz_transmission.application.frame_models import resolve_absorption, resolve_frame
from noiz_transmission.catalog import load_application_catalog


@pytest.fixture
def double():
    single = default_project_v71()
    return replace(single, panels=(single.panels[0], replace(single.panels[0], name="Panel 2")),
                   cavities=(Cavity(frame_type="steel", absorber_thickness_mm=40),))


@pytest.fixture(scope="module")
def catalog():
    return load_application_catalog()


@pytest.mark.parametrize("material", ["steel", "timber"])
def test_ordinary_double_computes_without_compliance_gauge_or_resistivity(double, material):
    project = replace(double, cavities=(replace(double.cavities[0], frame_type=material),))
    result = predict_assembly(project)
    assert result.model_name == AUTO_MODEL_ID
    assert result.rw_db is not None and result.stc_db is not None
    assert len(result.tl_db) == 21 and np.isfinite(result.tl_db).all()
    np.testing.assert_allclose(10 ** (-np.array(result.tl_db) / 10),
                               np.array(result.airborne_transmission) + result.studborne_transmission)
    params = result.resolved_parameters
    assert params["frame"]["profile"] == "line"
    assert params["absorption"]["flow_resistivity_pa_s_m2"] == 20000
    assert "reference" in params["absorption"]["source"]
    assert project.cavities[0].flow_resistivity_pa_s_m2 is None
    assert project.cavities[0].point_compliance_m_n is None


def test_single_automatic_preserves_the_verified_single_solver():
    expected = predict_assembly(default_project_v7())
    actual = predict_assembly(default_project_v71())
    assert actual.tl_db == expected.tl_db
    assert actual.rw_db == expected.rw_db
    assert actual.resolved_parameters["single_solver"] == DAVY_MODEL_ID


def test_absorption_changes_continuously_through_50mm_and_quantity_zero_excludes_it(double):
    results = []
    for thickness in (40, 49.99, 50.0, 50.01):
        cavity = replace(double.cavities[0], absorber_thickness_mm=thickness)
        results.append(predict_assembly(replace(double, cavities=(cavity,))))
    assert not np.allclose(results[0].tl_db, results[2].tl_db)
    np.testing.assert_allclose(results[1].tl_db, results[3].tl_db, atol=.03)
    off = replace(double.cavities[0], absorber_count=0, flow_resistivity_pa_s_m2=99999)
    empty = replace(double.cavities[0], absorber_thickness_mm=0)
    assert predict_assembly(replace(double, cavities=(off,))).tl_db == predict_assembly(
        replace(double, cavities=(empty,))).tl_db


def test_declared_sigma_wins_over_reference_and_does_not_depend_on_density(double, catalog):
    record = next(entry for entry in catalog if entry.kind == "absorption")
    one = replace(double.cavities[0], absorber=record)
    changed = replace(record, properties={**record.properties, "density_kg_m3": 999})
    assert resolve_absorption(one).flow_resistivity_pa_s_m2 == resolve_absorption(
        replace(one, absorber=changed)).flow_resistivity_pa_s_m2
    declared = replace(changed, properties={**changed.properties, "flow_resistivity_pa_s_m2": 12000})
    assert resolve_absorption(replace(one, absorber=declared)).flow_resistivity_pa_s_m2 == 12000
    explicit = resolve_absorption(replace(one, absorber=declared, flow_resistivity_pa_s_m2=7500))
    assert explicit.flow_resistivity_pa_s_m2 == 7500
    assert explicit.source == "project-explicit"
    unknown = replace(record, category="Closed cell foam")
    assert any("sustitución explícita" in note for note in resolve_absorption(
        replace(one, absorber=unknown)).warnings)


@pytest.mark.parametrize("code,profile", [(0, "independent"), (7, "independent"),
                                         (8, "independent"), (4, "line"), (20, "line"),
                                         (5, "point_pair"), (87, "point_pair")])
def test_catalogue_contact_policy_is_language_independent(catalog, code, profile):
    matching = [e for e in catalog if e.kind == "connection"
                and e.properties.get("connection_code") == code]
    assert matching
    for entry in matching:
        cavity = cavity_from_entry(Cavity(), entry)
        resolved = resolve_frame(cavity)
        assert resolved.profile == profile
        assert resolve_frame(replace(cavity, stud=replace(entry, name="任意翻訳"))).profile == profile


def test_special_isolator_does_not_silently_become_no_connection(catalog, double):
    spring = next(e for e in catalog if e.kind == "connection"
                  and e.properties.get("connection_code") == 28)
    cavity = cavity_from_entry(double.cavities[0], spring)
    frame = resolve_frame(cavity)
    assert frame.profile == "line"
    assert any("no se atribuye una mejora" in note for note in frame.warnings)
    generic = replace(cavity, stud=None, frame_type="timber")
    actual = predict_assembly(replace(double, cavities=(cavity,)))
    expected = predict_assembly(replace(double, cavities=(generic,)))
    assert actual.tl_db == expected.tl_db


def test_independent_catalogue_topology_has_no_bridge(double, catalog):
    record = next(e for e in catalog if e.kind == "connection"
                  and e.properties.get("connection_code") == 8)
    result = predict_assembly(replace(double, cavities=(cavity_from_entry(double.cavities[0], record),)))
    assert result.studborne_transmission == (0.0,) * 21


def test_explicit_separated_frame_survives_upgrade_but_new_selection_supersedes_it(catalog):
    legacy = Cavity(frame_type="steel", stud_configuration="independent")
    assert resolve_frame(legacy).profile == "independent"
    shared = next(e for e in catalog if e.kind == "connection"
                  and e.properties.get("connection_code") == 4)
    selected = cavity_from_entry(legacy, shared)
    assert selected.stud_configuration == "shared"
    assert resolve_frame(selected).profile == "line"


def test_new_schema_roundtrip_preserves_old_manual_model_and_auto_variants(double, tmp_path):
    old_path = Path(__file__).resolve().parents[1] / "examples/v7_double_steel.noiz.json"
    before = old_path.read_bytes()
    legacy, _ = load_workspace(old_path)
    assert legacy.calculation_model == "davy"
    expected = predict_assembly(legacy)
    target = tmp_path / "work.noiz.json"
    single = default_project_v71()
    save_workspace(legacy, (single,), target)
    assert json.loads(target.read_text())["schema_version"] == 6
    restored, variants = load_workspace(target)
    assert restored == legacy and variants == (single,)
    assert predict_assembly(restored).tl_db == expected.tl_db
    assert old_path.read_bytes() == before
    save_workspace(double, (), target)
    assert load_workspace(target)[0] == double


def test_schema5_cannot_claim_new_automatic_equations(double, tmp_path):
    target = tmp_path / "invalid.json"
    save_workspace(double, (), target)
    payload = json.loads(target.read_text())
    payload.update(schema_version=5, model_name=DAVY_MODEL_ID)
    target.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="esquema 5"):
        load_workspace(target)


def test_automatic_sources_are_kept_in_json_csv_and_html(double, tmp_path):
    result = predict_assembly(double)
    assert json.loads(json.dumps(asdict(result)))["resolved_parameters"]["absorption"][
        "flow_resistivity_pa_s_m2"] == 20000
    csv, html = tmp_path / "out.csv", tmp_path / "out.html"
    export_assembly_csv((result,), csv)
    export_assembly_html((result,), html)
    for path in (csv, html):
        text = path.read_text()
        assert "hansen-6e-table-7.12-reference-fibre-20000" in text
        assert "sharp-contact-topology-1" in text


def test_cancelled_automatic_request_returns_no_result(double):
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        predict_assembly(double, cancel_event=event)
