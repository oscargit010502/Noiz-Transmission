"""Davy path composition, physical input boundaries and numerical behaviour."""

from dataclasses import replace
from threading import Event

import numpy as np
import pytest

from noiz_transmission.core.davy import (
    DavyStud,
    davy_double_bands,
    davy_single_bands,
    davy_single_reference_bands,
    resonant_radiation_efficiency,
    studborne_tau,
)
from noiz_transmission.core.finite_panel import FinitePanel
from noiz_transmission.core.transfer import Plate, predict_multilayer


@pytest.fixture
def leaf():
    return Plate(10., 434., .03)


def double(leaf, stud=DavyStud(), **kwargs):
    return davy_double_bands(leaf, leaf, .1, width_m=2.4, height_m=2.7, stud=stud,
                             absorber_thickness_m=.075, ideal_absorber=True, **kwargs)


def test_double_reports_actual_power_paths_and_timber_limits_isolated_wall(leaf):
    isolated = double(leaf)
    timber = double(leaf, DavyStud("timber"))
    assert np.all(np.asarray(isolated.studborne_tau) == 0)
    selected = np.asarray(timber.frequencies_hz) > 200
    assert np.all(np.asarray(timber.studborne_tau)[selected] > 0)
    assert np.all(np.asarray(timber.tl_db)[selected] < np.asarray(isolated.tl_db)[selected])
    for result in (isolated, timber):
        np.testing.assert_allclose(
            10**(-np.asarray(result.tl_db) / 10),
            np.asarray(result.airborne_tau) + np.asarray(result.studborne_tau), rtol=2e-14,
        )


def test_common_wall_is_reciprocal_when_leaves_are_reversed(leaf):
    other = Plate(19., 2700., .04)
    stud = DavyStud("steel", point_compliance_m_n=1e-6)
    parameters = dict(width_m=2.4, height_m=2.7, stud=stud, cavity_absorption=.6)
    first = davy_double_bands(leaf, other, .1, **parameters)
    reverse = davy_double_bands(other, leaf, .1, **parameters)
    np.testing.assert_allclose(first.tl_db, reverse.tl_db, atol=2e-13)
    assert first.resonance_hz == pytest.approx(reverse.resonance_hz)


def test_resonance_has_published_equal_leaf_bending_contribution(leaf):
    result = double(leaf, DavyStud("timber", spacing_m=.6))
    f_bending = np.pi / (2 * .6**2) * np.sqrt(434 / 10)
    f_air2 = 1.21 * 343**2 / (.1 * 10) / (2 * np.pi)**2
    assert result.resonance_hz == pytest.approx(np.sqrt(2 * f_air2 + f_bending**2))


def test_absorption_changes_air_path_without_modifying_stud_path(leaf):
    settings = dict(width_m=2.4, height_m=2.7, stud=DavyStud("timber"))
    weak = davy_double_bands(leaf, leaf, .1, cavity_absorption=.1, **settings)
    good = davy_double_bands(leaf, leaf, .1, cavity_absorption=.8, **settings)
    above = np.asarray(weak.frequencies_hz) >= 100
    assert np.all(np.asarray(good.airborne_tau)[above] < np.asarray(weak.airborne_tau)[above])
    np.testing.assert_allclose(np.asarray(weak.studborne_tau)[above], np.asarray(good.studborne_tau)[above])


def test_increasing_point_compliance_reduces_structural_path(leaf):
    kwargs = dict(width_m=2.4, height_m=2.7)
    stiff = DavyStud("steel", attachment="point", point_compliance_m_n=0)
    flexible = replace(stiff, point_compliance_m_n=1e-5)
    f = np.array([125., 500., 2000.])
    assert np.all(studborne_tau(f, leaf, leaf, flexible, **kwargs)
                  < studborne_tau(f, leaf, leaf, stiff, **kwargs))


def test_manual_point_and_line_compliance_have_consistent_declared_conversion(leaf):
    point = DavyStud("steel", attachment="line", point_compliance_m_n=1e-6,
                    fastener_spacing_m=.3)
    line = replace(point, point_compliance_m_n=None, line_compliance_m2_n=3e-7)
    np.testing.assert_allclose(double(leaf, point).tl_db, double(leaf, line).tl_db)


