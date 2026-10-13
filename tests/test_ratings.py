"""Analytical examples and limits for the provisional airborne Rw procedure."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from noiz_transmission.core.ratings import (
    ISO717_FREQUENCIES_HZ,
    ISO717_REFERENCE_DB,
    iso717_rw,
)

FREQUENCIES = np.array(ISO717_FREQUENCIES_HZ)
REFERENCE = np.array(ISO717_REFERENCE_DB, dtype=float)


def test_reference_curve_can_shift_two_db_with_exactly_32_db_deficit():
    result = iso717_rw(FREQUENCIES, REFERENCE)
    assert result.rw_db == 54
    assert result.unfavorable_deviation_db == 32.0
    np.testing.assert_array_equal(result.reference_curve_db, REFERENCE + 2)
    assert sum(np.maximum(0, np.array(result.reference_curve_db) + 1 - REFERENCE)) > 32


def test_single_deep_notch_uses_total_deficit_without_an_stc_band_limit():
    measured = REFERENCE + 20
    measured[0] = REFERENCE[0] - 32
    result = iso717_rw(FREQUENCIES, measured)
    assert result.rw_db == 52
    assert result.unfavorable_deviation_db == 32
    # Lowering the notch by a tenth makes this same reference infeasible.
    measured[0] -= 0.1
    assert iso717_rw(FREQUENCIES, measured).rw_db == 51


def test_deficit_distribution_changes_weighted_rating():
    # Both curves have a 16 dB deficit at the unshifted reference. Concentrate
    # it in one band versus spreading it: the number of active bands differs.
    spread = REFERENCE - 1
    concentrated = REFERENCE + 20
    concentrated[0] = REFERENCE[0] - 16
    assert iso717_rw(FREQUENCIES, spread).rw_db == 53
    assert iso717_rw(FREQUENCIES, concentrated).rw_db == 68


@pytest.mark.parametrize("shift", [-100, -53, 0, 17, 300])
def test_integer_translation_invariance_without_arbitrary_rating_bounds(shift):
    original = iso717_rw(FREQUENCIES, REFERENCE)
    translated = iso717_rw(FREQUENCIES, REFERENCE + shift)
    assert translated.rw_db == original.rw_db + shift
    assert translated.unfavorable_deviation_db == original.unfavorable_deviation_db


def test_decimal_rounding_at_feasibility_boundary_is_explicit():
    assert iso717_rw(FREQUENCIES, REFERENCE - 0.04).rw_db == 54
    assert iso717_rw(FREQUENCIES, REFERENCE - 0.06).rw_db == 53
    # x.95 rounds up to x+1.0 using half-away-from-zero, not truncation.
    assert iso717_rw(FREQUENCIES, REFERENCE - 0.05).rw_db == 54


@pytest.mark.parametrize("extra", [(4000,), (5000,), (4000, 5000)])
def test_high_frequency_extra_bands_are_explicitly_excluded(extra):
    result = iso717_rw([*FREQUENCIES, *extra], [*REFERENCE, *([-900] * len(extra))])
    assert result == iso717_rw(FREQUENCIES, REFERENCE)
    assert len(result.reference_curve_db) == 16


@pytest.mark.parametrize(
    ("frequencies", "values"),
    [
        ([], []),
        (FREQUENCIES[:-1], REFERENCE[:-1]),
        (FREQUENCIES, REFERENCE[:-1]),
        (FREQUENCIES[::-1], REFERENCE[::-1]),
        ([*FREQUENCIES[:2], *FREQUENCIES[1:]], [*REFERENCE[:2], *REFERENCE[1:]]),
        ([99.99, *FREQUENCIES[1:]], REFERENCE),
        ([80, *FREQUENCIES], [33, *REFERENCE]),
        ([*FREQUENCIES, 6300], [*REFERENCE, 60]),
        ([[*FREQUENCIES]], [[*REFERENCE]]),
        ([np.nan, *FREQUENCIES[1:]], REFERENCE),
        (FREQUENCIES, [np.inf, *REFERENCE[1:]]),
        (FREQUENCIES, [np.nan, *REFERENCE[1:]]),
        ([*FREQUENCIES, 5000], [*REFERENCE, np.nan]),
        (FREQUENCIES, ["invalid", *REFERENCE[1:]]),
        (FREQUENCIES, ["33", *REFERENCE[1:]]),
        (["100", *FREQUENCIES[1:]], REFERENCE),
        (FREQUENCIES, [True, *REFERENCE[1:]]),
        (FREQUENCIES, np.ones(16, dtype=bool)),
        (FREQUENCIES.astype(complex), REFERENCE),
        (FREQUENCIES, REFERENCE.astype(complex)),
        (FREQUENCIES, REFERENCE.astype(complex) + 2j),
        (FREQUENCIES, [33 + 0j, *REFERENCE[1:]]),
        (FREQUENCIES, np.array([33 + 1j, *REFERENCE[1:]], dtype=object)),
    ],
)
def test_invalid_spectra_are_rejected_without_interpolation(frequencies, values):
    with pytest.raises(ValueError):
        iso717_rw(frequencies, values)


def test_fitting_does_not_mutate_input_and_result_is_immutable():
    values = REFERENCE.copy()
    result = iso717_rw(FREQUENCIES, values)
    np.testing.assert_array_equal(values, REFERENCE)
    with pytest.raises(FrozenInstanceError):
        result.rw_db = 1
