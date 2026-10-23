"""V3 editing, migration and physical feature dispatch regressions."""

import json
from dataclasses import replace

import numpy as np
import pytest

from noiz_transmission.application.assemblies import (
    Cavity,
    Facing,
    FloorSettings,
    LeakSettings,
    Panel,
    PorousSettings,
    RainfallSettings,
)
from noiz_transmission.application.assembly_services import (
    default_project,
    default_project_v3,
    describe_assembly,
    export_assembly_csv,
    load_assembly,
    octave_summary,
    predict_assembly,
    project_to_dict,
    save_assembly,
)


@pytest.fixture
def single():
    return replace(default_project_v3(), incidence="normal")


def test_default_single_and_mode_specific_excitation():
    assert len(default_project_v3().panels) == 1
    assert default_project_v3().element_type == "wall"
    assert default_project_v3("floor").excitation == "impact"
    assert default_project_v3("roof").excitation == "rainfall"
    assert default_project_v3("glazing").panels[0].layers[0].thickness_mm == 6


def test_quad_topology_and_limits(single):
    quad = replace(single, panels=single.panels * 4, cavities=(Cavity(),) * 3)
    assert len(quad.panels) == 4 and len(quad.cavities) == 3
    for element in ("floor", "roof", "porous"):
        with pytest.raises(ValueError, match="máximo"):
            replace(quad, element_type=element)
    with pytest.raises(ValueError, match="exactamente"):
        replace(quad, cavities=(Cavity(),) * 4)


def test_quad_prediction_contains_three_coupled_resonances(single):
    cavity = Cavity(absorber_thickness_mm=50, flow_resistivity_pa_s_m2=5000)
    project = replace(single, panels=single.panels * 4, cavities=(cavity,) * 3)
    result = predict_assembly(project)
    assert len(result.tl_db) == 21
    assert result.total_mass_kg_m2 == 40
    assert result.total_thickness_mm == 350
    # Eigenvalues of the four equal masses / three equal springs chain:
    # lambda_j = (2 - 2 cos(j*pi/4)) * k/m, j=1,2,3.
    scale = 1.21 * 343**2 / (0.1 * 10)
    expected = np.sqrt((2 - 2 * np.cos(np.arange(1, 4) * np.pi / 4)) * scale) / (2 * np.pi)
    assert result.resonance_frequencies_hz == pytest.approx(expected)


@pytest.mark.parametrize("value", [0, 11, True, 1.5])
def test_layer_quantity_limits(single, value):
    with pytest.raises(ValueError):
        replace(single.panels[0].layers[0], count=value)


def test_disabled_layers_are_preserved_but_excluded(single, tmp_path):
    first = single.panels[0].layers[0]
    inactive = replace(first, name="No participa", enabled=False, count=10, thickness_mm=50)
    edited = replace(single, panels=(Panel((first, inactive)),))
    expected = predict_assembly(single)
    result = predict_assembly(edited)
    assert result.tl_db == expected.tl_db
    assert result.total_mass_kg_m2 == expected.total_mass_kg_m2
    assert result.total_thickness_mm == expected.total_thickness_mm
    assert "No participa" not in describe_assembly(edited)
    path = tmp_path / "disabled.json"
    save_assembly(edited, path)
    assert load_assembly(path) == edited
    with pytest.raises(ValueError, match="active al menos"):
        predict_assembly(replace(single, panels=(Panel((inactive,)),)))


def test_absorber_count_zero_excludes_inactive_data():
    reference = replace(default_project(), incidence="normal")
    # Keep a deliberately incomplete material configuration; count zero disables it.
    disabled = Cavity(absorber_thickness_mm=900, flow_resistivity_pa_s_m2=None,
                      absorber_count=0)
    project = replace(reference, cavities=(disabled,))
    assert predict_assembly(project).tl_db == predict_assembly(reference).tl_db
    assert "900" not in describe_assembly(project)
    with pytest.raises(ValueError, match="profundidad"):
        replace(disabled, absorber_count=1)


