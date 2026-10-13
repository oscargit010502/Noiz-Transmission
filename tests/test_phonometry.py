"""Independent numerical checks, not evidence of experimental accuracy."""

import numpy as np
import pytest

from noiz_transmission.adapters.phonometry import phonometry_rw
from noiz_transmission.core.ratings import (
    ISO717_FREQUENCIES_HZ,
    ISO717_REFERENCE_DB,
    iso717_rw,
)

pytest.importorskip("phonometry", reason="Optional independent validation dependency")


def test_phonometry_public_api_matches_analytical_and_irregular_spectra():
    reference = np.array(ISO717_REFERENCE_DB, dtype=float)
    rng = np.random.default_rng(717)
    spectra = [
        reference,
        reference - 80,
        reference - 0.04,
        reference - 0.06,
        np.full(16, 30.0),
        np.array([1, *list(reference[1:] + 20)]),
        *rng.uniform(-10, 90, (32, 16)),
    ]
    for spectrum in spectra:
        own = iso717_rw(ISO717_FREQUENCIES_HZ, spectrum)
        external = phonometry_rw(ISO717_FREQUENCIES_HZ, spectrum)
        assert own.rw_db == external.rw_db
        assert own.unfavorable_deviation_db == pytest.approx(external.unfavorable_deviation_db)
        assert own.reference_curve_db == external.reference_curve_db
        assert external.library_version


def test_adapter_excludes_supported_extra_bands():
    external = phonometry_rw(
        [*ISO717_FREQUENCIES_HZ, 4000, 5000], [*ISO717_REFERENCE_DB, 0, 0]
    )
    assert external.rw_db == 54
    assert len(external.reference_curve_db) == 16


def test_adapter_rejects_missing_band_instead_of_inferring_a_band_set():
    with pytest.raises(ValueError, match="all 16"):
        phonometry_rw(ISO717_FREQUENCIES_HZ[:-1], ISO717_REFERENCE_DB[:-1])