def test_steel_without_a_mechanical_input_is_not_silently_rigid():
    with pytest.raises(ValueError, match="explicit connection compliance"):
        DavyStud("steel")
    with pytest.raises(ValueError, match="point connections"):
        DavyStud("timber", attachment="line")


def test_thin_fill_needs_documented_absorption_or_resistivity(leaf):
    with pytest.raises(ValueError, match="requires cavity absorption"):
        davy_double_bands(leaf, leaf, .1, width_m=2.4, height_m=2.7,
                          absorber_thickness_m=.04)
    with pytest.raises(ValueError, match="at least 50 mm"):
        davy_double_bands(leaf, leaf, .1, width_m=2.4, height_m=2.7,
                          absorber_thickness_m=.04, ideal_absorber=True)
    result = davy_double_bands(leaf, leaf, .1, width_m=2.4, height_m=2.7,
                               absorber_thickness_m=.04, flow_resistivity_pa_s_m2=12000)
    assert np.all(np.isfinite(result.tl_db))
    assert any("Miki" in warning for warning in result.warnings)


def test_extra_edge_loss_is_used_exactly_once(leaf):
    extra = replace(leaf, finite_size=FinitePanel(2.4, 2.7, .02))
    equivalent = replace(leaf, loss_factor=.05)
    np.testing.assert_allclose(double(extra).tl_db, double(equivalent).tl_db)
    parameters = dict(width_m=2.4, height_m=2.7)
    np.testing.assert_allclose(davy_single_bands(extra, **parameters).tl_db,
                               davy_single_bands(equivalent, **parameters).tl_db)


def test_resonant_radiation_is_finite_at_coincidence():
    sigma = resonant_radiation_efficiency([2499.99, 2500., 2500.01], 2500, 25,
                                         width_m=2.4, height_m=2.7, perimeter_m=31.8)
    np.testing.assert_allclose(sigma, 10**.5)


def test_single_stiffness_region_has_opposite_slope_to_mass_law():
    heavy = Plate(480., 2.5e7, .03)
    result = davy_single_reference_bands(heavy, width_m=1, height_m=1, frequencies_hz=[20, 40])
    assert result.tl_db[1] - result.tl_db[0] == pytest.approx(-20 * np.log10(2))


def test_cancellation_and_invalid_physical_inputs(leaf):
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        double(leaf, cancel_event=event)
    for bad in (-1., 0., np.nan, np.inf, True):
        with pytest.raises(ValueError):
            davy_single_bands(leaf, width_m=bad, height_m=2.7)
    with pytest.raises(ValueError, match="loss factor"):
        double(Plate(10, 434, 0))


def test_empirical_gauge_assumption_is_visible(leaf):
    result = double(leaf, DavyStud("steel", steel_gauge=25))
    assert any("convención de gauge" in warning for warning in result.warnings)
    assert any("NO está verificada" in warning for warning in result.warnings)


def test_single_retains_verified_finite_band_energy_integration(leaf):
    result = davy_single_bands(leaf, width_m=2.4, height_m=2.7, angle_limit_deg=75)
    expected = predict_multilayer((replace(leaf, finite_size=FinitePanel(2.4, 2.7)),),
                                  angle_limit_deg=75)
    np.testing.assert_allclose(result.tl_db, expected, atol=1e-13)


def test_homogeneous_thickness_cap_does_not_increase_insulation():
    plate = Plate(1200., 3.25e8, .02)
    parameters = dict(width_m=2.4, height_m=2.7, frequencies_hz=[1600., 2500., 5000.])
    thin = davy_single_bands(plate, **parameters)
    thick = davy_single_bands(plate, **parameters, thickness_m=.5, longitudinal_speed_m_s=3535.)
    assert thick.tl_db[0] == pytest.approx(thin.tl_db[0])
    cap = 20 * np.log10(1200 * 3535 / (4 * 1.21 * 343 * .5)) + 10 * np.log10(.02) + 17
    assert np.all(np.asarray(thick.tl_db)[1:] <= cap + 1e-12)
    assert np.all(np.asarray(thick.tl_db) <= np.asarray(thin.tl_db) + 1e-12)


def test_double_rejects_overlapping_resonance_and_coincidence_regimes():
    thick = Plate(480, 2.5e7, .03)
    with pytest.raises(ValueError, match="fuera del orden de regímenes"):
        double(thick, DavyStud("timber", spacing_m=.1))
