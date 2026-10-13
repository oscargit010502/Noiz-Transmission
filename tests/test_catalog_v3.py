"""V10 parsing and source-spectrum semantics, using only synthetic XML."""

import hashlib

import pytest

from noiz_transmission.catalog import catalog_spectrum, import_xml, load_catalog, save_catalog


def write_xml(tmp_path, body, root="InsulMaterials", record="Material", version="10.0",
              release="8"):
    path = tmp_path / "synthetic-v10.xml"
    path.write_text(
        f'<{root} xmlns="http://www.insul.co.nz" Version="{version}" Release="{release}">'
        f'<{record}>{body}</{record}></{root}>', encoding="utf-8",
    )
    return path


PANEL = """
<Name>Synthetic panel 10mm</Name><GUID>{synthetic-guid}</GUID><Type>Isotropic</Type>
<SideA><Thickness>0.01</Thickness><Density>800</Density><YoungsModulus>2e9</YoungsModulus>
<Damping>0.01</Damping><PoissonsRatio>0.3</PoissonsRatio><AnisotropicRatio>1</AnisotropicRatio>
<OrthotropicRatio>1</OrthotropicRatio><OrthotropicRatioZY>1</OrthotropicRatioZY></SideA>
<Core><Thickness>0.5</Thickness><Density>2000</Density></Core>
"""


def test_v10_si_properties_guid_and_material_eligibility(tmp_path):
    result = import_xml(write_xml(tmp_path, PANEL))
    entry, = result.entries
    assert entry.original_id == "{synthetic-guid}"
    assert entry.properties["source_guid"] == entry.original_id
    assert entry.properties["thickness_m"] == 0.01
    assert entry.properties["young_modulus_pa"] == 2e9
    assert entry.properties["density_kg_m3"] == 800
    assert entry.properties["units_schema_verified"] is True
    assert entry.properties["solid_model_eligible"] is True
    assert entry.properties["measurement_verified"] is False
    assert catalog_spectrum(entry) is None
    assert not any("revisar unidades" in warning for warning in result.warnings)


def test_future_xml_schema_remains_unverified(tmp_path):
    result = import_xml(write_xml(tmp_path, PANEL, release="99"))
    entry, = result.entries
    assert entry.properties["solid_model_eligible"] is False
    assert entry.properties["units_schema_verified"] is False
    assert any("revisar unidades" in warning for warning in result.warnings)


@pytest.mark.parametrize("category,material", [("MetalFrame", "metal"), ("TimberFrame", "timber")])
def test_stud_dimensions_are_si_and_do_not_define_structural_transmission(
    tmp_path, category, material,
):
    body = f"""<Name>Synthetic stud</Name><Type/><Category>{category}</Category>
    <Properties><StudDepth>0.09</StudDepth><StudWidth>0.04</StudWidth>
    <StudSpacing>0.6</StudSpacing><MaterialThickness>0.0006</MaterialThickness></Properties>"""
    entry, = import_xml(write_xml(tmp_path, body, "InsulStud", "Stud")).entries
    assert entry.properties["stud_depth_m"] == 0.09
    assert entry.properties["stud_width_m"] == 0.04
    assert entry.properties["stud_spacing_m"] == 0.6
    assert entry.properties["material_thickness_m"] == 0.0006
    assert entry.properties["frame_material"] == material
    assert entry.properties["material_type"] == ""
    assert entry.properties["structural_model_verified"] is False
    assert entry.properties["units_schema_verified"] is True
    assert entry.properties["solid_model_eligible"] is False
    assert catalog_spectrum(entry) is None


def test_floor_spectrum_is_delta_l_sorted_not_verified_ln(tmp_path):
    body = """<Name>Synthetic covering</Name><CoverType>LightWeight</CoverType>
    <IsolationGain><Source>Measured</Source><Lab>True</Lab><Data>
    <Hz250>5</Hz250><Hz31.5>-2</Hz31.5><Hz100>3</Hz100>
    </Data></IsolationGain>"""
    entry, = import_xml(write_xml(tmp_path, body, "InsulFloorCover", "FloorCover")).entries
    curve = catalog_spectrum(entry)
    assert curve.frequencies_hz == (31.5, 100, 250)
    assert curve.values_db == (-2, 3, 5)
    assert curve.quantity == "impact_sound_reduction"
    assert curve.unit == "dB"
    assert curve.cover_type == "LightWeight"
    assert curve.lab_claimed is True
    assert curve.verified is False
    assert any("informe" in warning for warning in curve.warnings)
    path = tmp_path / "catalog.json"
    save_catalog((entry,), path)
    assert catalog_spectrum(load_catalog(path)[0]) == curve


