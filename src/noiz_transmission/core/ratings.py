"""Provisional airborne Rw and explicitly legacy STC reference-curve ratings.

This implements the 16-band, integer-shift procedure described by ISO 717-1
(100–3150 Hz, at most 32 dB total unfavorable deviation). It is a numerical
rating of the supplied spectrum, not certification of a construction or a
replacement for laboratory measurement. Predicted spectra yield indicative Rw.

The reference data and rounding convention are independently cross-checked
against Phonometry 3.3.0, ``phonometry.building.weighted_rating`` (MIT):
https://github.com/jmrplens/phonometry . No external implementation is copied.
The STC function implements the legacy 32 dB sum / 8 dB individual-deficit
procedure described in the INSUL 10 public guide, with input rounded to whole
decibels. It does not claim compliance with an edition of ASTM E413. The
contour is independently cross-checked against python-acoustics' published
``stc_curve`` data; its algorithm is not used as an oracle for the 8 dB rule.
No impact rating, adaptation term, or room-to-room calculation is implied.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from numbers import Real

import numpy as np
from numpy.typing import ArrayLike

ISO717_FREQUENCIES_HZ: tuple[float, ...] = (
    100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0, 500.0,
    630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0,
)
ISO717_REFERENCE_DB: tuple[int, ...] = (
    33, 36, 39, 42, 45, 48, 51, 52, 53, 54, 55, 56, 56, 56, 56, 56,
)
STC_FREQUENCIES_HZ: tuple[float, ...] = (
    125.0, 160.0, 200.0, 250.0, 315.0, 400.0, 500.0, 630.0,
    800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0,
)
# A contour whose 500 Hz ordinate is 0 dB; its integer shift is the STC.
STC_REFERENCE_DB: tuple[int, ...] = (
    -16, -13, -10, -7, -4, -1, 0, 1, 2, 3, 4, 4, 4, 4, 4, 4,
)
STC_PROCEDURE = "STC-legacy-32-8-whole-dB-v1"


@dataclass(frozen=True)
class RwResult:
    """Indicative Rw and fitted curve on the 16 normative bands.

    ``unfavorable_deviation_db`` is a sum over bands, not uncertainty.
    The fitted reference always follows ``ISO717_FREQUENCIES_HZ`` even when
    the input contains additional 4000 Hz or 5000 Hz bands.
    """

    rw_db: int
    reference_curve_db: tuple[float, ...]
    unfavorable_deviation_db: float


@dataclass(frozen=True)
class StcResult:
    """Legacy STC from rounded TL, not a certified ASTM E413 test result."""

    stc: int
    reference_curve_db: tuple[float, ...]
    unfavorable_deviation_db: float
    maximum_deviation_db: float
    procedure: str = STC_PROCEDURE


def select_iso717_bands(
    frequencies_hz: ArrayLike,
    reduction_index_db: ArrayLike,
) -> tuple[float, ...]:
    """Validate and select the mandatory 16 bands without interpolation.

    Frequencies must be unique, strictly increasing nominal band centers.
    Optional 4000 Hz and 5000 Hz bands are accepted and explicitly excluded
    from the rating. All input values, including excluded bands, must be
    finite. Negative measured indices are allowed; values are never clipped.
    """
    frequencies, values = _validated_spectrum(frequencies_hz, reduction_index_db)
    allowed = (*ISO717_FREQUENCIES_HZ, 4000.0, 5000.0)
    if not np.all(np.isin(frequencies, allowed)):
        raise ValueError("Use nominal ISO 717 bands from 100–3150 Hz, optionally 4000/5000 Hz.")
    selected = np.isin(frequencies, ISO717_FREQUENCIES_HZ)
    if tuple(frequencies[selected]) != ISO717_FREQUENCIES_HZ:
        raise ValueError("Rw requires all 16 nominal bands from 100 to 3150 Hz; no interpolation.")
    return tuple(float(value) for value in values[selected])


def _validated_spectrum(frequencies_hz: ArrayLike, values_db: ArrayLike
                        ) -> tuple[np.ndarray, np.ndarray]:
    try:
        # Inspect elements before a float cast can erase imaginary parts or
        # silently turn numeric strings and mixed booleans into real numbers.
        frequencies_raw = np.asarray(frequencies_hz, dtype=object)
        values_raw = np.asarray(values_db, dtype=object)
        for raw in (frequencies_raw, values_raw):
            if any(not isinstance(value, Real) or isinstance(value, (bool, np.bool_))
                   for value in raw.flat):
                raise ValueError("Only real numbers are accepted; no booleans, strings or complex values.")
        frequencies = frequencies_raw.astype(float)
        values = values_raw.astype(float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Frequencies and reduction indices must be arrays of real numbers.") from exc
    if frequencies.ndim != 1 or values.ndim != 1:
        raise ValueError("Frequencies and reduction indices must be one-dimensional.")
    if frequencies.shape != values.shape:
        raise ValueError("Each frequency must have exactly one reduction index.")
    if not np.all(np.isfinite(frequencies)) or not np.all(np.isfinite(values)):
        raise ValueError("Frequencies and reduction indices must all be finite.")
    if np.any(np.diff(frequencies) <= 0):
        raise ValueError("Frequencies must be unique and strictly increasing.")
    return frequencies, values


def _tenths(values: Sequence[float]) -> tuple[int, ...]:
    # Decimal's integral rounding avoids binary floating-point comparisons at
    # exactly 32.0 dB. Expressed decimal halves are rounded away from zero.
    return tuple(
        int((Decimal(str(value)) * 10).to_integral_value(rounding=ROUND_HALF_UP))
        for value in values
    )


def iso717_rw(
    frequencies_hz: ArrayLike,
    reduction_index_db: ArrayLike,
) -> RwResult:
    """Fit the highest integer-shift reference satisfying the 32 dB limit.

    Supplied indices are reduced to one decimal place before fitting, with
    decimal halves rounded away from zero. Work is performed in integer
    tenths so an exact 32.0 dB deficit is accepted without numeric tolerance.
    """
    measured = _tenths(select_iso717_bands(frequencies_hz, reduction_index_db))
    margins = tuple(value - 10 * reference for value, reference in zip(
        measured, ISO717_REFERENCE_DB, strict=True
    ))

    def deficit(shift: int) -> int:
        return sum(max(0, 10 * shift - margin) for margin in margins)

    # At the lower bound every band lies above the reference. One band alone
    # exceeds the allowance at the exclusive upper bound. Monotonicity then
    # permits a short binary search, including arbitrarily low/high spectra.
    low = min(margins) // 10
    high = (min(margins) + 320) // 10 + 1
    while high - low > 1:
        candidate = (low + high) // 2
        if deficit(candidate) <= 320:
            low = candidate
        else:
            high = candidate

    return RwResult(
        rw_db=ISO717_REFERENCE_DB[7] + low,
        reference_curve_db=tuple(float(value + low) for value in ISO717_REFERENCE_DB),
        unfavorable_deviation_db=deficit(low) / 10.0,
    )


def legacy_stc(frequencies_hz: ArrayLike, transmission_loss_db: ArrayLike) -> StcResult:
    """Fit the highest whole-dB contour satisfying sum ≤ 32 and each ≤ 8 dB.

    Requires all 16 nominal 1/3-octave bands from 125 to 4000 Hz. Additional
    nominal 50, 63, 80, 100 and 5000 Hz bands are validated but excluded.
    There is no interpolation. TL is rounded to integer dB, with decimal
    halves away from zero; returned deficits refer to that rounded spectrum.

    Method reference: INSUL 10 User Guide, SoundInsulationTheory/Ratings-Airborne/
    (accessed 2026-10-15). That guide describes a legacy 8 dB rule, while its
    bibliography names E413-16. This function therefore identifies its actual
    procedure instead of declaring equivalence to a normative edition.
    """
    frequencies, values = _validated_spectrum(frequencies_hz, transmission_loss_db)
    allowed = (50.0, 63.0, 80.0, 100.0, *STC_FREQUENCIES_HZ, 5000.0)
    if not np.all(np.isin(frequencies, allowed)):
        raise ValueError("STC accepts nominal third-octave bands from 50 to 5000 Hz.")
    selected = np.isin(frequencies, STC_FREQUENCIES_HZ)
    if tuple(frequencies[selected]) != STC_FREQUENCIES_HZ:
        raise ValueError("STC requires all 16 nominal bands from 125 to 4000 Hz; no interpolation.")
    measured = tuple(int(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))
                     for value in values[selected])
    margins = tuple(value - reference for value, reference in zip(
        measured, STC_REFERENCE_DB, strict=True
    ))

    def deficits(shift: int) -> tuple[int, ...]:
        return tuple(max(0, shift - margin) for margin in margins)

    low = min(margins)  # No deficit at this lower bound.
    high = low + 9  # At least one band exceeds the individual 8 dB limit.
    while high - low > 1:
        candidate = (low + high) // 2
        deviations = deficits(candidate)
        if sum(deviations) <= 32 and max(deviations) <= 8:
            low = candidate
        else:
            high = candidate
    deviations = deficits(low)
    return StcResult(
        stc=low,
        reference_curve_db=tuple(float(value + low) for value in STC_REFERENCE_DB),
        unfavorable_deviation_db=float(sum(deviations)),
        maximum_deviation_db=float(max(deviations)),
    )
