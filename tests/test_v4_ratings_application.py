"""Rating selection must classify the spectrum without relabelling Rw."""

import csv
import json
from dataclasses import replace

import pytest

from noiz_transmission.application.assemblies import AssemblyPrediction
from noiz_transmission.application.assembly_services import (
    default_project_v3,
    export_assembly_csv,
    export_assembly_html,
    predict_assembly,
    project_from_dict,
    project_to_dict,
    save_assembly,
)
from noiz_transmission.core.ratings import STC_PROCEDURE
from noiz_transmission.core.transfer import NOMINAL_BANDS_HZ


@pytest.fixture
def notched_prediction():
    project = default_project_v3()
    spectrum = tuple(10. if f == 125 else 80. for f in NOMINAL_BANDS_HZ)
    return AssemblyPrediction(project, tuple(NOMINAL_BANDS_HZ), spectrum,
                              58, 10, 12.5, (), (), ())


def test_stc_is_computed_from_curve_and_differs_from_rw(notched_prediction):
    assert notched_prediction.stc_db == 34
    assert notched_prediction.rw_db == 58
    assert replace(notched_prediction, rw_db=99).stc_db == 34


@pytest.mark.parametrize("change", [{"incidence": "normal"}, {"excitation": "impact"},
                                     {"excitation": "rainfall"}])
def test_normal_and_non_airborne_results_have_no_stc(notched_prediction, change):
    project = replace(notched_prediction.project, **change)
    assert replace(notched_prediction, project=project).stc_db is None


def test_predict_assembly_exposes_stc_and_method_scope(monkeypatch, notched_prediction):
    monkeypatch.setattr("noiz_transmission.application.assembly_services.predict_multilayer",
                        lambda *args, **kwargs: notched_prediction.tl_db)
    result = predict_assembly(notched_prediction.project)
    assert result.rw_db == 58
    assert result.stc_db == 34
    assert any("STC orientativo" in item and "32/8" in item for item in result.warnings)


def test_reports_retain_rating_and_procedure(notched_prediction, tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "report.html"
    export_assembly_csv([notched_prediction], csv_path)
    export_assembly_html([notched_prediction], html_path)
    with csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["stc_illustrative"] == "34"
    assert rows[0]["stc_procedure"] == STC_PROCEDURE
    assert rows[0]["rw_db_illustrative"] == "58"
    html = html_path.read_text(encoding="utf-8")
    assert "STC: 34" in html
    assert "legado 32/8" in html
    assert STC_PROCEDURE in html


def test_new_computed_rating_does_not_change_project_schema(notched_prediction, tmp_path):
    data = project_to_dict(notched_prediction.project)
    assert "stc_db" not in data
    assert project_from_dict(data) == notched_prediction.project
    path = tmp_path / "project.noiz.json"
    save_assembly(notched_prediction.project, path)
    assert json.loads(path.read_text())["schema_version"] == 4
