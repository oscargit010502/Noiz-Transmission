"""Mathematical verification of the V2 model; no experimental equivalence claim."""

import math
from threading import Event

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import brentq

from noiz_transmission.core.physics import (
    mass_air_mass_resonance,
    mass_law_diffuse_tl,
    mass_law_normal_tl,
)
from noiz_transmission.core.transfer import (
    EXACT_BAND_CENTRES_HZ,
    NOMINAL_BANDS_HZ,
    Gap,
    MikiExtrapolationWarning,
    Plate,
    _adaptive_band_tau,
    _band_tau,
    _coefficients,
    miki_characteristics,
    miki_valid_frequency_range,
    narrowband_tau,
    predict_multilayer,
)


@pytest.mark.parametrize("angle", [0, 30, 78])
def test_limp_single_plate_matches_analytic_mass_impedance(angle):
    frequencies = np.geomspace(0.01, 20000, 80)
    mass = 14.0
    expected = 1 / (1 + (np.pi * frequencies * mass * math.cos(math.radians(angle))
                          / (1.21 * 343)) ** 2)
    np.testing.assert_allclose(
        narrowband_tau(frequencies, [Plate(mass)], incidence_angle_deg=angle), expected,
        rtol=1e-14,
    )


@pytest.mark.parametrize("incidence", ["normal", "diffuse"])
def test_limp_third_octaves_use_exact_edges_and_white_incident_power(incidence):
    actual = predict_multilayer([Plate(10)], frequencies_hz=[50, 125, 1000, 5000],
                               incidence=incidence)
    analytical = mass_law_normal_tl if incidence == "normal" else mass_law_diffuse_tl
    expected = []
    for centre in EXACT_BAND_CENTRES_HZ[[0, 4, 13, 20]]:
        lower, upper = centre * 10**(-1 / 20), centre * 10**(1 / 20)
        energy, _ = quad(lambda f: 10 ** (-float(analytical(f, 10)) / 10), lower, upper,
                         epsabs=1e-14, epsrel=1e-12)
        expected.append(-10 * math.log10(energy / (upper - lower)))
    np.testing.assert_allclose(actual, expected, atol=1e-11)
    # A true band energy mean differs from sampling its rounded nominal centre.
    assert abs(actual[1] - float(analytical(125, 10))) > 0.01


def test_bending_coincidence_transmits_and_structural_losses_are_passive():
    mass, stiffness, angle = 12.0, 600.0, 55.0
    frequency = 343**2 / (2 * math.pi) * math.sqrt(mass / stiffness)
    frequency /= math.sin(math.radians(angle))**2
    no_loss = narrowband_tau(frequency, [Plate(mass, stiffness, 0)], incidence_angle_deg=angle)
    damped = narrowband_tau(frequency, [Plate(mass, stiffness, .05)], incidence_angle_deg=angle)
    assert no_loss == pytest.approx(1.0, abs=1e-13)
    assert 0 < damped < no_loss
    assert float(narrowband_tau(frequency, [Plate(mass, stiffness)],
                               incidence_angle_deg=0)) < .001


def test_lossless_multi_leaf_conserves_energy():
    plates = (Plate(10, 350), Plate(6, 180), Plate(20, 1000))
    gaps = (Gap(.09), Gap(.04))
    frequencies = np.geomspace(30, 10000, 150)[:, None]
    sine_squared = np.linspace(0, .98, 65)[None, :]
    a, b, c, d = _coefficients(frequencies, sine_squared, plates, gaps, 1.21, 343)
    transmitted = 4 / abs(a + b + c + d)**2
    reflected = abs((a + b - c - d) / (a + b + c + d))**2
    np.testing.assert_allclose(reflected + transmitted, 1, atol=3e-14)


@pytest.mark.parametrize("angle", [0, 35, 78])
def test_reversing_asymmetric_absorbing_assembly_preserves_transmission(angle):
    plates = [Plate(14, 300, .08), Plate(8, 700, .05), Plate(20, 1500, .1)]
    gaps = [Gap(.08, 8000, .04), Gap(.03)]
    frequencies = np.geomspace(100, 5000, 90)
    forward = narrowband_tau(frequencies, plates, gaps, incidence_angle_deg=angle)
    backward = narrowband_tau(frequencies, plates[::-1], gaps[::-1], incidence_angle_deg=angle)
    np.testing.assert_allclose(forward, backward, rtol=2e-13)
    assert np.all((forward > 0) & (forward <= 1))


