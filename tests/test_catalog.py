"""Import integrity uses original synthetic XML, never the uploaded database."""

from dataclasses import replace
from pathlib import Path

import pytest

from noiz_transmission.catalog import (
    default_catalog_path,
    entry_from_dict,
    entry_to_dict,
    import_xml,
    load_catalog,
    merge_catalog,
    save_catalog,
    search_entries,
)


def xml_file(tmp_path, body, root="InsulMaterials", record="Material", encoding="utf-8"):
    text = (f'<{root} xmlns="http://www.insul.co.nz" Version="9.0" Release="22">'
            f'<{record}>{body}</{record}></{root}>')
    path = tmp_path / "synthetic.xml"
    path.write_bytes(text.encode(encoding))
    return path


PANEL = """
<Name>Panel sintético</Name><Type>Isotropic</Type><Category>Gypsum</Category>
<Manufacturer>Autor del ejemplo</Manufacturer>
<Region><Custom>-1</Custom><AllRegions>0</AllRegions><Spain>-1</Spain><USA>0</USA></Region>
<SideA><Density>800</Density><Thickness>0.0125</Thickness>
<YoungsModulus>2e9</YoungsModulus><Damping>0.01</Damping><PoissonsRatio>0.3</PoissonsRatio>
<OrthotropicRatio>1</OrthotropicRatio><AnisotropicRatio>1</AnisotropicRatio></SideA>
<Core><Thickness>0.1</Thickness><Density>10000</Density></Core>
<Measurement><Source>XXX</Source><Lab>True</Lab><Data><Hz100>10</Hz100></Data></Measurement>
"""


def test_si_properties_and_raw_fields_not_gui_units_or_residual_core(tmp_path):
    path = xml_file(tmp_path, PANEL)
    result = import_xml(path)
    entry, = result.entries
    assert entry.kind == "material"
    assert entry.properties["density_kg_m3"] == 800
    assert entry.properties["thickness_m"] == 0.0125
    assert entry.properties["young_modulus_pa"] == 2e9
    assert entry.properties["poisson_ratio"] == 0.3
    assert entry.properties["solid_model_eligible"] is True
    assert entry.raw_fields["SideA/YoungsModulus"] == "2e9"
    assert entry.raw_fields["Core/Thickness"] == "0.1"
    assert entry.raw_fields["$document/@Release"] == "22"
    assert entry.properties["measurement_verified"] is False
    assert entry.original_id == "Material[1]"
    assert entry.countries == ("Spain",)
    assert entry.source_file == path.name
    assert len(entry.source_sha256) == 64
    assert any("XXX" in warning for warning in entry.warnings)


def test_deterministic_ids_idempotent_import_and_content_change(tmp_path):
    path = xml_file(tmp_path, PANEL)
    a = import_xml(path).entries
    assert merge_catalog(a, import_xml(path).entries) == a
    changed = xml_file(tmp_path, PANEL.replace("800", "810"))
    b = import_xml(changed).entries
    assert a[0].id != b[0].id
    assert len(merge_catalog(a, b)) == 2


def test_duplicate_and_blank_names_are_retained_as_different_records(tmp_path):
    body = PANEL + "</Material><Material>" + PANEL + "</Material><Material><Name/>"
    entries = import_xml(xml_file(tmp_path, body)).entries
    assert len(entries) == len({e.id for e in entries}) == 3
    assert entries[0].name == entries[1].name
    assert "Sin nombre" in entries[2].name
    assert entries[2].raw_fields["Name"] == ""


def test_repeated_and_namespaced_extension_fields_and_attributes_survive(tmp_path):
    entry, = import_xml(xml_file(tmp_path, PANEL + """
        <Extension label="a"><Value>  original  </Value><Value>second</Value></Extension>
        <other:Name xmlns:other="https://example.invalid/schema">extension</other:Name>
    """)).entries
    assert entry.raw_fields["Extension/@label"] == "a"
    assert entry.raw_fields["Extension/Value[1]"] == "  original  "
    assert entry.raw_fields["Extension/Value[2]"] == "second"
    assert entry.raw_fields["{https://example.invalid/schema}Name"] == "extension"


