"""Published finite-panel expressions, dimensions and limiting cases."""

import math

import numpy as np
import pytest

from noiz_transmission.core.finite_panel import FinitePanel


def test_first_mode_matches_separable_simply_supported_plate_eigenvalue():
    # Analytical plate eigenvalue omega11² = D/m' [(pi/a)²+(pi/b)²]².
    mass, stiffness, width, height = 12.0, 500.0, 1.2, 2.7
    expected = math.sqrt(stiffness / mass) * (
        (math.pi / width)**2 + (math.pi / height)**2
    ) / (2 * math.pi)
    assert FinitePanel(width, height).first_mode_hz(mass, stiffness) == pytest.approx(expected)
    assert FinitePanel(height, width).first_mode_hz(mass, stiffness) == pytest.approx(expected)
    assert FinitePanel(2 * width, 2 * height).first_mode_hz(mass, stiffness) == pytest.approx(expected / 4)
    assert FinitePanel(width, height).first_mode_hz(mass, 0) == 0


def test_davy_limit_matches_area_perimeter_expression_and_keeps_array_shape():
    a, b, speed = 2.4, 2.7, 343.0
    frequencies = np.array([[50, 100, 1000], [2000, 3150, 5000]], dtype=float)
    area, perimeter = a * b, 2 * (a + b)
    expected_cos_squared = np.minimum(0.9, speed / frequencies * perimeter / (8 * math.pi * area))
    result = FinitePanel(a, b).davy_sine_squared_limit(frequencies, speed)
    assert result.shape == frequencies.shape
    assert result == pytest.approx(1 - expected_cos_squared)
    assert result == pytest.approx(FinitePanel(b, a).davy_sine_squared_limit(frequencies, speed))
    assert FinitePanel(a, b).davy_sine_squared_limit(1000).shape == ()


def test_finite_size_limit_caps_at_point_nine_and_tends_to_hemisphere():
    panel = FinitePanel(1, 2)
    assert panel.davy_sine_squared_limit(1e-9) == pytest.approx(0.1)
    assert panel.davy_sine_squared_limit(1e12) == pytest.approx(1, abs=1e-10)
    frequencies = np.geomspace(1, 1e5, 100)
    values = panel.davy_sine_squared_limit(frequencies)
    assert np.all(np.diff(values) >= 0)
    assert np.all(values >= 0.1 - 1e-15)
    assert np.all(values <= 1)
    assert np.all(FinitePanel(2, 4).davy_sine_squared_limit(frequencies) >= values)


def test_extreme_finite_geometry_cannot_overflow_capped_angular_expression():
    assert FinitePanel(1e-300, 1e-300).davy_sine_squared_limit(1e-300) == pytest.approx(0.1)
    assert FinitePanel(1e300, 1e300).davy_sine_squared_limit(1e300) == 1


def test_first_mode_avoids_intermediate_overflow_when_answer_is_representable():
    assert FinitePanel(1e150, 1e150).first_mode_hz(1e-300, 1e300) == pytest.approx(math.pi)
    assert FinitePanel(1e-150, 1e-150).first_mode_hz(1e300, 1e-300) == pytest.approx(math.pi)


def test_edge_loss_is_explicit_and_additive_not_inferred_from_material():
    assert FinitePanel(2, 3).total_loss_factor(0.03) == 0.03
    assert FinitePanel(2, 3, 0.02).total_loss_factor(0.03) == pytest.approx(0.05)
    assert FinitePanel(2, 3, 0.02).total_loss_factor(0) == 0.02


def test_stiffness_asymptote_matches_published_expression_and_negative_slope():
    panel = FinitePanel(0.8, 1.2)
    mass, rigidity = 25, 4000
    frequencies = np.array([5, 10, 20])
    stiffness = math.pi**4 * rigidity * (1 / 0.8**2 + 1 / 1.2**2)**2
    expected = 20 * np.log10(stiffness / (4 * math.pi * frequencies * 1.21 * 343))
    actual = panel.stiffness_asymptote_tl(frequencies, mass, rigidity)
    assert actual == pytest.approx(expected)
    assert np.diff(actual) == pytest.approx([-20 * math.log10(2)] * 2)


def test_stiffness_asymptote_does_not_extrapolate_into_modal_region():
    panel = FinitePanel(0.8, 1.2)
    f11 = panel.first_mode_hz(25, 4000)
    for frequency in (0.5 * f11, f11, 2 * f11):
        with pytest.raises(ValueError, match="0.5\\*f11"):
            panel.stiffness_asymptote_tl(frequency, 25, 4000)
    with pytest.raises(ValueError, match="0.5\\*f11"):
        panel.stiffness_asymptote_tl(10, 25, 0)
    with pytest.raises(ValueError, match="impedance ratio"):
        panel.stiffness_asymptote_tl(5, 1e-5, 4e-4)


@pytest.mark.parametrize("bad", [True, "1", None, 0, -1, float("nan"), float("inf")])
def test_nonphysical_geometry_frequency_and_air_speed_rejected(bad):
    with pytest.raises(ValueError):
        FinitePanel(bad, 2)
    with pytest.raises(ValueError):
        FinitePanel(2, bad)
    with pytest.raises(ValueError):
        FinitePanel(2, 3).davy_sine_squared_limit(bad)
    with pytest.raises(ValueError):
        FinitePanel(2, 3).davy_sine_squared_limit(100, bad)
    with pytest.raises(ValueError):
        FinitePanel(2, 3).first_mode_hz(bad, 100)


@pytest.mark.parametrize("bad", [True, "1", None, -1, float("nan"), float("inf")])
def test_nonphysical_damping_and_stiffness_rejected(bad):
    with pytest.raises(ValueError):
        FinitePanel(2, 3, bad)
    with pytest.raises(ValueError):
        FinitePanel(2, 3).total_loss_factor(bad)
    with pytest.raises(ValueError):
        FinitePanel(2, 3).first_mode_hz(10, bad)


def test_unrepresentable_fundamental_frequency_and_sum_rejected():
    with pytest.raises(ValueError, match="representable"):
        FinitePanel(1e-300, 1).first_mode_hz(10, 100)
    with pytest.raises(ValueError, match="representable"):
        FinitePanel(2, 3, 1e308).total_loss_factor(1e308)