def test_vanishing_gap_tends_to_combined_mass_and_low_frequency_air_spring_limit():
    frequencies = np.array([1, 10, 100, 1000])
    near_contact = narrowband_tau(frequencies, [Plate(10), Plate(15)], [Gap(1e-12)])
    np.testing.assert_allclose(near_contact, narrowband_tau(frequencies, [Plate(25)]), rtol=1e-8)
    low_frequency = narrowband_tau(.01, [Plate(10), Plate(15)], [Gap(.1)])
    # Compressibility and the small cavity air mass vanish as f tends to zero.
    assert low_frequency == pytest.approx(float(narrowband_tau(.01, [Plate(25)])), abs=1e-9)


def test_two_equal_leaves_have_mass_air_mass_resonance_and_gap_dependency():
    prediction = mass_air_mass_resonance(20, 20, .05)
    frequencies = np.linspace(.97 * prediction, 1.03 * prediction, 3001)
    tau = narrowband_tau(frequencies, [Plate(20), Plate(20)], [Gap(.05)])
    resonance = frequencies[tau.argmax()]
    assert resonance == pytest.approx(prediction, rel=.004)
    assert tau.max() > .999
    assert float(narrowband_tau(prediction, [Plate(20), Plate(20)], [Gap(.1)])) < .05


def test_miki_matches_independent_phonometry_coefficients_and_sign_convention():
    phonometry = pytest.importorskip("phonometry.materials.porous_absorber")
    frequencies = np.array([101, 500, 1000, 4999])
    z, k = miki_characteristics(frequencies, 8000, air_density=1.21, sound_speed=343)
    independent = phonometry.miki(frequencies, 8000, air_density=1.21, speed_of_sound=343)
    np.testing.assert_allclose(z, independent.characteristic_impedance, rtol=1e-14)
    np.testing.assert_allclose(k, independent.wavenumber, rtol=1e-14)
    assert np.all(z.real > 0)
    assert np.all(k.imag < 0)  # exp(-j*k*x) decays with distance.


def test_porous_slab_matches_multiple_reflection_solution():
    frequencies = np.array([100, 500, 1000, 3000])
    z, k = miki_characteristics(frequencies, 8000)
    reflection = (z - 1.21 * 343) / (z + 1.21 * 343)
    phase = np.exp(-1j * k * .05)
    amplitude = (1 - reflection**2) * phase / (1 - reflection**2 * phase**2)
    actual = narrowband_tau(frequencies, [Plate(1e-12), Plate(1e-12)], [Gap(.05, 8000, .05)])
    np.testing.assert_allclose(actual, abs(amplitude)**2, rtol=1e-9)


def test_porous_fill_changes_physical_response_and_warns_at_full_band_edges():
    plates = [Plate(10, 400, .03), Plate(10, 400, .03)]
    frequency = mass_air_mass_resonance(10, 10, .1)
    empty = narrowband_tau(frequency, plates, [Gap(.1)])
    filled = narrowband_tau(frequency, plates, [Gap(.1, 5000, .05)])
    assert float(filled) < float(empty)
    assert miki_valid_frequency_range(5000) == (50, 5000)
    # Nominal 50 and 5000 are at the fit boundary; their exact band edges go outside it.
    with pytest.warns(MikiExtrapolationWarning, match="outside 50 < f < 5000"):
        predict_multilayer(plates, [Gap(.1, 5000, .05)], frequencies_hz=[50, 5000])


def test_quadrature_converges_near_coincidence_for_absorbing_double_leaf():
    plates = (Plate(10, 400, .03), Plate(10, 400, .03))
    gaps = (Gap(.1, 10000, .05),)
    centres = EXACT_BAND_CENTRES_HZ[[17, 18, 19, 20]]
    angular_cutoff = math.sin(math.radians(78))**2
    coarse = [_band_tau(f, plates, gaps, 1.21, 343, angular_cutoff, 256, 64) for f in centres]
    fine = [_band_tau(f, plates, gaps, 1.21, 343, angular_cutoff, 1024, 256) for f in centres]
    np.testing.assert_allclose(-10 * np.log10(coarse), -10 * np.log10(fine), atol=.015, rtol=0)