def test_absorber_quantity_is_effective_thickness():
    reference = replace(default_project(), incidence="normal")
    two = Cavity(absorber_thickness_mm=25, absorber_count=2, flow_resistivity_pa_s_m2=5000)
    one = replace(two, absorber_thickness_mm=50, absorber_count=1)
    result = predict_assembly(replace(reference, cavities=(two,)))
    equivalent = predict_assembly(replace(reference, cavities=(one,)))
    assert result.tl_db == equivalent.tl_db


def test_geometry_drives_explicit_ideal_open_area(single):
    leak = LeakSettings(enabled=True, kind="slit", method="open_area", height_mm=2, length_mm=500)
    sealed = predict_assembly(single)
    result = predict_assembly(replace(single, leak=leak))
    fraction = 0.001 / (single.width_m * single.height_m)
    expected = -10 * np.log10((1 - fraction) * 10**(-np.array(sealed.tl_db) / 10) + fraction)
    assert result.tl_db == pytest.approx(expected)
    assert any("no es Gomperts ni Mechel" in warning for warning in result.warnings)
    smaller = predict_assembly(replace(single, width_m=single.width_m / 2, leak=leak))
    assert np.all(np.array(smaller.tl_db) < result.tl_db)
    aperture = replace(leak, kind="aperture", radius_mm=10)
    assert aperture.area_m2 == pytest.approx(np.pi * 0.01**2)


def test_oversized_or_double_counted_leak_is_rejected(single):
    leak = LeakSettings(enabled=True, method="open_area", height_mm=10_000, length_mm=10_000)
    with pytest.raises(ValueError, match="área de fuga"):
        predict_assembly(replace(single, leak=leak))
    with pytest.raises(ValueError, match="heredada"):
        predict_assembly(replace(single, leak=replace(leak, enabled=True), leak_percentage=1))


@pytest.mark.parametrize("method", ["gomperts", "mechel"])
def test_unverified_leak_solutions_never_silently_use_open_area(single, method):
    with pytest.raises(ValueError, match="implementación verificada"):
        predict_assembly(replace(single, leak=LeakSettings(enabled=True, method=method)))


@pytest.mark.parametrize("element,excitation", [("floor", "impact"), ("roof", "rainfall")])
def test_excitation_cannot_be_silently_substituted(single, element, excitation, tmp_path):
    project = replace(single, element_type=element, excitation=excitation)
    path = tmp_path / "unsupported.json"
    save_assembly(project, path)
    assert load_assembly(path) == project
    with pytest.raises(ValueError, match="no se genera una curva"):
        predict_assembly(project)


def test_current_schema_roundtrip_includes_all_settings(single, tmp_path):
    entry = replace(single.panels[0].layers[0].catalog_entry, kind="absorption")
    project = replace(
        single, facing=Facing(material=entry, thickness_mm=20, count=0),
        leak=LeakSettings(kind="aperture", position="corner", method="mechel", radius_mm=3,
                          cavity_empty=False, cavity_absorption=entry),
        rainfall=RainfallSettings(rain_type="natural", natural_mm_h=15, rainfall_area_m2=12),
        floor=FloorSettings(mode="predicted", base_floor="clt"),
        porous=PorousSettings(material=entry, thickness_mm=30, flow_resistivity_pa_s_m2=7000),
    )
    path = tmp_path / "v3.json"
    save_assembly(project, path)
    assert load_assembly(path) == project
    assert json.loads(path.read_text())["schema_version"] == 4
    payload = json.loads(path.read_text())
    payload["project"]["leak"]["unknown_parameter"] = 4
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="campos"):
        load_assembly(path)


def test_v2_migration_preserves_original_prediction_inputs(tmp_path):
    original = default_project()
    data = project_to_dict(original)
    for name in ("facing", "leak", "rainfall", "porous", "floor", "excitation",
                 "calculation_model"):
        del data[name]
    for panel in data["panels"]:
        del panel["edge_loss_factor"]
        for layer in panel["layers"]:
            del layer["enabled"]
    for cavity in data["cavities"]:
        for name in ("absorber_count", "stud", "gas"):
            del cavity[name]
    payload = {"schema_version": 2, "model_name": "transfer-matrix-plate-1", "project": data}
    path = tmp_path / "old-v2.json"
    path.write_text(json.dumps(payload))
    assert load_assembly(path) == original
    assert json.loads(path.read_text())["schema_version"] == 2
    del payload["project"]["width_m"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="V2"):
        load_assembly(path)


