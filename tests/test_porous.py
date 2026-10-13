"""Independent Miki slab and facing verification, with no experimental accuracy claim."""

import math
from threading import Event

import numpy as np
import pytest
from scipy.integrate import quad

from noiz_transmission.core.transfer import (
    EXACT_BAND_CENTRES_HZ,
    MikiExtrapolationWarning,
    Plate,
    PorousLayer,
    _coefficients,
    _tau,
    miki_characteristics,
    narrowband_tau,
    predict_multilayer,
    predict_porous_layer,
)


def _slab_transmission(frequency, sine_squared, thickness=.05, sigma=8000):
    # Multiple reflections at the two fluid interfaces, independently of the
    # transfer-matrix implementation. exp(-j*kz*d) decays with the phasor convention.
    z, k = miki_characteristics(frequency, sigma)
    kz = np.sqrt(k**2 - (2 * np.pi * frequency / 343)**2 * sine_squared)
    zn = z * k / kz
    exterior = 1.21 * 343 / np.sqrt(1 - sine_squared)
    reflection = (zn - exterior) / (zn + exterior)
    phase = np.exp(-1j * kz * thickness)
    transmission = (1 - reflection**2) * phase / (1 - reflection**2 * phase**2)
    return abs(transmission)**2


@pytest.mark.parametrize("angle", [0, 45, 78])
def test_unbacked_porous_layer_matches_multiple_reflections(angle):
    frequencies = np.geomspace(100, 5000, 80)
    sine_squared = math.sin(math.radians(angle))**2
    actual = _tau(frequencies, np.asarray(sine_squared), (), (), 1.21, 343,
                  PorousLayer(.05, 8000))
    np.testing.assert_allclose(actual, _slab_transmission(frequencies, sine_squared), rtol=1e-13)


@pytest.mark.parametrize("incidence", ["normal", "diffuse"])
def test_porous_third_octaves_match_independent_interface_integration(incidence):
    angular_limit = math.sin(math.radians(78))**2
    expected = []
    for centre in EXACT_BAND_CENTRES_HZ[[4, 13, 20]]:
        lower, upper = centre * 10**-.05, centre * 10**.05

        def frequency_power(f):
            if incidence == "normal":
                return _slab_transmission(f, 0)
            integral, _ = quad(lambda u: _slab_transmission(f, u), 0, angular_limit,
                                epsabs=1e-12, epsrel=1e-10)
            return integral / angular_limit

        power, _ = quad(frequency_power, lower, upper, epsabs=1e-10, epsrel=1e-9)
        expected.append(-10 * math.log10(power / (upper - lower)))
    actual = predict_porous_layer(PorousLayer(.05, 8000), frequencies_hz=[125, 1000, 5000],
                                  incidence=incidence)
    np.testing.assert_allclose(actual, expected, atol=1e-7, rtol=0)


def test_porous_facing_matches_product_of_physical_fluid_and_sheet_matrices():
    frequencies = np.geomspace(100, 5000, 80)
    mass, thickness, angle = 11.0, .045, 37.0
    omega = 2 * np.pi * frequencies
    sine_squared = math.sin(math.radians(angle))**2
    exterior = 1.21 * 343 / math.cos(math.radians(angle))
    z, k = miki_characteristics(frequencies, 7000)
    kz = np.sqrt(k**2 - (omega / 343)**2 * sine_squared)
    normal = z * k / kz
    co, si = np.cos(kz * thickness), 1j * np.sin(kz * thickness)
    # Fluid then limp plate, dimensional (p,v) matrices multiplied on paper.
    a, b = co, co * 1j * omega * mass + normal * si
    c, d = si / normal, si / normal * 1j * omega * mass + co
    expected = 4 / abs(a + b / exterior + c * exterior + d)**2
    actual = narrowband_tau(frequencies, [Plate(mass)], incidence_angle_deg=angle,
                            facing=PorousLayer(thickness, 7000))
    np.testing.assert_allclose(actual, expected, rtol=1e-13)
    assert not np.allclose(actual, narrowband_tau(frequencies, [Plate(mass)],
                                                incidence_angle_deg=angle))


def test_porosity_dissipates_energy_and_is_not_a_rigid_backed_absorber():
    frequencies = np.geomspace(100, 5000, 40)[:, None]
    angles = np.linspace(0, .97, 30)[None, :]
    a, b, c, d = _coefficients(frequencies, angles, (), (), 1.21, 343, PorousLayer(.06, 5000))
    transmission = 4 / abs(a + b + c + d)**2
    reflection = abs((a + b - c - d) / (a + b + c + d))**2
    assert np.all(transmission > 0)
    assert np.all(transmission + reflection < 1)
    assert np.all(transmission + reflection > 0)


@pytest.mark.parametrize("incidence", ["normal", "diffuse"])
def test_zero_thickness_excludes_facing_exactly_and_empty_porous_has_zero_tl(incidence):
    layer = PorousLayer(0, 8000)
    bands = [50, 1000, 5000]  # No extrapolation warning for absent material.
    bare = predict_multilayer([Plate(8, 300, .03)], frequencies_hz=bands, incidence=incidence)
    faced = predict_multilayer([Plate(8, 300, .03)], frequencies_hz=bands,
                              incidence=incidence, facing=layer)
    np.testing.assert_array_equal(bare, faced)
    porous = predict_porous_layer(layer, frequencies_hz=bands, incidence=incidence)
    np.testing.assert_allclose(porous, 0, atol=1e-12)


def test_porous_and_facing_band_warning_uses_edges_and_cancellation():
    with pytest.warns(MikiExtrapolationWarning, match="Facing/porous layer"):
        predict_porous_layer(PorousLayer(.05, 5000), frequencies_hz=[50])
    with pytest.warns(MikiExtrapolationWarning, match="Facing/porous layer"):
        predict_multilayer([Plate(10)], frequencies_hz=[5000], facing=PorousLayer(.05, 5000))
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        predict_porous_layer(PorousLayer(.05, 8000), frequencies_hz=[1000], cancel_event=event)


@pytest.mark.parametrize("bad", [True, -1, np.inf, np.nan, "20", 1j])
def test_porous_layer_rejects_impossible_inputs(bad):
    with pytest.raises(ValueError):
        PorousLayer(bad, 5000)
    with pytest.raises(ValueError):
        PorousLayer(.05, bad)


def test_porous_predictors_reject_untyped_layers():
    with pytest.raises(ValueError, match="PorousLayer"):
        predict_porous_layer(object())
    with pytest.raises(ValueError, match="PorousLayer"):
        predict_multilayer([Plate(10)], facing=object())
