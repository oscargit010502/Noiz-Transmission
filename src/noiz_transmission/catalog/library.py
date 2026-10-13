"""Lossless field import and strict local persistence for user-supplied XML.

In the inspected INSUL 9.0/22 XML format lengths are metres, density kg/m³,
and Young's modulus Pa (the desktop displays mm and GPa). SideA is the
physical panel only for Isotropic entries. Other material types may contain
several active constituents; their raw fields are retained without inventing
an equivalent homogeneous plate. Absorption/Properties/Damping has no
documented dimension here and is deliberately NOT a structural loss factor.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path

CATALOG_KINDS = (
    "material", "profile", "glazing", "floor_cover", "absorption", "core", "stud",
)
_ROOTS = {
    "InsulMaterials": ("material", "Material"),
    "InsulProfiles": ("profile", "Profile"),
    "InsulGlazing": ("glazing", "Glazing"),
    "InsulFloorCover": ("floor_cover", "FloorCover"),
    "InsulAbsorption": ("absorption", "Absorption"),
    "InsulCore": ("core", "Material"),
    # Generic import support only: no Studs file was supplied for schema verification.
    "InsulStuds": ("stud", "Stud"),
    "InsulStud": ("stud", "Stud"),
}
_MAX_BYTES = 32 * 1024 * 1024
_NUMERIC_FIELDS = frozenset({
    "Density", "YoungsModulus", "Damping", "Thickness", "PoissonsRatio", "Plateau",
    "OrthotropicRatio", "OrthotropicRatioZY", "AnisotropicRatio", "RibL", "RibH",
    "RibW", "RibV", "ElasticModulus", "UnderlayDensity", "UnderlayThickness",
    "UnderlayElasticModulus", "UnderlayDamping", "UnderlayOrthotropicRatio",
    "UnderlayPoissonsRatio", "Colour", "Texture", "UnderlayColour", "UnderlayTexture",
})
_ALIASES = {
    "Density": "density_kg_m3", "Thickness": "thickness_m",
    "YoungsModulus": "young_modulus_pa", "Damping": "loss_factor",
    "PoissonsRatio": "poisson_ratio", "AnisotropicRatio": "anisotropic_ratio",
    "OrthotropicRatio": "orthotropic_ratio", "OrthotropicRatioZY": "orthotropic_ratio_zy",
}
PropertyValue = float | str | bool | None


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    kind: str
    name: str
    category: str
    manufacturer: str
    countries: tuple[str, ...]
    properties: dict[str, PropertyValue]
    raw_fields: dict[str, str]
    source_file: str
    source_sha256: str
    original_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key in ("id", "kind", "name", "category", "manufacturer", "source_file",
                    "source_sha256", "original_id"):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f"{key}: se requiere texto.")
        if not self.id.strip() or not self.name.strip() or self.kind not in CATALOG_KINDS:
            raise ValueError("Identificador, nombre o familia de catálogo inválidos.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("La procedencia requiere un SHA-256 hexadecimal de 64 caracteres.")
        for key in ("countries", "warnings"):
            value = getattr(self, key)
            if not isinstance(value, tuple) or any(not isinstance(v, str) for v in value):
                raise ValueError(f"{key}: se requiere una tupla de textos.")
        if not isinstance(self.raw_fields, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in self.raw_fields.items()
        ):
            raise ValueError("raw_fields debe conservar claves y valores de texto.")
        if not isinstance(self.properties, dict):
            raise ValueError("properties debe ser un objeto.")
        for key, value in self.properties.items():
            if not isinstance(key, str) or type(value) not in (str, float, int, bool, type(None)):
                raise ValueError("Propiedad de catálogo inválida.")
            if type(value) in (int, float):
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("Las propiedades numéricas deben ser finitas.")
        # Break references to caller-owned dictionaries at construction.
        object.__setattr__(self, "properties", dict(self.properties))
        object.__setattr__(self, "raw_fields", dict(self.raw_fields))


@dataclass(frozen=True)
class ImportResult:
    entries: tuple[CatalogEntry, ...]
    warnings: tuple[str, ...]
    source_file: str
    source_sha256: str


class _SafeTreeBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("XML con DTD o entidades no permitido.")

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self.depth += 1
        self.nodes += 1
        if self.depth > 64 or self.nodes > 500_000:
            raise ValueError("XML excede los límites de profundidad o número de elementos.")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self.depth -= 1
        return super().end(tag)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _flatten(element: ET.Element, namespace: str) -> dict[str, str]:
    """Preserve leaves, attributes, repeated nodes and unexpected namespaced fields."""
    result: dict[str, str] = {}

    def name(tag: str) -> str:
        return tag.removeprefix(namespace) if tag.startswith(namespace) else tag

    def walk(node: ET.Element, path: str) -> None:
        for attr, value in node.attrib.items():
            result[f"{path}/@{name(attr)}".lstrip("/")] = value
        if not len(node):
            result[path] = node.text or ""
        elif node.text and node.text.strip():
            result[f"{path}/text()".lstrip("/")] = node.text
        totals = Counter(child.tag for child in node)
        counts: Counter[str] = Counter()
        for child in node:
            counts[child.tag] += 1
            suffix = f"[{counts[child.tag]}]" if totals[child.tag] > 1 else ""
            walk(child, f"{path}/{name(child.tag)}{suffix}".lstrip("/"))

    walk(element, "")
    return result


def _number(text: str, field: str, warnings: list[str]) -> float | None:
    try:
        value = float(text)
    except (ValueError, OverflowError):
        warnings.append(f"{field}: valor numérico vacío o inválido; se conserva el texto original.")
        return None
    if not math.isfinite(value):
        warnings.append(f"{field}: valor no finito; se conserva el texto original.")
        return None
    return value


def _properties(raw: dict[str, str], kind: str, warnings: list[str]) -> dict[str, PropertyValue]:
    props: dict[str, PropertyValue] = {
        "material_type": raw.get("Type", "").strip(),
        "source_version": raw.get("$document/@Version", ""),
        "source_release": raw.get("$document/@Release", ""),
        "measurement_verified": False,
    }
    for path, text in raw.items():
        field = path.rsplit("/", 1)[-1]
        if field in _NUMERIC_FIELDS or re.fullmatch(r"Hz\d+(?:\.\d+)?", field):
            props[path] = _number(text, path, warnings)
    section = {"material": "SideA", "glazing": "SideA", "core": "Core",
               "floor_cover": "Properties", "absorption": "Properties"}.get(kind)
    if section:
        for original, target in _ALIASES.items():
            key = f"{section}/{original}"
            if key in raw:
                if kind == "absorption" and original == "Damping":
                    target = "damping_raw"
                props[target] = props.get(key)
        for key in ("density_kg_m3", "thickness_m", "young_modulus_pa"):
            value = props.get(key)
            if isinstance(value, (int, float)) and value <= 0:
                warnings.append(f"{key}: valor no positivo; no apto para una placa física.")
    props["archived"] = raw.get("Archived", "0").strip() in ("-1", "1", "True", "true")
    props["all_regions"] = raw.get("Region/AllRegions", "0").strip() in (
        "-1", "1", "True", "true",
    )
    source = raw.get("Measurement/Source", raw.get("IsolationGain/Source", "")).strip()
    props["measurement_source"] = source
    if any(p.startswith(("Measurement/", "IsolationGain/")) for p in raw):
        warnings.append(
            "Espectro importado sin verificación documental; no se considera un ensayo validado."
        )
        if source.casefold() in ("", "xxx"):
            warnings.append("La referencia de medición está vacía o contiene el marcador XXX.")
    if kind == "absorption":
        warnings.append(
            "Damping del absorbente se conserva sin asignar resistividad ni factor de pérdidas."
        )
    if kind in ("material", "glazing") and props["material_type"] != "Isotropic":
        warnings.append(
            "Tipo compuesto, perfilado o anisótropo: no sustituir por una placa homogénea SideA."
        )
    if kind == "stud":
        warnings.append("Esquema Stud no verificado; conservar campos para revisión manual.")
    positive = all(type(props.get(k)) in (float, int) and props[k] > 0
                   for k in ("density_kg_m3", "thickness_m", "young_modulus_pa"))
    poisson = props.get("poisson_ratio")
    loss = props.get("loss_factor")
    if kind in ("material", "glazing"):
        if type(poisson) in (float, int) and not -1 < poisson < 0.5:
            warnings.append("Poisson fuera del intervalo físico (-1, 0.5).")
        if type(loss) in (float, int) and loss < 0:
            warnings.append("Factor de pérdidas negativo; no apto para cálculo.")
        if any(props.get(k, 1) != 1 for k in (
            "anisotropic_ratio", "orthotropic_ratio", "orthotropic_ratio_zy",
        )):
            warnings.append("Razón anisótropa distinta de 1; revisar antes del modelo isótropo.")
    props["units_schema_verified"] = (
        props["source_version"] == "9.0" and props["source_release"] == "22"
    )
    props["solid_model_eligible"] = bool(
        kind in ("material", "glazing") and props["material_type"] == "Isotropic"
        and raw.get("Name", "").strip() and props["units_schema_verified"]
        and positive and type(poisson) in (float, int) and -1 < poisson < 0.5
        and type(loss) in (float, int) and loss >= 0
        and all(props.get(k, 1) == 1 for k in (
            "anisotropic_ratio", "orthotropic_ratio", "orthotropic_ratio_zy",
        ))
    )
    return props


def import_xml(path: str | Path) -> ImportResult:
    """Import each record, including blank-name/duplicate rows, retaining provenance.

    Record IDs are file-content hash + ordinal, because the supplied format has
    no explicit IDs. An XML extension, its namespace, or Lab=True does not make
    any entry scientifically verified. Unsupported roots fail explicitly.
    """
    path = Path(path)
    with path.open("rb") as stream:
        data = stream.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("El XML supera el límite de 32 MiB.")
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc
    root_name = _local(root.tag)
    if root_name not in _ROOTS:
        raise ValueError(f"Familia XML no reconocida: {root_name}.")
    kind, record_tag = _ROOTS[root_name]
    namespace = root.tag.removesuffix(root_name)
    if namespace not in ("", "{http://www.insul.co.nz}"):
        raise ValueError("Namespace XML no reconocido.")
    if any(child.tag != f"{namespace}{record_tag}" for child in root):
        raise ValueError(f"Se esperaba un registro {record_tag} dentro de {root_name}.")
    sha256 = hashlib.sha256(data).hexdigest()
    source_file = path.name
    entries = []
    names = Counter((child.findtext(f"{namespace}Name") or "").strip() for child in root)
    for index, node in enumerate(root, 1):
        raw = _flatten(node, namespace)
        raw.update({f"$document/@{k}": v for k, v in root.attrib.items()})
        raw["$document/root"] = root_name
        raw["$document/namespace"] = namespace.strip("{}")
        warnings: list[str] = []
        original_id = raw.get("@ID", raw.get("ID", f"{record_tag}[{index}]"))
        label = raw.get("Name", "").strip()
        if not label:
            warnings.append("Nombre vacío en el origen; registro conservado con su ordinal.")
        if names[label] > 1:
            warnings.append("Nombre repetido en el archivo; se conserva como registro independiente.")
        name = label or f"Sin nombre · {record_tag} {index}"
        countries = []
        for key, text in raw.items():
            if key.startswith("Region/") and key not in ("Region/Custom", "Region/AllRegions"):
                if text.strip() in ("-1", "1", "True", "true"):
                    countries.append(key.removeprefix("Region/"))
                elif text.strip() not in ("0", "False", "false", ""):
                    warnings.append(f"{key}: bandera regional desconocida {text!r}.")
        properties = _properties(raw, kind, warnings)
        entries.append(CatalogEntry(
            id=f"xml:{sha256}:{index}", kind=kind, name=name,
            category=raw.get("Category", "").strip(),
            manufacturer=raw.get("Manufacturer", "").strip(), countries=tuple(countries),
            properties=properties, raw_fields=raw, source_file=source_file,
            source_sha256=sha256, original_id=original_id, warnings=tuple(warnings),
        ))
    summary = [
        "Datos del usuario; importación no equivale a validación científica ni licencia de redistribución."
    ]
    if root.attrib.get("Version") != "9.0" or root.attrib.get("Release") != "22":
        summary.append("Versión XML distinta del esquema inspeccionado 9.0/22; revisar unidades.")
    if not entries:
        summary.append("Archivo válido sin registros.")
    summary.append(f"{sum(bool(entry.warnings) for entry in entries)} registros con observaciones.")
    return ImportResult(tuple(entries), tuple(summary), source_file, sha256)


def entry_to_dict(entry: CatalogEntry) -> dict:
    """JSON snapshot with independent mutable containers."""
    return {
        field.name: (dict(value) if isinstance(value, dict)
                     else list(value) if isinstance(value, tuple) else value)
        for field in fields(CatalogEntry)
        for value in (getattr(entry, field.name),)
    }


def entry_from_dict(data: dict) -> CatalogEntry:
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(CatalogEntry)}:
        raise ValueError("Esquema de registro de catálogo inválido.")
    copied = dict(data)
    for key in ("countries", "warnings"):
        if not isinstance(data[key], list):
            raise ValueError(f"{key}: se requiere una lista JSON.")
        copied[key] = tuple(data[key])
    return CatalogEntry(**copied)


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clave JSON repetida: {key}.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Número JSON no finito: {value}.")


def load_catalog(path: str | Path) -> tuple[CatalogEntry, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    with path.open("rb") as stream:
        data = stream.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("El catálogo supera el límite de 32 MiB.")
    try:
        content = json.loads(data, object_pairs_hook=_strict_object, parse_constant=_invalid_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Catálogo JSON inválido: {exc}") from exc
    if (not isinstance(content, dict) or set(content) != {"schema_version", "entries"}
            or type(content["schema_version"]) is not int or content["schema_version"] != 1
            or not isinstance(content["entries"], list)):
        raise ValueError("Esquema o versión del catálogo no admitidos.")
    entries = tuple(entry_from_dict(value) for value in content["entries"])
    if len({e.id for e in entries}) != len(entries):
        raise ValueError("El catálogo contiene identificadores repetidos.")
    return entries


def save_catalog(entries: Iterable[CatalogEntry], path: str | Path) -> None:
    """Replace atomically: failed serialization leaves the existing library intact."""
    entries = tuple(entries)
    if any(not isinstance(entry, CatalogEntry) for entry in entries):
        raise ValueError("Todos los elementos deben ser registros del catálogo.")
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError("El catálogo contiene identificadores repetidos.")
    # Revalidate snapshots because the frozen dataclass contains mutable dictionaries.
    snapshots = [entry_to_dict(entry) for entry in entries]
    for snapshot in snapshots:
        entry_from_dict(snapshot)
    data = json.dumps({"schema_version": 1, "entries": snapshots}, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > _MAX_BYTES:
        raise ValueError("El catálogo supera el límite de 32 MiB.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def merge_catalog(existing: Iterable[CatalogEntry], incoming: Iterable[CatalogEntry]
                  ) -> tuple[CatalogEntry, ...]:
    """Idempotent file reimport; preserve different rows even if names coincide."""
    merged = {entry.id: entry for entry in existing}
    for entry in incoming:
        merged[entry.id] = entry
    return tuple(merged.values())


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def search_entries(entries: Iterable[CatalogEntry], query: str = "", kind: str | None = None,
                   category: str | None = None, manufacturer: str | None = None,
                   country: str | None = None) -> tuple[CatalogEntry, ...]:
    words = _fold(query).split()
    result = []
    for entry in entries:
        if any(value is not None and _fold(value) != _fold(getattr(entry, key))
               for key, value in (("kind", kind), ("category", category),
                                  ("manufacturer", manufacturer))):
            continue
        if country is not None and not entry.properties.get("all_regions", False):
            if _fold(country) not in {_fold(c) for c in entry.countries}:
                continue
        haystack = _fold(" ".join((entry.name, entry.category, entry.manufacturer,
                                    *entry.countries)))
        if all(word in haystack for word in words):
            result.append(entry)
    return tuple(result)


def default_catalog_path() -> Path:
    """User library location, overridable for portable installations and tests."""
    if configured := os.environ.get("NOIZ_CATALOG_PATH"):
        return Path(configured).expanduser()
    portable = Path.cwd() / "local_data" / "catalog.json"
    if portable.is_file():
        return portable
    # A source checkout can be launched from elsewhere. Never search above an
    # installed site-packages location: that might capture another environment's data.
    module = Path(__file__).resolve()
    if module.parent.name == "catalog" and module.parents[1].name == "noiz_transmission":
        source = module.parents[2]
        checkout = source.parent
        if source.name == "src" and (checkout / "pyproject.toml").is_file():
            portable = checkout / "local_data" / "catalog.json"
            if portable.is_file():
                return portable
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return root / "NoizTransmission" / "catalog.json"
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "noiz-transmission" / "catalog.json"
