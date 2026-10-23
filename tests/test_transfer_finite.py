"""Independent energy integrals for the finite angular correction.

These verify the documented approximation, not experimental TL accuracy.
"""

import math
from dataclasses import replace

import numpy as np
import pytest
from scipy.integrate import quad

from noiz_transmission.core.finite_panel import FinitePanel
from noiz_transmission.core.transfer import Gap, Plate, narrowband_tau, predict_multilayer


def _exact_band_edges(nominal):
    # IEC base-10 bands: the nominal label 50 corresponds to 50.1187... Hz.
    exponent = {50: -13, 125: -9, 1000: 0}[nominal]
    return 1000 * 10**((exponent - 0.5) / 10), 1000 * 10**((exponent + 0.5) / 10)


@pytest.mark.parametrize("angle", [60, 90])
def test_finite_limp_band_matches_unnormalised_closed_angular_integral(angle):
    mass, width, height, density, speed = 10.0, 1.0, 2.0, 1.21, 343.0
    user_bound = math.sin(math.radians(angle))**2

    def power(frequency):
        # Hansen eq.7.56 and integral of 1/[1 + x² (1-u)] from 0 to uMax.
        cos_squared = min(0.9, speed / frequency * 2 * (width + height)
                          / (8 * math.pi * width * height))
        bound = min(user_bound, 1 - cos_squared)
        x_squared = (math.pi * frequency * mass / (density * speed))**2
        return math.log1p(x_squared * bound / (1 + x_squared * (1 - bound))) / x_squared

    expected = []
    for nominal in (50, 125, 1000):
        lower, upper = _exact_band_edges(nominal)
        energy = quad(power, lower, upper, epsabs=1e-13, epsrel=1e-11)[0]
        expected.append(-10 * math.log10(energy / (upper - lower)))
    actual = predict_multilayer(
        [Plate(mass, finite_size=FinitePanel(width, height))],
        frequencies_hz=[50, 125, 1000], angle_limit_deg=angle,
    )
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-7)


def test_size_changes_diffuse_result_without_changing_normal_incidence():
    small = Plate(10, 400, 0.03, finite_size=FinitePanel(1, 2))
    large = replace(small, finite_size=FinitePanel(10, 20))
    normal_small = predict_multilayer([small], frequencies_hz=[125], incidence="normal")
    normal_large = predict_multilayer([large], frequencies_hz=[125], incidence="normal")
    np.testing.assert_allclose(normal_small, normal_large, rtol=0, atol=1e-12)
    diffuse_small = predict_multilayer([small], frequencies_hz=[125])
    diffuse_large = predict_multilayer([large], frequencies_hz=[125])
    assert diffuse_small[0] > diffuse_large[0] + 1


@pytest.mark.parametrize("leaf_count", [1, 2, 3, 4])
def test_finite_single_to_quad_matches_independent_matrix_energy_integral(leaf_count):
    # Light limp panels and shallow cavities keep this verification below the
    # mass-air-mass modes; no empirical curve or engine function is the oracle.
    masses = tuple(2.0 + index for index in range(leaf_count))
    depth, width, height, density, speed = 0.01, 1.0, 2.0, 1.21, 343.0
    user_bound = math.sin(math.radians(78))**2

    def angular_power(frequency, u):
        cosine = math.sqrt(1 - u)
        medium_impedance = density * speed / cosine
        phase = 2 * math.pi * frequency * depth * cosine / speed
        cavity = np.array([
            [math.cos(phase), 1j * medium_impedance * math.sin(phase)],
            [1j / medium_impedance * math.sin(phase), math.cos(phase)],
        ])
        matrix = np.eye(2, dtype=complex)
        for index, mass in enumerate(masses):
            panel = np.array([[1, 1j * 2 * math.pi * frequency * mass], [0, 1]])
            matrix = matrix @ panel
            if index < leaf_count - 1:
                matrix = matrix @ cavity
        denominator = (matrix[0, 0] + matrix[0, 1] / medium_impedance
                       + matrix[1, 0] * medium_impedance + matrix[1, 1])
        return 4 / abs(denominator)**2

    def frequency_power(frequency):
        cosine_squared = min(0.9, speed * 2 * (width + height)
                             / (frequency * 8 * math.pi * width * height))
        bound = min(user_bound, 1 - cosine_squared)
        return quad(lambda u: angular_power(frequency, u), 0, bound,
                    epsabs=1e-12, epsrel=1e-10)[0]

    lower, upper = _exact_band_edges(50)
    power = quad(frequency_power, lower, upper, epsabs=1e-12, epsrel=1e-10)[0]
    expected = -10 * math.log10(power / (upper - lower))
    plates = tuple(Plate(mass, finite_size=FinitePanel(width, height)) for mass in masses)
    gaps = tuple(Gap(depth) for _ in range(leaf_count - 1))
    actual = predict_multilayer(plates, gaps, frequencies_hz=[50])
    assert actual[0] == pytest.approx(expected, abs=1e-7, rel=0)


def test_edge_loss_changes_bending_response_as_explicit_additional_loss():
    finite_edge = Plate(10, 400, 0.03, finite_size=FinitePanel(2, 3, 0.02))
    finite_total = Plate(10, 400, 0.05, finite_size=FinitePanel(2, 3))
    frequencies = [1000, 2000, 4000]
    np.testing.assert_allclose(
        narrowband_tau(frequencies, [finite_edge], incidence_angle_deg=60),
        narrowband_tau(frequencies, [finite_total], incidence_angle_deg=60), rtol=1e-13,
    )
    # Exercises the frequency-precomputed kernel, as well as narrowband physics.
    np.testing.assert_allclose(
        predict_multilayer([finite_edge], frequencies_hz=[1000]),
        predict_multilayer([finite_total], frequencies_hz=[1000]), rtol=0, atol=1e-10,
    )


def test_mixed_finite_and_infinite_panels_are_rejected_explicitly():
    plates = [Plate(10, finite_size=FinitePanel(2, 3)), Plate(10)]
    with pytest.raises(ValueError, match="[Ff]inite|[Mm]ix"):
        predict_multilayer(plates, [Gap(0.1)], frequencies_hz=[125])
    with pytest.raises(ValueError, match="[Ff]inite|[Mm]ix"):
        narrowband_tau(125, plates, [Gap(0.1)])


def test_invalid_finite_size_does_not_fall_back_to_infinite_panel():
    with pytest.raises(ValueError, match="[Ff]inite"):
        Plate(10, finite_size="2 x 3")