def test_empty_cavity_narrow_angular_resonance_uses_resolved_integration():
    plates = (Plate(10, 400, .03), Plate(10, 400, .03))
    gaps = (Gap(.1),)
    # 1600 Hz contains a sharp cavity transmission ridge missed by coarse angle quadrature.
    actual = predict_multilayer(plates, gaps, frequencies_hz=[1600])
    independently_refined = _adaptive_band_tau(EXACT_BAND_CENTRES_HZ[15], plates, gaps,
                                              1.21, 343, math.sin(math.radians(78))**2)
    assert actual[0] == pytest.approx(-10 * math.log10(independently_refined), abs=.01)
    assert actual[0] == pytest.approx(50.1143, abs=.01)


@pytest.mark.parametrize("mass,depth,nominal", [
    (10.164445435122943, .2005680630917093, 2500),
    (100, .1, 1600),
])
def test_normal_cavity_resonance_cannot_hide_between_frequency_quadrature_nodes(mass, depth, nominal):
    # Independent equal-limp-leaf solution: tau = 1 / (1 + r**2), where
    # r=x*cos(kd)-x²*sin(kd)/2. This case fooled whole-band 32/64-point grids:
    # 73.775557 / 73.767939 dB versus the resolved reference 47.234642 dB.
    centre = EXACT_BAND_CENTRES_HZ[np.flatnonzero(NOMINAL_BANDS_HZ == nominal)[0]]
    lower, upper = centre * 10**(-1 / 20), centre * 10**(1 / 20)

    def reflection(f):
        x = 2 * np.pi * f * mass / (1.21 * 343)
        phase = 2 * np.pi * f * depth / 343
        return x * np.cos(phase) - x**2 * np.sin(phase) / 2

    grid = np.linspace(lower, upper, 101)
    roots = [brentq(reflection, x, y) for x, y in zip(grid[:-1], grid[1:], strict=True)
             if reflection(x) * reflection(y) < 0]
    assert roots
    points = []
    for root in roots:
        step = 1e-5
        width = 1 / abs((reflection(root + step) - reflection(root - step)) / (2 * step))
        points.extend(root + multiplier * width for multiplier in (-100, -10, -1, 0, 1, 10, 100)
                      if lower < root + multiplier * width < upper)
    energy, _ = quad(lambda f: 1 / (1 + reflection(f)**2), lower, upper,
                     points=sorted(points), epsabs=1e-18, epsrel=1e-7, limit=400)
    expected = -10 * math.log10(energy / (upper - lower))
    actual = predict_multilayer([Plate(mass)] * 2, [Gap(depth)], frequencies_hz=[nominal],
                               incidence="normal")
    assert actual[0] == pytest.approx(expected, abs=.001)


def test_diffuse_coincidence_cavity_ridge_is_not_certified_by_coarse_grid_agreement():
    # Reference 33.40241949 dB evaluated by the reverse integration order:
    # resonance-resolved frequency integration nested inside adaptive angular
    # integration. Production uses angular-inside-frequency integration.
    # Coarse whole-band grids incorrectly agreed at 33.523968 / 33.493593 dB.
    result = predict_multilayer([Plate(5.677360880736749, 226.4694822540052, .03)] * 2,
                               [Gap(.3314146994590839)], frequencies_hz=[4000])
    assert result[0] == pytest.approx(33.40241949, abs=.003)


