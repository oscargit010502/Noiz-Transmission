"""Mathematical verification; these are not experimental validation cases."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad

from noiz_transmission.core import physics
from noiz_transmission.core.physics import (
    THIRD_OCTAVE_NOMINAL_HZ,
    critical_frequency,
    mass_air_mass_resonance,
    mass_law_diffuse_tl,
    mass_law_normal_tl,
    surface_density,
    tau_to_tl,
    tl_to_tau,
)

_ANALYTICAL_CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "validation" / "cases.json").read_text(
        encoding="utf-8",
    )
)["cases"]


@pytest.mark.parametrize("case", _ANALYTICAL_CASES, ids=lambda case: case["id"])
def test_published_analytical_validation_case(case):
    result = getattr(physics, case["function"])(**case["inputs"])
    assert result == pytest.approx(case["expected"], abs=case["absolute_tolerance"], rel=0)


def test_surface_density_uses_si_units():
    assert surface_density(2400, 0.1) == 240
    assert surface_density(800, 0.0125) == 10


def test_normal_incidence_known_impedance_match_and_array_shape():
    # x = π f m'/(ρc) = 1 gives exactly half of the incident power transmitted.
    frequency = 1.21 * 343 / (math.pi * 10)
    result = mass_law_normal_tl(frequency, 10)
    assert isinstance(result, np.ndarray)
    assert result.shape == ()
    assert result == pytest.approx(10 * math.log10(2), rel=1e-14)
    shaped = mass_law_normal_tl([[frequency, 2 * frequency]], 10)
    assert shaped.shape == (1, 2)


def test_mass_frequency_equivalence_and_high_frequency_slope():
    frequencies = THIRD_OCTAVE_NOMINAL_HZ
    np.testing.assert_allclose(
        mass_law_normal_tl(2 * frequencies, 10), mass_law_normal_tl(frequencies, 20),
    )
    difference = mass_law_normal_tl(2e6, 20) - mass_law_normal_tl(1e6, 20)
    assert difference == pytest.approx(20 * math.log10(2), abs=1e-9)


@pytest.mark.parametrize("angle", [15.0, 60.0, 78.0, 90.0])
def test_diffuse_model_matches_independent_energy_quadrature(angle):
    angle_rad = math.radians(angle)
    frequencies = np.array([0.001, 20, 100, 1000, 10000], dtype=float)
    expected = []
    for frequency in frequencies:
        x = math.pi * frequency * 15 / (1.21 * 343)
        integral, _ = quad(
            lambda theta: 2 * math.sin(theta) * math.cos(theta)
            / (1 + (x * math.cos(theta)) ** 2),
            0, angle_rad, epsabs=1e-14, epsrel=1e-12,
        )
        expected.append(-10 * math.log10(integral / math.sin(angle_rad) ** 2))
    np.testing.assert_allclose(
        mass_law_diffuse_tl(frequencies, 15, limiting_angle_deg=angle),
        expected, rtol=1e-11, atol=1e-12,
    )


def test_full_hemisphere_known_half_impedance_case():
    frequency = 1.21 * 343 / (math.pi * 10)
    assert mass_law_diffuse_tl(frequency, 10, limiting_angle_deg=90) == pytest.approx(
        -10 * math.log10(math.log(2)), rel=1e-14,
    )


def test_diffuse_average_normalization_and_small_angle_limit():
    frequencies = THIRD_OCTAVE_NOMINAL_HZ
    np.testing.assert_allclose(
        mass_law_diffuse_tl(frequencies, 10, limiting_angle_deg=1e-5),
        mass_law_normal_tl(frequencies, 10), rtol=1e-12,
    )
    for angle in [10, 78, 90]:
        result = mass_law_diffuse_tl(1e-9, 1, limiting_angle_deg=angle)
        x = math.pi * 1e-9 / (1.21 * 343)
        weak_sheet_limit = 10 / math.log(10) * x**2 * (
            1 + math.cos(math.radians(angle)) ** 2
        ) / 2
        assert result == pytest.approx(weak_sheet_limit, rel=1e-12, abs=0)


def test_more_grazing_incidence_reduces_limp_sheet_loss():
    narrow = mass_law_diffuse_tl(THIRD_OCTAVE_NOMINAL_HZ, 10, limiting_angle_deg=30)
    broad = mass_law_diffuse_tl(THIRD_OCTAVE_NOMINAL_HZ, 10, limiting_angle_deg=78)
    normal = mass_law_normal_tl(THIRD_OCTAVE_NOMINAL_HZ, 10)
    assert np.all(normal >= narrow)
    assert np.all(narrow >= broad)
    assert np.all(broad > 0)


@pytest.mark.parametrize("model", [mass_law_normal_tl, mass_law_diffuse_tl])
def test_extreme_finite_inputs_do_not_overflow_intermediate_products(model):
    result = model([1e-200, 1e200], 1e200)
    assert np.all(np.isfinite(result))
    assert np.all(result >= 0)
    assert result[1] > result[0]


def test_plate_critical_frequency_and_scaling():
    # Independent direct evaluation of the homogeneous thin-plate expression.
    density, thickness, modulus, ratio = 2400, 0.1, 30e9, 0.2
    stiffness = modulus * thickness**3 / (12 * (1 - ratio**2))
    expected = 343**2 / (2 * math.pi) * math.sqrt(density * thickness / stiffness)
    frequency = critical_frequency(density, thickness, modulus, ratio)
    assert frequency == pytest.approx(expected, rel=1e-14)
    assert critical_frequency(density, 2 * thickness, modulus, ratio) == pytest.approx(
        frequency / 2,
    )
    assert critical_frequency(density, thickness, 4 * modulus, ratio) == pytest.approx(
        frequency / 2,
    )
    assert critical_frequency(density, thickness, modulus, -0.2) == pytest.approx(frequency)


def test_mass_air_mass_resonance_and_independent_mass_scaling():
    expected = math.sqrt(1.21 * 343**2 / 0.1 * (1 / 10 + 1 / 15)) / (2 * math.pi)
    frequency = mass_air_mass_resonance(10, 15, 0.1)
    assert frequency == pytest.approx(expected, rel=1e-14)
    assert mass_air_mass_resonance(15, 10, 0.1) == pytest.approx(frequency)
    assert mass_air_mass_resonance(20, 30, 0.1) == pytest.approx(frequency / math.sqrt(2))
    assert mass_air_mass_resonance(10, 15, 0.4) == pytest.approx(frequency / 2)
    assert mass_air_mass_resonance(10, 1e200, 0.1) == pytest.approx(
        math.sqrt(1.21 * 343**2 / (0.1 * 10)) / (2 * math.pi),
    )


def test_power_transmission_conversion_roundtrip():
    loss = np.array([0, 1, 10, 20, 60, 100, 3000], dtype=float)
    np.testing.assert_allclose(tau_to_tl(tl_to_tau(loss)), loss, atol=1e-12)
    assert tl_to_tau(10) == pytest.approx(0.1)
    assert tau_to_tl(0.01) == pytest.approx(20)
    assert tl_to_tau(0) == 1
    assert tau_to_tl(1) == 0


@pytest.mark.parametrize("invalid", [0, -1, np.nan, np.inf, -np.inf, 1j, True, "10"])
@pytest.mark.parametrize("model", [mass_law_normal_tl, mass_law_diffuse_tl])
def test_mass_law_rejects_nonphysical_inputs(model, invalid):
    with pytest.raises(ValueError):
        model([100, invalid], 10)
    with pytest.raises(ValueError):
        model([100], invalid)
    with pytest.raises(ValueError):
        model([100], 10, air_density_kg_m3=invalid)
    with pytest.raises(ValueError):
        model([100], 10, sound_speed_m_s=invalid)


@pytest.mark.parametrize("invalid", [0, -1, np.nan, np.inf, 1j, True, "10"])
def test_diagnostic_functions_reject_nonphysical_positive_parameters(invalid):
    with pytest.raises(ValueError):
        surface_density(invalid, 0.1)
    with pytest.raises(ValueError):
        surface_density(2400, invalid)
    for index in [0, 1, 2, 4]:
        arguments = [2400, 0.1, 30e9, 0.2, 343]
        arguments[index] = invalid
        with pytest.raises(ValueError):
            critical_frequency(*arguments)
    for index in range(5):
        arguments = [10, 15, 0.1, 1.21, 343]
        arguments[index] = invalid
        with pytest.raises(ValueError):
            mass_air_mass_resonance(*arguments)


@pytest.mark.parametrize("invalid", [-1, 0.5, 0.8, np.nan, np.inf, 1j, [0.2], True, "0.2"])
def test_isotropic_plate_rejects_unstable_poisson_ratio(invalid):
    with pytest.raises(ValueError):
        critical_frequency(2400, 0.1, 30e9, invalid)


@pytest.mark.parametrize("angle", [0, -10, 90.001, 180, np.inf, np.nan, 1j, True, "78"])
def test_diffuse_model_rejects_invalid_cutoff(angle):
    with pytest.raises(ValueError):
        mass_law_diffuse_tl(100, 10, limiting_angle_deg=angle)


@pytest.mark.parametrize("invalid", [0, -0.1, 1.01, np.nan, np.inf, 1j, [], True, "0.1"])
def test_coefficient_conversion_rejects_nonphysical_inputs(invalid):
    with pytest.raises(ValueError):
        tau_to_tl(invalid)


@pytest.mark.parametrize("invalid", [-0.1, np.nan, np.inf, 1j, [], True, "10"])
def test_tl_conversion_rejects_nonphysical_inputs(invalid):
    with pytest.raises(ValueError):
        tl_to_tau(invalid)


def test_unrepresentable_outputs_raise_instead_of_clipping():
    with pytest.raises(ValueError, match="representable"):
        tl_to_tau(10000)
    with pytest.raises(ValueError, match="representable"):
        surface_density(1e308, 1e308)
    with pytest.raises(ValueError, match="representable"):
        surface_density(1e-300, 1e-300)
    with pytest.raises(ValueError, match="representable"):
        critical_frequency(1, 1e-300, 1, 0.2, 1e300)


def test_empty_frequency_input_and_nonscalar_mass_are_invalid():
    for model in [mass_law_normal_tl, mass_law_diffuse_tl]:
        with pytest.raises(ValueError):
            model([], 10)
        with pytest.raises(ValueError):
            model([100], [10, 20])
