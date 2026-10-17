"""Read the distributed catalogue without writing into the installation folder."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from importlib.resources import files

from .examples import example_entries
from .library import (
    _MAX_BYTES,
    CatalogEntry,
    decode_catalog,
    default_catalog_path,
    load_catalog,
    merge_catalog,
)


def bundled_entries() -> tuple[CatalogEntry, ...]:
    """Return detached source snapshots; an incomplete distribution fails explicitly."""
    resources = files("noiz_transmission.data").joinpath("catalog")
    manifest = json.loads(resources.joinpath("manifest.json").read_text(encoding="utf-8"))
    with resources.joinpath("catalog-v5.json.gz").open("rb") as raw:
        with gzip.GzipFile(fileobj=raw) as stream:
            data = stream.read(_MAX_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != manifest["catalog_sha256"]:
        raise ValueError("El catálogo integrado está dañado. Vuelve a instalar Noiz Transmission.")
    entries = decode_catalog(data)
    if len(entries) != manifest["entry_count"]:
        raise ValueError("El catálogo integrado está incompleto.")
    return entries


def load_application_catalog() -> tuple[CatalogEntry, ...]:
    """Combine shipped entries and user entries without overwriting either source.

    A deliberate NOIZ_CATALOG_PATH override selects an isolated library, preserving
    portable custom workflows and tests. Normal startup always includes the base.
    User snapshots win on identical IDs; reimporting a bundled XML is idempotent.
    """
    user_entries = load_catalog(default_catalog_path())
    if os.environ.get("NOIZ_CATALOG_PATH"):
        return user_entries or example_entries()
    return merge_catalog(bundled_entries(), user_entries)
