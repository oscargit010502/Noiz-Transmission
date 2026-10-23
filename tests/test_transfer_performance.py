"""Optimized angular preparation preserves the reference transfer algebra."""

import math
from threading import Event

import numpy as np
import pytest

from noiz_transmission.core import transfer


@pytest.mark.parametrize("panels", [1, 2, 3, 4])
@pytest.mark.parametrize("filled", [False, True])
def test_prepared_scalar_and_batch_kernel_matches_broadcasted_reference(panels, filled):
    plates = tuple(transfer.Plate(8 + index * 3, 350 + index * 250, .015 + .01 * index)
                   for index in range(panels))
    gaps = tuple(transfer.Gap(.08 + .01 * index, 12000 if filled else None,
                              .04 if filled else 0) for index in range(panels - 1))
    facing = transfer.PorousLayer(.02, 8000)
    angles = np.array([0, .1, .5, .8, .97, 1 - 1e-10])
    for frequency in (125, 1600, 4000):
        prepared = transfer._angular_coefficients(frequency, plates, gaps, 1.21, 343, facing)
        expected = transfer._coefficients(np.asarray(frequency), angles,
                                          plates, gaps, 1.21, 343, facing)
        np.testing.assert_allclose(prepared(angles), expected, rtol=2e-12, atol=1e-12)
        actual = np.array([prepared(float(angle)) for angle in angles]).T
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-12)


def test_prepared_gas_critical_angle_and_evanescent_kernel():
    plates = (transfer.Plate(10, 500, .03), transfer.Plate(15, 900, .02))
    gaps = (transfer.Gap(.04, gas_density_kg_m3=.166, gas_sound_speed_m_s=1007),)
    critical_u = (343 / 1007)**2
    angles = np.array([0, critical_u - 1e-10, critical_u, critical_u + 1e-10, .8])
    prepared = transfer._angular_coefficients(1250, plates, gaps, 1.21, 343)
    expected = transfer._coefficients(np.asarray(1250), angles, plates, gaps, 1.21, 343)
    np.testing.assert_allclose(prepared(angles), expected, rtol=1e-12)
    np.testing.assert_allclose(np.array([prepared(float(u)) for u in angles]).T,
                               expected, rtol=1e-12)


def test_porous_coefficients_are_prepared_once_per_unique_medium(monkeypatch):
    original = transfer.miki_characteristics
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(transfer, "miki_characteristics", counted)
    plates = (transfer.Plate(10, 400, .03),) * 4
    prepared = transfer._angular_coefficients(
        1000, plates, (transfer.Gap(.1, 10000, .05),) * 3, 1.21, 343,
        transfer.PorousLayer(.02, 10000),
    )
    for angle in np.linspace(0, .9, 100):
        prepared(float(angle))
    prepared(np.linspace(0, .9, 100).reshape(10, 10))
    assert calls == [10000]


def test_standalone_porous_kernel_matches_reference():
    facing = transfer.PorousLayer(.05, 10000)
    angles = np.linspace(0, .98, 101)
    prepared = transfer._angular_coefficients(1000, (), (), 1.21, 343, facing)
    expected = transfer._coefficients(np.asarray(1000), angles, (), (), 1.21, 343, facing)
    np.testing.assert_allclose(prepared(angles), expected, rtol=1e-12, atol=1e-12)


def test_running_angular_integration_still_checks_cancellation(monkeypatch):
    original = transfer._angular_coefficients
    event = Event()

    def cancel_after_preparation(*args, **kwargs):
        result = original(*args, **kwargs)
        event.set()
        return result

    monkeypatch.setattr(transfer, "_angular_coefficients", cancel_after_preparation)
    with pytest.raises(ValueError, match="cancelado"):
        transfer.predict_multilayer((transfer.Plate(10, 400, .03),) * 4,
                                    (transfer.Gap(.1),) * 3,
                                    frequencies_hz=[100], cancel_event=event)


def test_declared_tolerance_keeps_narrow_diffuse_ridge():
    # Independently resolved reverse-order integral, documented in test_transfer.
    expected = 33.40241949
    actual = transfer.predict_multilayer(
        (transfer.Plate(5.677360880736749, 226.4694822540052, .03),) * 2,
        (transfer.Gap(.3314146994590839),), frequencies_hz=[4000],
        quadrature_tolerance_db=.05,
    )
    assert math.isfinite(actual[0])
    assert actual[0] == pytest.approx(expected, abs=.003)


def test_finite_stack_requires_common_area_but_allows_axis_swap_and_distinct_edge_loss():
    from noiz_transmission.core.finite_panel import FinitePanel

    first = transfer.Plate(10, 400, .02, FinitePanel(2.4, 2.7, .01))
    rotated = transfer.Plate(15, 600, .02, FinitePanel(2.7, 2.4, .04))
    result = transfer.narrowband_tau([100, 500], (first, rotated), (transfer.Gap(.1),))
    assert np.all(np.isfinite(result))
    mismatched = transfer.Plate(15, 600, .02, FinitePanel(2.4, 3.0))
    with pytest.raises(ValueError, match="common width and height"):
        transfer.predict_multilayer((first, mismatched), (transfer.Gap(.1),),
                                    frequencies_hz=[100])