@pytest.mark.parametrize("mass,nominal", [(10, 5000), (1000, 1600)])
def test_close_triple_leaf_modes_are_resolved_even_without_sampled_sign_changes(mass, nominal):
    # Independent algebra for three identical limp leaves and two identical
    # air gaps: tau=1/(1+r²), r=x/2*[3cos²φ-sin²φ-4x sinφ cosφ+x²sin²φ].
    # The two branches tanφ=(2x±sqrt(x²+3))/(x²-1) provide explicit root brackets.
    centre = EXACT_BAND_CENTRES_HZ[np.flatnonzero(NOMINAL_BANDS_HZ == nominal)[0]]
    lower, upper = centre * 10**(-1 / 20), centre * 10**(1 / 20)
    depth = .1

    def reflection(f):
        x = 2 * np.pi * f * mass / (1.21 * 343)
        phase = 2 * np.pi * f * depth / 343
        co, si = np.cos(phase), np.sin(phase)
        return x / 2 * (3 * co**2 - si**2 - 4 * x * si * co + x**2 * si**2)

    roots = []
    for mode in range(1, math.ceil(upper * 2 * depth / 343) + 1):
        for branch in (-1, 1):
            def equation(f):
                x = 2 * np.pi * f * mass / (1.21 * 343)
                return np.tan(2 * np.pi * f * depth / 343) - (
                    2 * x + branch * np.sqrt(x**2 + 3)
                ) / (x**2 - 1)

            root = brentq(equation, mode * 343 / (2 * depth) + 1e-9,
                           (mode + .5) * 343 / (2 * depth) - 1e-9, xtol=1e-12)
            if lower < root < upper:
                roots.append(root)
    assert len(roots) == 2
    points = []
    for root in roots:
        step = 1e-5
        width = 1 / abs((reflection(root + step) - reflection(root - step)) / (2 * step))
        points.extend(root + multiplier * width for multiplier in [0, *(sign * 10.0**power for power in range(10) for sign in (-1, 1))]
                      if lower < root + multiplier * width < upper)
    energy, _ = quad(lambda f: 1 / (1 + reflection(f)**2), lower, upper,
                     points=sorted(points), epsabs=1e-18, epsrel=1e-6, limit=400)
    expected = -10 * math.log10(energy / (upper - lower))
    actual = predict_multilayer([Plate(mass, 434, .03)] * 3, [Gap(depth)] * 2,
                               frequencies_hz=[nominal], incidence="normal")
    assert actual[0] == pytest.approx(expected, abs=.002)


def test_prediction_can_be_cancelled_cooperatively():
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="cancelado"):
        predict_multilayer([Plate(10)] * 2, [Gap(.1)], cancel_event=event)


@pytest.mark.parametrize("bad", [True, "10", 1j, [1], np.inf, np.nan, -1])
def test_plate_and_gap_reject_nonphysical_scalars(bad):
    for create in (lambda: Plate(bad), lambda: Plate(10, bad), lambda: Plate(10, 400, bad),
                   lambda: Gap(bad), lambda: Gap(.1, bad, .05), lambda: Gap(.1, 10000, bad)):
        with pytest.raises(ValueError):
            create()


def test_zero_mass_zero_gap_and_incomplete_absorber_parameters_are_invalid():
    for create in (lambda: Plate(0), lambda: Gap(0), lambda: Gap(.1, 5000),
                   lambda: Gap(.1, None, .05), lambda: Gap(.1, 5000, .2)):
        with pytest.raises(ValueError):
            create()


@pytest.mark.parametrize("frequency", [0, -1, True, 1j, "50", [], np.inf, np.nan, [50, True]])
def test_narrowband_rejects_invalid_frequencies(frequency):
    with pytest.raises(ValueError):
        narrowband_tau(frequency, [Plate(10)])


def test_unsupported_assemblies_and_band_centres_are_explicit():
    for plates, gaps in (([], []), ([Plate(10)], [Gap(.1)]), ([Plate(10)] * 4, [Gap(.1)] * 3),
                         ([object()], []), ([Plate(10)] * 2, [object()])):
        with pytest.raises(ValueError):
            predict_multilayer(plates, gaps)
    with pytest.raises(ValueError, match="nominal"):
        predict_multilayer([Plate(10)], frequencies_hz=[62])
    with pytest.raises(ValueError, match="incidence"):
        predict_multilayer([Plate(10)], incidence="random")
    assert predict_multilayer([Plate(10)], frequencies_hz=[[100, 200], [500, 1000]]).shape == (2, 2)
    assert len(predict_multilayer([Plate(10)])) == len(NOMINAL_BANDS_HZ) == 21


@pytest.mark.parametrize("angle", [True, -1, 90, np.nan, np.inf, "30"])
def test_narrowband_rejects_invalid_incidence_angle(angle):
    with pytest.raises(ValueError):
        narrowband_tau([100], [Plate(10)], incidence_angle_deg=angle)


def test_unrepresentable_transfer_is_rejected_not_returned_as_zero_or_infinity():
    with pytest.raises(ValueError, match="representable"):
        narrowband_tau(1e200, [Plate(1e200, 1e200)])
