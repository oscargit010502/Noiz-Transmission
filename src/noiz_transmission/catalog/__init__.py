"""User-owned material libraries, independent of the desktop and acoustic solver.

INSUL XML is an interchange source, not evidence of measurement or validation.
Bundled third-party data retains its source attribution; see data/catalog/NOTICE.md.
"""

from .bundled import bundled_entries, load_application_catalog
from .examples import example_entries
from .library import (
    CATALOG_KINDS,
    CatalogEntry,
    CatalogReference,
    CatalogSpectrum,
    ImportResult,
    catalog_references,
    catalog_spectrum,
    default_catalog_path,
    entry_from_dict,
    entry_to_dict,
    import_xml,
    load_catalog,
    merge_catalog,
    safe_reference_url,
    save_catalog,
    search_entries,
)

__all__ = [
    "CATALOG_KINDS", "CatalogEntry", "CatalogReference", "CatalogSpectrum", "ImportResult",
    "bundled_entries", "load_application_catalog", "catalog_references", "catalog_spectrum",
    "default_catalog_path",
    "entry_from_dict", "entry_to_dict", "example_entries", "import_xml", "load_catalog",
    "merge_catalog", "safe_reference_url", "save_catalog", "search_entries",
]
