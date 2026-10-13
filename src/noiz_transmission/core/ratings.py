"""Provisional airborne Rw reference-curve calculation for element spectra.

This implements the 16-band, integer-shift procedure described by ISO 717-1
(100–3150 Hz, at most 32 dB total unfavorable deviation). It is a numerical
rating of the supplied spectrum, not certification of a construction or a
replacement for laboratory measurement. Predicted spectra yield indicative Rw.

The reference data and rounding convention are independently cross-checked
against Phonometry 3.3.0, ``phonometry.building.weighted_rating`` (MIT):
https://github.com/jmrplens/phonometry . No external implementation is copied.
No STC, impact rating, adaptation term, or room-to-room calculation is implied.
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
    try:
        # Inspect elements before a float cast can erase imaginary parts or
        # silently turn numeric strings and mixed booleans into real numbers.
        frequencies_raw = np.asarray(frequencies_hz, dtype=object)
        values_raw = np.asarray(reduction_index_db, dtype=object)
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
    allowed = (*ISO717_FREQUENCIES_HZ, 4000.0, 5000.0)
    if not np.all(np.isin(frequencies, allowed)):
        raise ValueError("Use nominal ISO 717 bands from 100–3150 Hz, optionally 4000/5000 Hz.")
    selected = np.isin(frequencies, ISO717_FREQUENCIES_HZ)
    if tuple(frequencies[selected]) != ISO717_FREQUENCIES_HZ:
        raise ValueError("Rw requires all 16 nominal bands from 100 to 3150 Hz; no interpolation.")
    return tuple(float(value) for value in values[selected])


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