def test_octaves_average_energy_weighted_by_exact_bandwidth(single):
    result = predict_assembly(single)
    equal = replace(result, tl_db=(30.0,) * 21)
    summary = octave_summary(equal)
    assert tuple(f for f, _ in summary) == (63, 125, 250, 500, 1000, 2000, 4000)
    assert [v for _, v in summary] == pytest.approx([30] * 7)
    changed = replace(equal, tl_db=(0, 30, 30, *([30] * 18)))
    first = octave_summary(changed)[0][1]
    expected = -10 * np.log10((1 + 10**0.1 * 0.001 + 10**0.2 * 0.001)
                            / (1 + 10**0.1 + 10**0.2))
    assert first == pytest.approx(expected)
    assert first != pytest.approx(20)
    with pytest.raises(ValueError, match="21 tercios"):
        octave_summary(replace(result, frequencies_hz=result.frequencies_hz[1:]))


def test_facing_changes_curve_and_disabled_facing_is_exact_noop(single):
    reference = predict_assembly(single)
    settings = Facing(enabled=True, thickness_mm=20, flow_resistivity_pa_s_m2=5000, count=2)
    modified = predict_assembly(replace(single, facing=settings))
    assert not np.allclose(reference.tl_db, modified.tl_db)
    assert modified.total_thickness_mm == reference.total_thickness_mm + 40
    assert modified.total_mass_kg_m2 == reference.total_mass_kg_m2
    assert predict_assembly(replace(single, facing=replace(settings, count=0))).tl_db == reference.tl_db
    assert predict_assembly(replace(single, facing=replace(settings, enabled=False))).tl_db == reference.tl_db


def test_standalone_porous_has_no_phantom_plate_mass(single, tmp_path):
    project = replace(single, element_type="porous",
                      porous=PorousSettings(thickness_mm=50, flow_resistivity_pa_s_m2=5000))
    result = predict_assembly(project)
    assert result.total_mass_kg_m2 == 0
    assert result.total_thickness_mm == 50
    assert result.critical_frequencies_hz == result.resonance_frequencies_hz == ()
    assert all(value >= 0 for value in result.tl_db)
    export_assembly_csv([result], tmp_path / "porous.csv")
    assert (tmp_path / "porous.csv").exists()


def test_glazing_gas_changes_tl_and_mass_spring_diagnostic():
    reference = replace(default_project(), element_type="glazing", incidence="normal")
    argon = replace(reference, cavities=(Cavity(gas="argon"),))
    air_result, argon_result = predict_assembly(reference), predict_assembly(argon)
    assert not np.allclose(air_result.tl_db, argon_result.tl_db)
    assert argon_result.resonance_frequencies_hz != air_result.resonance_frequencies_hz
    assert any("20 °C" in warning and "argon" in warning for warning in argon_result.warnings)


def test_workspace_roundtrip_preserves_each_mode_topology_and_provenance(single, tmp_path):
    from noiz_transmission.application.assembly_services import load_workspace, save_workspace

    layer = replace(single.panels[0].layers[0], thickness_mm=19, count=2)
    quad = replace(single, name="Quad editado", panels=(Panel((layer,)),) * 4,
                   cavities=(Cavity(depth_mm=150),) * 3)
    floor = replace(default_project_v3("floor"), floor=FloorSettings(base_floor="clt"))
    roof = replace(default_project_v3("roof"),
                   rainfall=RainfallSettings(rain_type="natural", natural_mm_h=22))
    path = tmp_path / "workspace.json"
    # An outdated cached active project must not override the current active edits.
    stale_active = replace(single, name="Copia antigua")
    save_workspace(single, (stale_active, quad, floor, roof), path)
    active, variants = load_workspace(path)
    assert active == single
    assert variants == (quad, floor, roof)
    assert load_assembly(path) == single
    payload = json.loads(path.read_text())
    assert len(payload["variants"]) == 3
    assert "variants" not in payload["project"]
    # All source snapshots survive independently of both original and loaded instances.
    variant_layer = variants[0].panels[0].layers[0]
    assert variant_layer.thickness_mm == 19
    assert variant_layer.catalog_entry.properties["thickness_m"] == 0.0125
    variant_layer.catalog_entry.properties["thickness_m"] = 999
    assert quad.panels[0].layers[0].catalog_entry.properties["thickness_m"] == 0.0125
    assert load_workspace(path)[1][0].panels[0].layers[0].catalog_entry.properties["thickness_m"] == 0.0125