@pytest.mark.parametrize("root,record,kind", [
    ("InsulMaterials", "Material", "material"),
    ("InsulGlazing", "Glazing", "glazing"),
    ("InsulCore", "Material", "core"),
    ("InsulProfiles", "Profile", "profile"),
    ("InsulFloorCover", "FloorCover", "floor_cover"),
    ("InsulAbsorption", "Absorption", "absorption"),
    ("InsulStuds", "Stud", "stud"),
])
def test_root_defines_family_not_filename_or_shared_record_tag(tmp_path, root, record, kind):
    entry, = import_xml(xml_file(tmp_path, PANEL, root, record)).entries
    assert entry.kind == kind


def test_core_uses_core_properties_and_absorption_keeps_ambiguous_damping(tmp_path):
    core, = import_xml(xml_file(tmp_path, PANEL, "InsulCore")).entries
    assert core.properties["density_kg_m3"] == 10000
    assert core.properties["solid_model_eligible"] is False
    absorption, = import_xml(xml_file(tmp_path, """
        <Name>Absorbente sintético</Name><Properties><Density>30</Density>
        <Thickness>0.075</Thickness><YoungsModulus/><Damping>15000</Damping></Properties>
    """, "InsulAbsorption", "Absorption")).entries
    assert absorption.properties["damping_raw"] == 15000
    assert "loss_factor" not in absorption.properties
    assert "flow_resistivity_pa_s_m2" not in absorption.properties
    assert absorption.properties["young_modulus_pa"] is None
    assert absorption.raw_fields["Properties/YoungsModulus"] == ""


@pytest.mark.parametrize("old,new", [
    ("Isotropic", "ElasticCore"), ("Isotropic", "Orthotropic"),
    ("<Density>800</Density>", "<Density>0</Density>"),
    ("<Damping>0.01</Damping>", "<Damping>-0.01</Damping>"),
    ("<PoissonsRatio>0.3</PoissonsRatio>", "<PoissonsRatio>0.5</PoissonsRatio>"),
    ("<AnisotropicRatio>1</AnisotropicRatio>", "<AnisotropicRatio>0.2</AnisotropicRatio>"),
])
def test_ineligible_panel_not_silently_approved(tmp_path, old, new):
    entry, = import_xml(xml_file(tmp_path, PANEL.replace(old, new))).entries
    assert entry.properties["solid_model_eligible"] is False


@pytest.mark.parametrize("value", ["", "no disponible", "NaN", "1e999", "1,23"])
def test_invalid_numeric_values_preserved_and_warned(tmp_path, value):
    text = PANEL.replace("<Density>800</Density>", f"<Density>{value}</Density>")
    entry, = import_xml(xml_file(tmp_path, text)).entries
    assert entry.raw_fields["SideA/Density"] == value
    assert entry.properties["density_kg_m3"] is None
    assert entry.properties["solid_model_eligible"] is False
    assert any("SideA/Density" in warning for warning in entry.warnings)


def test_search_combines_unicode_words_exact_facets_and_region_flags(tmp_path):
    first, = import_xml(xml_file(tmp_path, PANEL)).entries
    second = replace(first, id="example-2", manufacturer="Other", countries=("USA",))
    assert search_entries((first, second), "sintetico autor", country="spain") == (first,)
    assert search_entries((first, second), category="gypsum", manufacturer="other") == (second,)
    assert not search_entries((first, second), kind="profile")
    global_entry = replace(first, properties={**first.properties, "all_regions": True})
    assert search_entries((global_entry,), country="Colombia") == (global_entry,)


def test_catalog_and_project_snapshot_roundtrip(tmp_path):
    entries = import_xml(xml_file(tmp_path, PANEL)).entries
    path = tmp_path / "user_library" / "catalog.json"
    assert load_catalog(path) == ()
    save_catalog(entries, path)
    assert load_catalog(path) == entries
    assert entry_from_dict(entry_to_dict(entries[0])) == entries[0]
    assert not tuple(path.parent.glob(".catalog.json.*"))


@pytest.mark.parametrize("json_text", [
    '{"schema_version":1,"schema_version":1,"entries":[]}',
    '{"schema_version":true,"entries":[]}',
    '{"schema_version":2,"entries":[]}',
    '{"schema_version":1,"entries":[],"unknown":null}',
    '{"schema_version":1,"entries":[NaN]}',
])
def test_library_strict_json_rejects_ambiguous_data(tmp_path, json_text):
    path = tmp_path / "library.json"
    path.write_text(json_text)
    with pytest.raises(ValueError):
        load_catalog(path)


