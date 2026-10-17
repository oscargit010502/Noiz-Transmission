"""V5 interchange coverage uses authored fixtures, never the private product database."""

import hashlib

import pytest

from noiz_transmission.catalog import (
    catalog_references,
    default_catalog_path,
    import_xml,
    load_catalog,
    safe_reference_url,
    save_catalog,
)


def source(tmp_path, body, root="InsulConnections", record="Connection", release="8"):
    path = tmp_path / "synthetic-v5.xml"
    path.write_text(
        f'<{root} xmlns="http://www.insul.co.nz" Version="10.0" Release="{release}">'
        f'<{record}>{body}</{record}></{root}>', encoding="utf-8",
    )
    return path


def test_connection_preserves_distinct_family_dimensions_flags_and_uninterpreted_code(tmp_path):
    path = source(tmp_path, """<Name>Synthetic resilient connection</Name><GUID>example-connection</GUID>
    <Category>MetalFrame</Category><Manufacturer>Example manufacturer</Manufacturer>
    <Properties><Connection>999</Connection><StudDepth>0.095</StudDepth><StudWidth>0.045</StudWidth>
    <MaterialThickness>0.0006</MaterialThickness><CavityWidth>0.13</CavityWidth>
    <useDefinedStudSpacing isSpacingFixed="-1">1</useDefinedStudSpacing>
    <definedStudSpacing>0.4</definedStudSpacing><braceSpacing>0.8</braceSpacing>
    <FrameStiffness>123.4</FrameStiffness><noAbsorption>0</noAbsorption></Properties>""")
    entry, = import_xml(path).entries
    assert entry.kind == "connection"
    assert entry.properties["frame_material"] == "metal"
    assert entry.properties["stud_depth_m"] == 0.095
    assert entry.properties["material_thickness_m"] == 0.0006
    assert entry.properties["cavity_width_m"] == 0.13
    assert entry.properties["defined_stud_spacing_m"] == 0.4
    assert entry.properties["brace_spacing_m"] == 0.8
    assert entry.properties["stud_spacing_defined"] is True
    assert entry.properties["stud_spacing_fixed"] is True
    assert entry.properties["no_absorption_declared"] is False
    assert entry.properties["connection_code"] == 999
    assert "stud_spacing_m" not in entry.properties
    assert entry.properties["units_schema_verified"] is True
    assert entry.properties["structural_model_verified"] is False
    assert entry.properties["geometry_verified"] is False
    assert entry.properties["solid_model_eligible"] is False
    assert entry.raw_fields["Properties/FrameStiffness"] == "123.4"
    assert entry.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    catalog = tmp_path / "catalog.json"
    save_catalog((entry,), catalog)
    assert load_catalog(catalog) == (entry,)


@pytest.mark.parametrize("root,record,body,property_name,expected", [
    ("InsulStud", "Stud", "<Category>MetalFrame</Category><Properties><StudDepth>0.064</StudDepth>"
     "<MaterialThickness>0.00055</MaterialThickness></Properties>", "stud_depth_m", 0.064),
    ("InsulProfiles", "Profile", "<Type>Trapezoidal</Type><Profile><RibL>0.2</RibL>"
     "<RibH>0.035</RibH></Profile>", "Profile/RibL", 0.2),
    ("InsulGlazing", "Glazing", "<Type>Isotropic</Type><SideA><Thickness>0.006</Thickness>"
     "<YoungsModulus>52e9</YoungsModulus></SideA>", "young_modulus_pa", 52e9),
    ("InsulCore", "Material", "<Core><Thickness>0.00038</Thickness></Core>",
     "thickness_m", 0.00038),
])
def test_inspected_10_0_7_units_preserve_si(tmp_path, root, record, body, property_name, expected):
    result = import_xml(source(tmp_path, "<Name>Synthetic dimensions</Name>" + body,
                               root, record, "7"))
    entry, = result.entries
    assert entry.properties["units_schema_verified"] is True
    assert entry.properties[property_name] == expected
    assert not any("revisar unidades" in warning for warning in result.warnings)


def test_references_are_metadata_and_do_not_promote_geometry_or_measurements(tmp_path):
    entry, = import_xml(source(tmp_path, """<Name>Synthetic connection</Name><Remarks>
    <Open>Drawing: https://manufacturer.example/drawings/channel.pdf</Open>
    <Technical>https://manufacturer.example/model.ifc?revision=2&amp;lang=es</Technical>
    <Unsafe>file:///C:/private/part.ifc</Unsafe></Remarks>""")).entries
    references = catalog_references(entry)
    assert [(item.field, item.url) for item in references] == [
        ("Remarks/Open", "https://manufacturer.example/drawings/channel.pdf"),
        ("Remarks/Technical", "https://manufacturer.example/model.ifc?revision=2&lang=es"),
    ]
    assert entry.properties["geometry_verified"] is False
    assert entry.properties["measurement_verified"] is False
    assert entry.raw_fields["Remarks/Unsafe"] == "file:///C:/private/part.ifc"


@pytest.mark.parametrize("url", [
    "file:///C:/drawing.ifc", "javascript:alert(1)", "data:text/html,example",
    "https:///missing-host", "https://user:password@example.com/drawing",
    "https://example.com:99999/drawing", "https://example.com:bad/drawing",
    "https://example.com/\nfile", "https://example.com/<script>",
    "https://example.com\\@other.example/drawing", "https://-bad.example/drawing",
])
def test_unsafe_or_malformed_source_urls_cannot_be_opened(url):
    assert safe_reference_url(url) is None


@pytest.mark.parametrize("url", [
    "https://manufacturer.example/drawing.pdf", "http://manufacturer.example:8080/a?b=2&c=3",
    "https://[2001:db8::1]/model.ifc", "https://fabricación.example/plano.pdf",
])
def test_explicit_web_references_are_accepted(url):
    assert safe_reference_url(url) == url


def test_namespace_and_product_name_are_not_invented_references(tmp_path):
    entry, = import_xml(source(tmp_path, "<Name>Manufacturer Sound Clip</Name>"
                               "<Manufacturer>Example company</Manufacturer>")).entries
    assert catalog_references(entry) == ()


def test_v5_portable_catalog_takes_precedence_without_overwriting_v3(tmp_path, monkeypatch):
    monkeypatch.delenv("NOIZ_CATALOG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "local_data"
    folder.mkdir()
    for name in ("catalog.json", "catalog-v3.json", "catalog-v5.json"):
        (folder / name).write_text(name)
    assert default_catalog_path() == folder / "catalog-v5.json"
    assert (folder / "catalog-v3.json").read_text() == "catalog-v3.json"
    (folder / "catalog-v5.json").unlink()
    assert default_catalog_path() == folder / "catalog-v3.json"

