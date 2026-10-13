"""Versioned materials with explicit provenance, loaded independently of the UI."""

import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import date
from importlib.resources import files
from typing import Any


def finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    """Accept finite real JSON numbers, rejecting booleans and numeric strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} debe ser un número real.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} debe ser finito.") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} debe ser finito" + (" y positivo." if positive else "."))
    return result


def nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} debe ser texto no vacío.")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Campo JSON repetido: {key}.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Constante JSON no finita: {value}.")


def strict_json_loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


@dataclass(frozen=True)
class Material:
    id: str
    name: str
    density_kg_m3: float
    young_modulus_pa: float
    poisson_ratio: float
    region: str
    source: str
    data_status: str
    source_url: str | None
    source_date: str
    license: str
    version: str
    uncertainty: str

    def __post_init__(self) -> None:
        for name in (
            "id", "name", "region", "source", "data_status", "source_date",
            "license", "version", "uncertainty",
        ):
            nonempty_string(getattr(self, name), name)
        if self.data_status not in {"synthetic", "manufacturer", "measured", "literature"}:
            raise ValueError("data_status debe ser synthetic, manufacturer, measured o literature.")
        if self.data_status in {"manufacturer", "measured"} and self.source_url is None:
            raise ValueError("Los datos comerciales o medidos requieren una source_url verificable.")
        finite_number(self.density_kg_m3, "density_kg_m3", positive=True)
        finite_number(self.young_modulus_pa, "young_modulus_pa", positive=True)
        poisson = finite_number(self.poisson_ratio, "poisson_ratio")
        if not -1 < poisson < 0.5:
            raise ValueError("poisson_ratio debe estar entre -1 y 0.5 (excluidos).")
        if self.source_url is not None:
            nonempty_string(self.source_url, "source_url")
            if not self.source_url.startswith(("https://", "http://")):
                raise ValueError("source_url debe usar HTTP o HTTPS.")
        try:
            parsed = date.fromisoformat(self.source_date)
        except ValueError as exc:
            raise ValueError("source_date debe ser una fecha ISO YYYY-MM-DD.") from exc
        if parsed.isoformat() != self.source_date:
            raise ValueError("source_date debe ser una fecha ISO YYYY-MM-DD.")


def material_from_dict(data: Any) -> Material:
    expected = {field.name for field in fields(Material)}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("El material no cumple el esquema de campos requerido.")
    return Material(**data)


def _catalog() -> dict[str, Any]:
    resource = files("noiz_transmission.data").joinpath("materials.json")
    data = strict_json_loads(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "catalog_version", "materials",
    }:
        raise ValueError("Esquema de catálogo inválido.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Versión de catálogo no compatible.")
    nonempty_string(data["catalog_version"], "catalog_version")
    if not isinstance(data["materials"], list):
        raise ValueError("materials debe ser una lista.")
    return data


def catalog_version() -> str:
    return _catalog()["catalog_version"]


def list_materials() -> tuple[Material, ...]:
    """Return reference data; synthetic entries never imply commercial suitability."""
    materials = tuple(material_from_dict(item) for item in _catalog()["materials"])
    if len({item.id for item in materials}) != len(materials):
        raise ValueError("Identificadores de material repetidos en el catálogo.")
    return materials


def material_to_dict(material: Material) -> dict[str, Any]:
    return asdict(material)
