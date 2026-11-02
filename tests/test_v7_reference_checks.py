"""Independent numerical substitutions in published equations, not accuracy claims.

Expected constants below were evaluated separately from the production module
after inspecting the rendered Hansen 6e pages 383, 435 and 436. The sigma values
supplied to the connection equations deliberately exercise the three critical-
frequency branches; they are not a fitted commercial partition spectrum.
"""

import math

import numpy as np
import pytest

from noiz_transmission.core.davy import (
    DavyStud,
    davy_double_bands,
    davy_radiation_efficiency,
    line_connection_tau,
    point_connection_tau,
    resonant_radiation_efficiency,
    steel_compliance,
)
from noiz_transmission.core.transfer import Plate


def test_hansen_6_91_forced_radiation_independent_numeric_substitution():
    # a=2A/P=1 m; this chooses ka directly, isolating transcription errors in H.
    ka = np.array([0.5, 1.0, 5.0, 20.0])
    frequency = ka * 343 / (2 * math.pi)
    sigma = davy_radiation_efficiency(frequency, area_m2=2, perimeter_m=4)
    assert sigma == pytest.approx(
        [0.127668825251222, 0.32906217638894364,
         1.1944117273381907, 1.917004733300831], rel=1e-12,
    )
    # Radiation efficiency is not a power transmission coefficient.
    assert sigma[-1] > 1


def test_hansen_4_181_resonant_radiation_omits_invalid_corner_term():
    # 2*f11 < f < fc: no fitted transition or coincidence cap is involved.
    sigma = resonant_radiation_efficiency(
        [100, 500, 1000, 2000], critical_frequency_hz=2700, first_mode_hz=40,
        width_m=2.4, height_m=2.7, perimeter_m=31.8,
    )
    assert sigma == pytest.approx(
        [0.01270429497291857, 0.03458378273319559,
         0.06659883237166656, 0.28629476092249445], rel=1e-12,
    )
    # A subcritical mechanically excited leaf must not acquire the much larger
    # forced-acoustic radiation ratio through the stale chapter cross-reference.
    forced = davy_radiation_efficiency([100, 500, 1000, 2000], 6.48, 31.8)
    assert np.all(sigma < forced)


def test_hansen_4_180_low_mode_piston_radiation():
    sigma = resonant_radiation_efficiency(
        [10], critical_frequency_hz=2700, first_mode_hz=40,
        width_m=2.4, height_m=2.7, perimeter_m=31.8,
    )
    assert sigma == pytest.approx([0.022031636477998114], rel=1e-12)


@pytest.mark.parametrize("compliance,expected", [
    (0, [0.03566087302768942, 0.0004382175761443159, 0.00005404072627930267]),
    (5e-7, [0.017994202855720513, 0.000044551597890522486, 0.0000021155153075410186]),
])
def test_hansen_7_93_point_path_independent_numeric_substitution(compliance, expected):
    actual = point_connection_tau(
        [500, 1500, 2500], mass1=10, mass2=15, fc1=1000, fc2=2000,
        eta1=.03, eta2=.04, sigma1=.5, sigma2=.75,
        point_density_m2=1 / (.6 * .25), compliance_m_n=compliance,
        air_density=1.2, sound_speed=340,
    )
    assert actual == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("compliance,expected", [
    (0, [0.01447262398752453, 0.000512411695995004, 0.00010132126847438919]),
    (2e-7, [0.005308618410673402, 0.0000044395089793904535, 0.0000001775164086257922]),
])
def test_hansen_7_95_line_path_independent_numeric_substitution(compliance, expected):
    actual = line_connection_tau(
        [500, 1500, 2500], mass1=10, mass2=15, fc1=1000, fc2=2000,
        eta1=.03, eta2=.04, sigma1=.5, sigma2=.75,
        spacing_m=.6, compliance_m2_n=compliance,
        air_density=1.2, sound_speed=340,
    )
    assert actual == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("attachment,expected", [
    ("point", [0.0000047361818117096474, 0.0000002745630681203754]),
    ("line", [0.0000023959431227009813, 0.00000010343583568891556]),
])
def test_hansen_table_7_8_two_frequency_branches(attachment, expected):
    # g=20 is a declared regression coordinate. This checks arithmetic only;
    # it does not assert that g=20 maps to any particular metal thickness.
    actual = steel_compliance(
        [125, 1000], mass1=10, mass2=15, spacing_m=.6,
        fastener_spacing_m=.25, steel_gauge=20, area_m2=6.48,
        attachment=attachment,
    )
    assert actual == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("path,connection", [
    (point_connection_tau, {"point_density_m2": 5, "compliance_m_n": 3e-7}),
    (line_connection_tau, {"spacing_m": .6, "compliance_m2_n": 1e-7}),
])
def test_connection_path_reciprocity_under_swapping_leaves(path, connection):
    values = dict(mass1=9, mass2=14, fc1=1800, fc2=2900,
                  eta1=.02, eta2=.05, sigma1=.03, sigma2=.06)
    original = path([250, 1000, 2000, 3150], **values, **connection)
    swapped = {f"{name}{index}": values[f"{name}{3 - index}"]
               for name in ("mass", "fc", "eta", "sigma") for index in (1, 2)}
    reverse = path([250, 1000, 2000, 3150], **swapped, **connection)
    assert original == pytest.approx(reverse, rel=1e-13)


