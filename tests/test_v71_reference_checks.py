"""Independent Sharp design inversions and conservation checks for V7.1.

These cases test published arithmetic, dimensional behavior and bookkeeping;
they do not claim a measured error margin for a commercial construction.
Sharp (1978), pp. 61–63, equations 23–26 and the worked 58 dB design example.
"""

import math

import numpy as np
import pytest

from noiz_transmission.core.automatic import automatic_double_bands, sharp_bridge_tl
from noiz_transmission.core.transfer import Plate


@pytest.mark.parametrize("connection,total_mass", [
    ("point", 29.01417149115317),
    ("line", 64.01843996644799),
])
def test_sharp_design_example_inverted_from_required_performance(connection, total_mass):
    # Masses were independently obtained from design eqs.25 and26 for TLs=58,
    # f=1000, fc=4000 and e/b=.61. The production routine evaluates forward
    # eqs.23/24. Its 0.0206 dB difference from58 is rounding of99 and72 there.
    actual = sharp_bridge_tl(
        [1000], total_mass / 2, total_mass / 2, 4000, 4000,
        spacing_m=.61, connection=connection,
    )
    assert actual == pytest.approx([57.97940008672036], abs=1e-10)
    assert actual[0] == pytest.approx(58, abs=.021)


def test_sharp_figure12_structural_asymptote_uses_mass_of_other_leaf():
    # p61 Figure12:15.9/9.5mm gypsum, b=.61m. Nominal masses/fc are discussed
    # onpp62–63. This tests the published asymptote, NOT the measured curve:
    # the source doesn't give all conditions needed to reproduce that test.
    actual = sharp_bridge_tl(
        [250, 500, 1000, 1250], 12.6, 7.3, 2500, 4000,
        spacing_m=.61, connection="line",
    )
    assert actual == pytest.approx(
        [37.84010933917929, 43.86070925245892, 49.88130916573854, 51.819509425899696],
        abs=1e-10,
    )


@pytest.mark.parametrize("fc1,fc2", [(2500, 4000), (4000, 2500), (3000, 3000)])
def test_line_leaf_order_does_not_choose_a_different_source_mass(fc1, fc2):
    forward = sharp_bridge_tl([250, 500, 1000], 12.6, 7.3, fc1, fc2,
                             spacing_m=.61, connection="line")
    reverse = sharp_bridge_tl([250, 500, 1000], 7.3, 12.6, fc2, fc1,
                             spacing_m=.61, connection="line")
    assert forward == pytest.approx(reverse, abs=1e-12)


def test_point_contact_follows_its_physical_leaf_when_reversing_partition():
    # Eq23 uses fc of the point-supported leaf, not simply the greater fc.
    forward = sharp_bridge_tl([250, 500, 1000], 12.6, 7.3, 2500, 4000,
                             spacing_m=.61, connection="point", point_supported_panel=1)
    reverse = sharp_bridge_tl([250, 500, 1000], 7.3, 12.6, 4000, 2500,
                             spacing_m=.61, connection="point", point_supported_panel=2)
    assert forward == pytest.approx(reverse, abs=1e-12)


def test_two_point_supported_leaves_match_impedance_equations_not_one_side_shortcut():
    # Equations17,20,22 with c343 give point impedances599.181 and561.733
    # N s/m, K=-2.21397dB. This is not the one-sided approximation23.
    forward = sharp_bridge_tl([250, 500, 1000], 10, 15, 2500, 4000,
                             spacing_m=.61, connection="point_pair")
    reverse = sharp_bridge_tl([250, 500, 1000], 15, 10, 4000, 2500,
                             spacing_m=.61, connection="point_pair")
    assert forward == pytest.approx(reverse, abs=1e-12)
    assert forward == pytest.approx(
        [48.45143092378231, 54.47203083706192, 60.49263075034155], abs=1e-10,
    )


@pytest.mark.parametrize("connection,expected_db", [
    ("point", 6.020599913279624), ("point_pair", 6.020599913279624),
    ("line", 3.010299956639812),
])
def test_connection_spacing_change_matches_number_of_transmission_paths(connection, expected_db):
    # Doubling lattice spacing quarters point density; doubling line spacing
    # halves line density. These are different geometric dimensions.
    args = ([500, 1000], 10, 10, 3000, 3000)
    dense = sharp_bridge_tl(*args, spacing_m=.3, connection=connection)
    sparse = sharp_bridge_tl(*args, spacing_m=.6, connection=connection)
    assert sparse - dense == pytest.approx([expected_db, expected_db], abs=1e-12)


def test_automatic_resonance_matches_two_masses_and_physical_air_spring():
    masses = np.array([10., 15.])
    depth, rho, c = .1, 1.21, 343.
    result = automatic_double_bands(
        Plate(masses[0], 434, .03), Plate(masses[1], 900, .04), depth,
        width_m=2.4, height_m=2.7, bridge="line", stud_spacing_m=.6,
        absorber_thickness_m=.05, flow_resistivity_pa_s_m2=20000,
        frequencies_hz=[250, 500, 1000],
        air_density=rho, sound_speed=c,
    )
    spring = rho * c**2 / depth
    # Independent eigenproblem, not the analytic resonance expression.
    matrix = spring * np.array([[1 / masses[0], -1 / np.sqrt(masses.prod())],
                                [-1 / np.sqrt(masses.prod()), 1 / masses[1]]])
    expected = math.sqrt(np.linalg.eigvalsh(matrix)[-1]) / (2 * math.pi)
    assert result.resonance_hz == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("bridge", ["none", "line", "point", "point_pair"])
def test_automatic_total_is_energy_sum_and_passive_for_regular_wall(bridge):
    result = automatic_double_bands(
        Plate(10, 434, .03), Plate(15, 900, .04), .1,
        width_m=2.4, height_m=2.7, bridge=bridge, stud_spacing_m=.6,
        point_spacing_m=.6, absorber_thickness_m=.05, flow_resistivity_pa_s_m2=20000,
    )
    airborne, structural = np.asarray(result.airborne_tau), np.asarray(result.studborne_tau)
    total = np.power(10., -np.asarray(result.tl_db) / 10)
    assert total == pytest.approx(airborne + structural, rel=1e-12)
    assert np.all((total > 0) & (total <= 1))
    assert np.all(airborne > 0)
    assert np.all(structural >= 0)
    if bridge == "none":
        assert np.all(structural == 0)


def test_filled_and_empty_cavity_do_not_receive_the_same_ideal_airborne_curve():
    args = (Plate(10, 434, .03), Plate(15, 900, .04), .1)
    options = dict(width_m=2.4, height_m=2.7, bridge="none",
                   frequencies_hz=[500, 1000, 2000])
    empty = automatic_double_bands(*args, absorber_thickness_m=0, **options)
    filled = automatic_double_bands(*args, absorber_thickness_m=.05,
                                   flow_resistivity_pa_s_m2=20000, **options)
    assert np.all(np.asarray(filled.tl_db) > np.asarray(empty.tl_db))