def test_spectrum_does_not_interpolate_or_overwrite_duplicates(tmp_path):
    body = """<Name>Synthetic</Name><IsolationGain><Source>XXX</Source><Data>
    <Hz100>2</Hz100><Hz100>5</Hz100><Hz125>NaN</Hz125><Hz160>12</Hz160>
    <Hz200/><Hz250>12</Hz250><Hz315>12</Hz315><Hz315>NaN</Hz315>
    <Hz400>NaN</Hz400><Hz400>12</Hz400><Hz0>10</Hz0><Unknown>15</Unknown>
    </Data></IsolationGain>"""
    entry, = import_xml(write_xml(tmp_path, body, "InsulFloorCover", "FloorCover")).entries
    curve = catalog_spectrum(entry)
    assert curve.frequencies_hz == (160, 250)
    assert curve.values_db == (12, 12)
    assert curve.lab_claimed is False
    assert curve.verified is False
    assert any("repetida" in warning for warning in curve.warnings)
    assert any("constante" in warning for warning in curve.warnings)
    assert entry.raw_fields["IsolationGain/Data/Hz100[1]"] == "2"
    assert entry.raw_fields["IsolationGain/Data/Hz100[2]"] == "5"


def test_legacy_measurement_is_sound_reduction_not_floor_gain(tmp_path):
    body = PANEL + """<Measurement><Source>Example report</Source><Lab>True</Lab>
    <Data><Hz100>10</Hz100><Hz125>15</Hz125></Data></Measurement>"""
    entry, = import_xml(write_xml(tmp_path, body, version="9.0", release="22")).entries
    curve = catalog_spectrum(entry)
    assert curve.quantity == "sound_reduction_index"
    assert curve.values_db == (10, 15)
    assert curve.source == "Example report"
    assert curve.verified is False


def test_illegal_control_recovery_preserves_original_text_hash_and_file(tmp_path):
    body = "<Name>Synthetic \x01name</Name><Properties><Thickness>0.075</Thickness></Properties>"
    path = write_xml(tmp_path, body, "InsulAbsorption", "Absorption")
    original = path.read_bytes()
    result = import_xml(path)
    entry, = result.entries
    assert entry.name == "Synthetic �name"
    assert entry.raw_fields["Name"] == "Synthetic \x01name"
    assert entry.raw_fields["$import/repaired_fields"] == "Name"
    assert entry.source_sha256 == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() == original
    assert any("control XML ilegal" in warning for warning in entry.warnings)
    assert any("controles ilegales" in warning for warning in result.warnings)
    save_catalog((entry,), tmp_path / "catalog.json")
    assert load_catalog(tmp_path / "catalog.json") == (entry,)
    with pytest.raises(ValueError, match="XML inválido"):
        import_xml(path, repair_invalid_controls=False)


@pytest.mark.parametrize("body", [
    "<Na\x01me>Invalid markup</Na\x01me>",
    "<Name>Panel</Name><Properties><Thickness>0.0\x011</Thickness></Properties>",
    '<Name invalid="\x01">Panel</Name>',
    "<Name>Panel</Name>\x01",
    "<Name>Panel</Name><Unknown><Name>Not a product \x01name</Name></Unknown>",
])
def test_name_repair_does_not_repair_markup_properties_or_other_fields(tmp_path, body):
    with pytest.raises(ValueError):
        import_xml(write_xml(tmp_path, body))


def test_recovery_still_rejects_entities_before_processing_names(tmp_path):
    path = tmp_path / "malicious.xml"
    path.write_bytes(
        b'<!DOCTYPE InsulMaterials [<!ENTITY value "bad">]>'
        b'<InsulMaterials><Material><Name>\x01&value;</Name></Material></InsulMaterials>'
    )
    with pytest.raises(ValueError, match="DTD"):
        import_xml(path)