def test_point_path_scales_with_connection_density_when_radiation_is_fixed():
    parameters = dict(mass1=10, mass2=15, fc1=1000, fc2=2000,
                      eta1=.03, eta2=.04, sigma1=.05, sigma2=.07,
                      compliance_m_n=5e-7)
    sparse = point_connection_tau([500, 1000, 2000], point_density_m2=4, **parameters)
    dense = point_connection_tau([500, 1000, 2000], point_density_m2=8, **parameters)
    assert dense == pytest.approx(2 * sparse, rel=1e-13)
    assert -10 * np.log10(sparse) + 10 * np.log10(dense) == pytest.approx(
        np.full(3, 3.010299956639812), rel=1e-13,
    )


def test_hansen_adjusted_double_resonance_against_coupled_eigenproblem():
    first, second = Plate(10, 434, .03), Plate(15, 900, .04)
    stud = DavyStud(kind="timber", spacing_m=.6, fastener_spacing_m=.3)
    depth, rho, speed = .1, 1.21, 343.
    result = davy_double_bands(first, second, depth, width_m=2.4, height_m=2.7,
                               stud=stud, frequencies_hz=[500, 1000],
                               air_density=rho, sound_speed=speed)
    masses = np.array([10., 15.])
    first_modes = np.pi / (2 * .6**2) * np.sqrt(np.array([434., 900.]) / masses)
    air_spring = rho * speed**2 / depth
    # A separate mass-normalised two-oscillator stiffness eigenproblem,
    # not the quadratic-root expression used by the production model.
    stiffness = np.diag((2 * np.pi * first_modes)**2)
    stiffness += air_spring * np.array([
        [1 / masses[0], -1 / np.sqrt(masses.prod())],
        [-1 / np.sqrt(masses.prod()), 1 / masses[1]],
    ])
    frequencies = np.sqrt(np.linalg.eigvalsh(stiffness)) / (2 * np.pi)
    assert result.resonance_hz == pytest.approx(frequencies[-1], rel=1e-13)


def test_realistic_path_order_and_energy_bookkeeping_without_accuracy_claim():
    panel = Plate(10, 434, .03)
    options = dict(width_m=2.4, height_m=2.7, frequencies_hz=[500, 1000, 2000, 4000],
                   absorber_thickness_m=.075, ideal_absorber=True)
    independent = davy_double_bands(panel, panel, .1, **options)
    timber = davy_double_bands(panel, panel, .1, stud=DavyStud(kind="timber"), **options)
    steel = davy_double_bands(
        panel, panel, .1,
        stud=DavyStud(kind="steel", attachment="point", point_compliance_m_n=1e-5),
        **options,
    )
    # Added structural transmission cannot improve the airborne-only result.
    assert np.all(np.array(timber.tl_db) < np.array(independent.tl_db))
    assert np.all(np.array(steel.tl_db) < np.array(independent.tl_db))
    assert np.all(np.array(steel.tl_db) > np.array(timber.tl_db))
    for result in (independent, timber, steel):
        tau = np.array(result.airborne_tau) + np.array(result.studborne_tau)
        assert 10 ** (-np.array(result.tl_db) / 10) == pytest.approx(tau, rel=1e-13)
        assert np.all((tau > 0) & (tau < 1))
