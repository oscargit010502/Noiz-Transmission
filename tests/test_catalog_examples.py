"""Public fallback materials and example projects carry honest, portable sources."""

import hashlib
from importlib.resources import files
from pathlib import Path

import pytest

from noiz_transmission.application.assembly_services import (
    layer_from_entry,
    load_assembly,
    load_workspace,
)
from noiz_transmission.catalog import example_entries, load_catalog, save_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_fallback_has_usable_si_defaults_and_actual_source_hashes():
    entries = example_entries()
    assert len(entries) == 4
    assert len({entry.id for entry in entries}) == 4
    assert [layer_from_entry(entry).thickness_mm for entry in entries[:3]] == [12.5, 100, 6]
    assert entries[2].kind == "glazing"
    for entry in entries:
        assert entry.properties["data_status"] == "synthetic"
        assert entry.properties["license"] == "MIT"
        assert entry.properties["measurement_verified"] is False
        assert entry.manufacturer == "Sin fabricante"
        source = files("noiz_transmission.data").joinpath(entry.source_file).read_bytes()
        assert hashlib.sha256(source).hexdigest() == entry.source_sha256
    absorber = entries[-1]
    assert absorber.kind == "absorption"
    assert absorber.properties["thickness_m"] == 0.05
    assert "flow_resistivity_pa_s_m2" not in absorber.properties
    assert "damping_raw" not in absorber.properties
    with pytest.raises(ValueError):
        layer_from_entry(absorber)


def test_fallback_entries_are_detached_and_do_not_create_a_private_library(tmp_path):
    library_path = tmp_path / "library.json"
    assert load_catalog(library_path) == ()
    examples = example_entries()
    examples[0].properties["density_kg_m3"] = 1
    assert example_entries()[0].properties["density_kg_m3"] == 800
    assert load_catalog(library_path) == ()
    assert not library_path.exists()
    save_catalog(example_entries(), library_path)
    assert load_catalog(library_path) == example_entries()


def test_public_projects_have_expected_topologies_and_explicit_porous_inputs():
    projects = {name: load_assembly(ROOT / f"examples/v3_{name}.noiz.json")
                for name in ("single", "double", "quad", "glazing", "porous")}
    assert [len(projects[name].panels) for name in projects] == [1, 2, 4, 2, 1]
    quad = projects["quad"]
    assert len(quad.cavities) == 3
    assert quad.incidence == "normal"
    assert all(cavity.flow_resistivity_pa_s_m2 == 10000 for cavity in quad.cavities)
    assert projects["glazing"].cavities[0].gas == "argon"
    assert projects["porous"].porous.flow_resistivity_pa_s_m2 == 10000
    for project in projects.values():
        assert "sintético" in project.notes
        for panel in project.panels:
            for layer in panel.layers:
                assert layer.catalog_entry.properties["data_status"] == "synthetic"
                assert not layer.catalog_entry.id.startswith("xml:")
    active, variants = load_workspace(ROOT / "examples/v3_workspace.noiz.json")
    assert active == projects["single"]
    assert variants == tuple(projects[name] for name in ("double", "quad", "glazing", "porous"))
