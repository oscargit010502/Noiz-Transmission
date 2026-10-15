"""Mathematical limits and external fixture for the explicit legacy STC method."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from noiz_transmission.core.ratings import (
    STC_FREQUENCIES_HZ,
    STC_PROCEDURE,
    STC_REFERENCE_DB,
    legacy_stc,
)

FREQUENCIES = np.array(STC_FREQUENCIES_HZ)
REFERENCE = np.array(STC_REFERENCE_DB) + 40


def test_reference_contour_total_deficit_boundary_is_inclusive():
    result = legacy_stc(FREQUENCIES, REFERENCE)
    assert result.stc == 42
    assert result.unfavorable_deviation_db == 32
    assert result.maximum_deviation_db == 2
    assert result.procedure == STC_PROCEDURE
    np.testing.assert_array_equal(result.reference_curve_db, REFERENCE + 2)


def test_deep_notch_respects_individual_eight_db_limit():
    measured = REFERENCE + 30
    measured[0] = REFERENCE[0] - 8
    result = legacy_stc(FREQUENCIES, measured)
    assert result.stc == 40
    assert result.unfavorable_deviation_db == 8
    assert result.maximum_deviation_db == 8
    measured[0] -= 1
    assert legacy_stc(FREQUENCIES, measured).stc == 39


def test_joint_sum_and_individual_limit_can_be_active_together():
    measured = REFERENCE + 10
    measured[:4] = REFERENCE[:4] - 8
    result = legacy_stc(FREQUENCIES, measured)
    assert result.stc == 40
    assert result.unfavorable_deviation_db == 32
    assert result.maximum_deviation_db == 8


@pytest.mark.parametrize("shift", [-1000, -51, 0, 300, 1000])
def test_integer_translation_has_no_arbitrary_rating_bounds(shift):
    result = legacy_stc(FREQUENCIES, REFERENCE + shift)
    assert result.stc == 42 + shift
    assert result.unfavorable_deviation_db == 32


def test_whole_db_rounding_is_explicit_and_half_away_from_zero():
    assert legacy_stc(FREQUENCIES, REFERENCE - .5).stc == 42
    assert legacy_stc(FREQUENCIES, REFERENCE - .5001).stc == 41
    negative_reference = REFERENCE - 100
    assert legacy_stc(FREQUENCIES, negative_reference + .5).stc == -58
    assert legacy_stc(FREQUENCIES, negative_reference + .5001).stc == -57


def test_independent_python_acoustics_026_smooth_spectrum_fixture():
    # python-acoustics 0.2.6 building.stc() returns 40 for this spectrum.
    # It is ONLY a comparison away from its defective individual-deficit
    # handling. The 8 dB boundary is independently tested above instead.
    # https://github.com/python-acoustics/python-acoustics/blob/v0.2.6/acoustics/building.py
    measured = [23, 25, 28, 29, 30, 34, 36, 40, 42, 43, 43, 43, 44, 45, 45, 46]
    result = legacy_stc(FREQUENCIES, measured)
    assert result.stc == 40
    assert result.unfavorable_deviation_db == 27
    assert result.maximum_deviation_db == 6


def test_matches_exhaustive_feasibility_for_many_random_spectra():
    random = np.random.default_rng(170413)
    for _ in range(50):
        measured = random.integers(-20, 90, 16)
        # Independent exhaustive search in absolute STC, using the three
        # linear segments defining the contour instead of the library array.
        contour = np.concatenate((np.arange(-16, 0, 3), np.arange(5), np.full(5, 4)))
        feasible = []
        for candidate in range(-50, 110):
            deficit = np.maximum(contour + candidate - measured, 0)
            if deficit.sum() <= 32 and deficit.max() <= 8:
                feasible.append(candidate)
        assert legacy_stc(FREQUENCIES, measured).stc == max(feasible)


def test_extra_nominal_bands_do_not_affect_stc_but_are_validated():
    frequencies = [50, 63, 80, 100, *FREQUENCIES, 5000]
    measured = [-999, -999, -999, -999, *REFERENCE, -999]
    assert legacy_stc(frequencies, measured) == legacy_stc(FREQUENCIES, REFERENCE)
    measured[-1] = np.nan
    with pytest.raises(ValueError):
        legacy_stc(frequencies, measured)


@pytest.mark.parametrize(("frequencies", "values"), [
    ([], []),
    (FREQUENCIES[:-1], REFERENCE[:-1]),
    (FREQUENCIES, REFERENCE[:-1]),
    (FREQUENCIES[::-1], REFERENCE[::-1]),
    ([125, *FREQUENCIES], [10, *REFERENCE]),
    ([124.99, *FREQUENCIES[1:]], REFERENCE),
    ([*FREQUENCIES, 6300], [*REFERENCE, 40]),
    ([*FREQUENCIES], [[*REFERENCE]]),
    ([np.nan, *FREQUENCIES[1:]], REFERENCE),
    (FREQUENCIES, [np.inf, *REFERENCE[1:]]),
    (FREQUENCIES, [True, *REFERENCE[1:]]),
    (FREQUENCIES, ["24", *REFERENCE[1:]]),
    (FREQUENCIES, [24 + 0j, *REFERENCE[1:]]),
    (["125", *FREQUENCIES[1:]], REFERENCE),
])
def test_invalid_inputs_never_interpolate_or_coerce(frequencies, values):
    with pytest.raises(ValueError):
        legacy_stc(frequencies, values)


def test_fitting_is_immutable_and_preserves_input():
    before = REFERENCE.copy()
    result = legacy_stc(FREQUENCIES, REFERENCE)
    np.testing.assert_array_equal(REFERENCE, before)
    with pytest.raises(FrozenInstanceError):
        result.stc = 1