def test_save_duplicate_ids_and_invalid_mutated_property_preserves_existing(tmp_path):
    entry, = import_xml(xml_file(tmp_path, PANEL)).entries
    path = tmp_path / "library.json"
    save_catalog((entry,), path)
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="repetidos"):
        save_catalog((entry, entry), path)
    entry.properties["density_kg_m3"] = float("nan")
    with pytest.raises(ValueError):
        save_catalog((entry,), path)
    assert path.read_bytes() == previous


@pytest.mark.parametrize("field,value", [
    ("source_sha256", ""), ("kind", "unknown"), ("countries", "Spain"),
    ("name", ""), ("properties", []), ("raw_fields", {"density": 10}),
    ("properties", {"bad": [1, 2]}), ("properties", {"bad": float("inf")}),
])
def test_strict_entry_snapshot(tmp_path, field, value):
    entry, = import_xml(xml_file(tmp_path, PANEL)).entries
    snapshot = entry_to_dict(entry)
    snapshot[field] = value
    with pytest.raises(ValueError):
        entry_from_dict(snapshot)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_dtd_and_external_entity_rejected_even_with_unicode_encodings(tmp_path, encoding):
    path = tmp_path / "untrusted.xml"
    payload = ('<!DOCTYPE InsulMaterials [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'
               '<InsulMaterials><Material><Name>&leak;</Name></Material></InsulMaterials>')
    path.write_bytes(payload.encode(encoding))
    with pytest.raises(ValueError):
        import_xml(path)


@pytest.mark.parametrize("payload", [
    "<Unknown/>", "<InsulMaterials><Glazing/></InsulMaterials>",
    '<InsulMaterials xmlns="https://unrecognized.invalid"/>',
    '<InsulMaterials>' + '<Deep>' * 70 + '</Deep>' * 70 + '</InsulMaterials>',
])
def test_unknown_or_excessively_deep_xml_rejected(tmp_path, payload):
    path = tmp_path / "bad.xml"
    path.write_text(payload)
    with pytest.raises(ValueError):
        import_xml(path)


def test_utf8_bom_supported(tmp_path):
    path = xml_file(tmp_path, PANEL, encoding="utf-8-sig")
    assert import_xml(path).entries[0].name == "Panel sintético"


def test_default_path_can_point_to_local_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "local_data" / "catalog.json"))
    assert default_catalog_path() == Path(tmp_path / "local_data" / "catalog.json")


def test_portable_catalog_precedence_and_no_directory_creation(monkeypatch, tmp_path):
    import noiz_transmission.catalog.library as library

    monkeypatch.delenv("NOIZ_CATALOG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    # Simulate a wheel installation, which must not search its ancestor directories.
    wheel = tmp_path / ".venv/lib/python3.13/site-packages/noiz_transmission/catalog/library.py"
    monkeypatch.setattr(library, "__file__", str(wheel))
    local = tmp_path / "user_data"
    monkeypatch.setenv("XDG_DATA_HOME", str(local))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    user_default = default_catalog_path()
    assert user_default.parent.parent == local
    assert not local.exists()
    portable = tmp_path / "local_data" / "catalog.json"
    portable.parent.mkdir()
    portable.write_text('{"schema_version":1,"entries":[]}')
    assert default_catalog_path() == portable
    override = tmp_path / "override.json"
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(override))
    assert default_catalog_path() == override
    assert not override.exists()


def test_checkout_fallback_requires_source_layout_and_existing_file(monkeypatch, tmp_path):
    import noiz_transmission.catalog.library as library

    monkeypatch.delenv("NOIZ_CATALOG_PATH", raising=False)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    checkout = tmp_path / "checkout"
    source = checkout / "src/noiz_transmission/catalog/library.py"
    source.parent.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]")
    portable = checkout / "local_data/catalog.json"
    portable.parent.mkdir()
    portable.write_text('{"schema_version":1,"entries":[]}')
    monkeypatch.setattr(library, "__file__", str(source))
    assert default_catalog_path() == portable
    portable.unlink()
    assert default_catalog_path() != portable
    assert not portable.exists()
