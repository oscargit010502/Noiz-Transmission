"""Independent numerical cross-check through Phonometry's public API.

Tested with Phonometry 3.3.0 (MIT), published at
https://pypi.org/project/phonometry/3.3.0/ . Matching another implementation
checks the rating algorithm only; it does not experimentally validate a model.
"""

from dataclasses import dataclass
from importlib.metadata import version

from numpy.typing import ArrayLike

from noiz_transmission.core.ratings import select_iso717_bands


@dataclass(frozen=True)
class PhonometryRwResult:
    """Independent rating result with the installed dependency version."""

    rw_db: int
    reference_curve_db: tuple[float, ...]
    unfavorable_deviation_db: float
    library_version: str


def phonometry_rw(
    frequencies_hz: ArrayLike,
    reduction_index_db: ArrayLike,
) -> PhonometryRwResult:
    """Calculate indicative Rw using optional Phonometry, without interpolation.

    Validation and band selection are shared with Noiz; numerical rounding
    and the complete curve-fit calculation are performed by Phonometry.
    """
    values = select_iso717_bands(frequencies_hz, reduction_index_db)
    try:
        from phonometry.building import weighted_rating
    except ImportError as exc:
        raise ImportError(
            "The independent Rw check requires Phonometry; install the project's "
            "validation dependencies."
        ) from exc
    result = weighted_rating(values, bands="third-octave")
    return PhonometryRwResult(
        rw_db=int(result.rating),
        reference_curve_db=tuple(float(value) for value in result.shifted_reference),
        unfavorable_deviation_db=float(result.unfavourable_sum),
        library_version=version("phonometry"),
    )
