"""Combined-model boundaries and invariants, independent of frame UI defaults."""

import math
from threading import Event

import numpy as np
import pytest

from noiz_transmission.core.automatic import automatic_double_bands, sharp_bridge_tl
from noiz_transmission.core.davy import DavyStud, davy_double_bands
from noiz_transmission.core.transfer import Plate


@pytest.fixture
def plates():
    # Physically different leaves exercise ordering/reciprocity.
    return Plate(8.5, 300., .03), Plate(12., 700., .04)


def options(**extra):
    return {"width_m": 2.4, "height_m": 2.7,
            "absorber_thickness_m": .04, "flow_resistivity_pa_s_m2": 20000., **extra}


def resonance(plates, depth=.1):
    m1, m2 = (p.mass_kg_m2 for p in plates)
    return math.sqrt(1.21 * 343**2 * (m1 + m2) / (4 * math.pi**2 * depth * m1 * m2))


def test_independent_route_preserves_existing_airborne_solution(plates):
    new = automatic_double_bands(*plates, .1, bridge="none", **options())
    old = davy_double_bands(*plates, .1, stud=DavyStud(kind="independent"),
                            minimum_background_absorption=.1, **options())
    assert new.tl_db == pytest.approx(old.tl_db, rel=1e-13)
    assert not any(new.studborne_tau)


@pytest.mark.parametrize("bridge", ["line", "point", "point_pair"])
def test_low_frequency_mass_path_is_not_counted_twice(plates, bridge):
    f0 = resonance(plates)
    frequencies = np.asarray([f0 / 4, f0 / 2, 2 * f0 / 3])
    result = automatic_double_bands(*plates, .1, bridge=bridge,
                                    **options(frequencies_hz=frequencies))
    air_only = automatic_double_bands(*plates, .1, bridge="none",
                                      **options(frequencies_hz=frequencies))
    assert result.tl_db == pytest.approx(air_only.tl_db, abs=1e-10)
    assert result.studborne_tau == (0., 0., 0.)


@pytest.mark.parametrize("bridge", ["line", "point", "point_pair"])
def test_transition_is_continuous_at_both_join_frequencies(plates, bridge):
    f0 = resonance(plates)
    for join in (2 * f0 / 3, f0):
        frequencies = join * np.asarray([1 - 1e-8, 1., 1 + 1e-8])
        result = automatic_double_bands(*plates, .1, bridge=bridge,
                                       **options(frequencies_hz=frequencies))
        assert max(result.tl_db) - min(result.tl_db) < 1e-5


@pytest.mark.parametrize("bridge", ["line", "point_pair"])
def test_complete_prediction_is_reciprocal_for_symmetric_contact_types(plates, bridge):
    forward = automatic_double_bands(*plates, .1, bridge=bridge, **options())
    backward = automatic_double_bands(*plates[::-1], .1, bridge=bridge, **options())
    assert forward.tl_db == pytest.approx(backward.tl_db, abs=1e-12)


def test_point_on_one_leaf_follows_physical_leaf_when_reversed(plates):
    first = automatic_double_bands(*plates, .1, bridge="point",
                                  point_supported_panel=1, **options())
    reverse = automatic_double_bands(*plates[::-1], .1, bridge="point",
                                    point_supported_panel=2, **options())
    assert first.tl_db == pytest.approx(reverse.tl_db, abs=1e-12)


def test_fill_thickness_has_no_discontinuous_switch_at_50_mm(plates):
    cases = [automatic_double_bands(*plates, .1, bridge="line",
                                   **options(absorber_thickness_m=t)).tl_db
             for t in (.049999, .05, .050001)]
    assert np.max(np.abs(np.asarray(cases[2]) - cases[0])) < .002


def test_thin_fill_limit_recovers_empty_background_without_changing_legacy(plates):
    empty = automatic_double_bands(*plates, .1, **options(absorber_thickness_m=0.,
                                                         flow_resistivity_pa_s_m2=None))
    thin = automatic_double_bands(*plates, .1, **options(absorber_thickness_m=1e-5))
    assert thin.tl_db == pytest.approx(empty.tl_db, abs=1e-8)
    legacy = davy_double_bands(*plates, .1, stud=DavyStud(kind="independent"),
                               **options(absorber_thickness_m=.04))
    auto_air = automatic_double_bands(*plates, .1, bridge="none", **options())
    assert np.all(np.asarray(auto_air.tl_db) >= np.asarray(legacy.tl_db) - 1e-10)
    assert any("α=min(kd,max" in item for item in auto_air.warnings)
    assert not any("α=min(kd,max" in item for item in legacy.warnings)


def test_adding_rigid_bridge_never_improves_air_only_spectrum(plates):
    independent = np.asarray(automatic_double_bands(*plates, .1, bridge="none", **options()).tl_db)
    bridged = np.asarray(automatic_double_bands(*plates, .1, bridge="line", **options()).tl_db)
    assert np.all(bridged <= independent + 1e-12)


def test_point_pair_path_uses_full_reciprocal_impedance_expression():
    # Two identical point impedances give K=0 in Sharp 22. This is not
    # Sharp 23, whose single-point / opposite-line approximation has K=-6.02.
    f = np.asarray([125., 1000., 4000.])
    expected = 20 * np.log10(20 * f) - 48 + 20 * math.log10(.6 * 2000) - 45
    assert sharp_bridge_tl(f, 10, 10, 2000, 2000, spacing_m=.6,
                           connection="point_pair") == pytest.approx(expected)


def test_generic_fill_requires_resolved_reference_or_measured_resistivity(plates):
    with pytest.raises(ValueError, match="flow resistivity"):
        automatic_double_bands(*plates, .1, **options(flow_resistivity_pa_s_m2=None))


def test_cancelled_calculation_stops_before_work(plates):
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        automatic_double_bands(*plates, .1, **options(cancel_event=event))


@pytest.mark.parametrize("field,value", [("bridge", "flexible-brand"),
                                        ("stud_spacing_m", 0), ("point_spacing_m", float("nan")),
                                        ("point_supported_panel", 0),
                                        ("point_supported_panel", True)])
def test_invalid_connection_inputs_are_not_silently_defaulted(plates, field, value):
    with pytest.raises(ValueError):
        automatic_double_bands(*plates, .1, **options(**{field: value}))
