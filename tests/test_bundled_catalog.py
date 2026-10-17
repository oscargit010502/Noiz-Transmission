"""A fresh distribution starts with the supplied library, without an import step."""

import hashlib
import json
import os
from collections import Counter
from dataclasses import replace
from importlib.resources import files

import pytest

from noiz_transmission.catalog import (
    bundled_entries,
    example_entries,
    load_application_catalog,
    load_catalog,
    save_catalog,
)


def test_shipped_library_contains_all_eight_sources_with_provenance():
    entries = bundled_entries()
    assert dict(Counter(entry.kind for entry in entries)) == {
        "material": 1575, "absorption": 523, "connection": 387, "floor_cover": 669,
        "glazing": 80, "stud": 69, "profile": 281, "core": 45,
    }
    assert len({entry.id for entry in entries}) == 3629
    manifest = json.loads(files("noiz_transmission.data").joinpath("catalog/manifest.json").read_text())
    for source in manifest["sources"]:
        matching = [entry for entry in entries if entry.source_file == source["filename"]]
        assert len(matching) == source["entry_count"]
        assert all(entry.source_sha256 == source["sha256"] for entry in matching)
        assert all(entry.raw_fields and entry.original_id for entry in matching)
    entries[0].properties["test_mutation"] = True
    assert "test_mutation" not in bundled_entries()[0].properties


def test_normal_startup_preserves_user_library_and_no_duplicate_base(tmp_path, monkeypatch):
    import noiz_transmission.catalog.bundled as module

    monkeypatch.delenv("NOIZ_CATALOG_PATH", raising=False)
    library = tmp_path / "user.json"
    monkeypatch.setattr(module, "default_catalog_path", lambda: library)
    assert len(load_application_catalog()) == 3629
    assert not library.exists()  # Opening does not create or modify user files.
    base = bundled_entries()
    modified = replace(base[0], name="Nombre conservado del usuario")
    custom = example_entries()[0]
    save_catalog((modified, custom), library)
    original = library.read_bytes()
    combined = load_application_catalog()
    assert len(combined) == 3630
    assert next(entry for entry in combined if entry.id == modified.id) == modified
    assert library.read_bytes() == original
    save_catalog(combined, library)
    assert load_application_catalog() == combined
    assert len(load_catalog(library)) == 3630


def test_explicit_override_still_selects_an_isolated_library(tmp_path, monkeypatch):
    library = tmp_path / "chosen.json"
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(library))
    assert load_application_catalog() == example_entries()
    chosen = example_entries()[:1]
    save_catalog(chosen, library)
    assert load_application_catalog() == chosen


def test_fresh_desktop_has_native_catalogue_without_writing_installation(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    import noiz_transmission.catalog.bundled as module
    from noiz_transmission.ui.main_window import MainWindow

    monkeypatch.delenv("NOIZ_CATALOG_PATH", raising=False)
    library = tmp_path / "user.json"
    monkeypatch.setattr(module, "default_catalog_path", lambda: library)
    resource = files("noiz_transmission.data").joinpath("catalog/catalog-v5.json.gz")
    before = hashlib.sha256(resource.read_bytes()).hexdigest()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        assert len(window.entries) == 3629
        assert window.material_picker.products_list.count() > 1500
        window.topology_tabs.setCurrentIndex(1)
        window.part_tabs.setCurrentIndex(1)
        assert window.stud_picker.products_list.count() == 456
        assert window.absorber_picker.products_list.count() == 523
        assert not library.exists()
        assert hashlib.sha256(resource.read_bytes()).hexdigest() == before
    finally:
        window._confirm_discard = lambda: True
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
