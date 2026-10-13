"""Catalog validation protects units and provenance before solving a project."""

from dataclasses import asdict, replace

import pytest

from noiz_transmission.application.materials import (
    catalog_version,
    list_materials,
    material_from_dict,
    strict_json_loads,
)


def test_bundled_examples_are_explicitly_synthetic_and_have_provenance():
    materials = list_materials()
    assert len(materials) == 3
    assert len({material.id for material in materials}) == len(materials)
    assert catalog_version() == "2026.10-synthetic-1"
    for material in materials:
        assert material.data_status == "synthetic"
        assert material.source_url is None
        assert material.source and material.uncertainty and material.license
        assert material_from_dict(asdict(material)) == material


@pytest.mark.parametrize("field,value", [
    ("density_kg_m3", 0),
    ("density_kg_m3", -1),
    ("density_kg_m3", True),
    ("density_kg_m3", "800"),
    ("density_kg_m3", float("nan")),
    ("young_modulus_pa", float("inf")),
    ("young_modulus_pa", 0),
    ("poisson_ratio", -1),
    ("poisson_ratio", 0.5),
    ("name", " "),
    ("source", None),
    ("data_status", "commercial-verified"),
    ("data_status", "manufacturer"),
    ("data_status", "measured"),
    ("source_url", "javascript:alert(1)"),
    ("source_date", "2026-99-01"),
    ("source_date", "20261013"),
])
def test_invalid_material_properties_are_rejected(field, value):
    with pytest.raises(ValueError):
        replace(list_materials()[0], **{field: value})


def test_material_schema_rejects_missing_or_unrecognized_fields():
    data = asdict(list_materials()[0])
    data["undocumented_property"] = 1
    with pytest.raises(ValueError, match="esquema"):
        material_from_dict(data)
    del data["undocumented_property"]
    del data["uncertainty"]
    with pytest.raises(ValueError, match="esquema"):
        material_from_dict(data)


def test_printed_literature_can_be_cited_without_a_web_url():
    material = replace(
        list_materials()[0], data_status="literature", source="Author, Title, 2020, p. 34",
    )
    assert material.source_url is None


def test_manufacturer_data_requires_a_url():
    material = replace(
        list_materials()[0], data_status="manufacturer", source_url="https://example.org/data.pdf",
    )
    assert material.data_status == "manufacturer"


@pytest.mark.parametrize("text", [
    '{"density": 1, "density": 2}',
    '{"value": NaN}',
    '{"value": Infinity}',
    '{"value": -Infinity}',
])
def test_strict_json_rejects_ambiguous_or_nonfinite_data(text):
    with pytest.raises(ValueError):
        strict_json_loads(text)
