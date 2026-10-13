"""Small MIT reference library available when the user has no local catalogue.

These are declared synthetic values for learning the editor and checking the
solver. They are not commercial products or laboratory measurements. The source
hashes refer to the exact bundled JSON bytes, including the declared defaults.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from importlib.resources import files

from noiz_transmission.application.materials import list_materials

from .library import CatalogEntry


def example_entries() -> tuple[CatalogEntry, ...]:
    """Return detached synthetic entries; never create or replace a user library."""
    resources = files("noiz_transmission.data")
    material_bytes = resources.joinpath("materials.json").read_bytes()
    defaults_bytes = resources.joinpath("example_catalog.json").read_bytes()
    defaults = json.loads(defaults_bytes)
    material_hash = hashlib.sha256(material_bytes).hexdigest()
    defaults_hash = hashlib.sha256(defaults_bytes).hexdigest()
    entries = []
    for material in list_materials():
        example = defaults["plate_defaults"][material.id]
        raw = {key: json.dumps(value, ensure_ascii=False) for key, value in asdict(material).items()}
        raw.update({
            "Example/defaults_file": "example_catalog.json",
            "Example/defaults_sha256": defaults_hash,
            "Example/thickness_m": str(example["thickness_m"]),
            "Example/loss_factor": str(example["loss_factor"]),
            "Example/source": defaults["source"],
        })
        entries.append(CatalogEntry(
            id=f"noiz-example:{material.id}",
            kind="glazing" if material.id == "synthetic-glazing-panel" else "material",
            name=material.name, category="Referencia sintética", manufacturer="Sin fabricante",
            countries=("Internacional",),
            properties={
                "density_kg_m3": material.density_kg_m3,
                "young_modulus_pa": material.young_modulus_pa,
                "poisson_ratio": material.poisson_ratio,
                "thickness_m": example["thickness_m"], "loss_factor": example["loss_factor"],
                "material_type": "Isotropic", "solid_model_eligible": True,
                "anisotropic_ratio": 1.0, "orthotropic_ratio": 1.0,
                "units_schema_verified": True, "measurement_verified": False,
                "data_status": "synthetic", "license": "MIT",
                "source_version": "1", "source_release": "public-synthetic",
            },
            raw_fields=raw, source_file="materials.json", source_sha256=material_hash,
            original_id=material.id,
            warnings=("Datos sintéticos públicos MIT: no caracterizan ningún producto comercial.",
                      "Espesor y amortiguamiento son hipótesis declaradas en example_catalog.json."),
        ))
    absorption = defaults["absorption"]
    entries.append(CatalogEntry(
        id=f"noiz-example:{absorption['id']}", kind="absorption", name=absorption["name"],
        category="Referencia sintética", manufacturer="Sin fabricante", countries=("Internacional",),
        properties={
            "thickness_m": absorption["thickness_m"], "density_kg_m3": absorption["density_kg_m3"],
            "solid_model_eligible": False, "measurement_verified": False,
            "units_schema_verified": True, "data_status": "synthetic", "license": "MIT",
        },
        raw_fields={"Source": defaults["source"], "License": "MIT",
                    **{key: str(value) for key, value in absorption.items()}},
        source_file="example_catalog.json", source_sha256=defaults_hash,
        original_id=absorption["id"], warnings=(defaults["source"], absorption["note"]),
    ))
    return tuple(entries)