@pytest.mark.parametrize("mutation", [
    lambda p: p["variants"].append(p["variants"][0]),
    lambda p: p["variants"].append(p["project"]),
    lambda p: p["variants"][0].pop("width_m"),
    lambda p: p["variants"][0].update(variants=[]),
    lambda p: p["project"].update(variants=[]),
    lambda p: p.update(variants=None),
    lambda p: p["variants"][0]["panels"][0]["layers"][0].update(enabled=1),
])
def test_workspace_validation_covers_hidden_variants(single, tmp_path, mutation):
    from noiz_transmission.application.assembly_services import load_workspace, save_workspace

    path = tmp_path / "corrupt-workspace.json"
    save_workspace(single, (default_project(),), path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_text(json.dumps(payload))
    for loader in (load_workspace, load_assembly):
        with pytest.raises(ValueError):
            loader(path)


def test_project_dictionary_optional_variants_are_validated_without_nesting(single):
    from noiz_transmission.application.assembly_services import project_from_dict

    data = {**project_to_dict(single), "variants": [project_to_dict(default_project())]}
    assert project_from_dict(data) == single
    data["variants"][0]["variants"] = []
    with pytest.raises(ValueError, match="campos"):
        project_from_dict(data)


def test_workspace_duplicate_keys_or_write_failure_preserve_saved_work(single, tmp_path, monkeypatch):
    from noiz_transmission.application import assembly_services as service

    path = tmp_path / "workspace.json"
    double = default_project()
    service.save_workspace(single, (double,), path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="duplicada"):
        service.save_workspace(single, (double, replace(double, name="Conflicto")), path)
    assert path.read_bytes() == before

    def refuse_publish(*args):
        raise OSError("Fallo de disco simulado")

    monkeypatch.setattr(service.os, "replace", refuse_publish)
    with pytest.raises(OSError, match="disco"):
        service.save_workspace(replace(single, name="Edición"), (double,), path)
    assert path.read_bytes() == before
    assert tuple(tmp_path.iterdir()) == (path,)


def test_workspace_legacy_and_simple_project_files_have_no_hidden_variants(single, tmp_path):
    from noiz_transmission.application.assembly_services import load_workspace
    from noiz_transmission.application.services import Project, save_project

    simple = tmp_path / "simple.json"
    save_assembly(single, simple)
    assert load_workspace(simple) == (single, ())
    legacy = tmp_path / "v1.json"
    save_project(Project("Legacy", "synthetic-light-panel", 12.5), legacy)
    active, variants = load_workspace(legacy)
    assert active.name == "Legacy"
    assert variants == ()


def test_cli_calculates_active_workspace_but_validates_all_variants(single, tmp_path):
    from noiz_transmission import cli
    from noiz_transmission.application.assembly_services import save_workspace

    path = tmp_path / "workspace.json"
    # Inactive excitation may be unsupported physically, but must remain editable/persistable.
    save_workspace(single, (default_project_v3("roof"),), path)
    output = tmp_path / "results"
    assert cli.main(["assembly", str(path), "--output-dir", str(output)]) == 0
    result = json.loads((output / "result.json").read_text())
    assert len(result["predictions"]) == 1
    assert result["predictions"][0]["project"]["element_type"] == "wall"
    payload = json.loads(path.read_text())
    payload["variants"][0]["rainfall"]["natural_mm_h"] = -1
    path.write_text(json.dumps(payload))
    rejected_output = tmp_path / "rejected"
    with pytest.raises(SystemExit) as error:
        cli.main(["assembly", str(path), "--output-dir", str(rejected_output)])
    assert error.value.code == 2
    assert not rejected_output.exists()
