"""Finite rectangular panel parameters and published correction diagnostics.

These functions do not turn a plane-wave transfer matrix into a modal model.
The Davy angular limit reproduced by Bies et al. (2024), equations 7.56–7.57,
is a finite-size correction above 1.5 times the first panel natural frequency.
Equation 7.57 is an *unnormalised* angular integral. Replacing its upper limit
and then dividing by that limit would implement a different approximation.

Sources are recorded, with the distinction from Sewell's model, in
``docs/v6-physics.md``. All quantities use SI units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from noiz_transmission.core.physics import _positive_scalar, _real_array

FloatArray = NDArray[np.float64]
FINITE_MODEL_ID = "finite-davy-transfer-1"


def _nonnegative(value: float, name: str) -> float:
    raw = _real_array(value, name)
    if raw.ndim != 0 or float(raw) < 0:
        raise ValueError(f"{name} must be a finite nonnegative scalar")
    return float(raw)


@dataclass(frozen=True)
class FinitePanel:
    """Rectangular panel geometry and additional junction/edge loss.

    ``edge_loss_factor`` is dimensionless, nonnegative and explicitly supplied.
    Zero means that no *additional* junction loss is specified. It must not be
    added to a measured structural loss that already includes the edges.
    A measured total including radiation requires separating that contribution,
    because the transfer matrix explicitly couples the plate to the fluids.
    It is not inferred from density, manufacturer, thickness or frame names.

    The first-mode diagnostic assumes four simply supported edges. The angular
    size correction itself does not resolve the support conditions or modes.
    """

    width_m: float
    height_m: float
    edge_loss_factor: float = 0.0

    def __post_init__(self) -> None:
        for name in ("width_m", "height_m"):
            object.__setattr__(self, name, _positive_scalar(getattr(self, name), name))
        object.__setattr__(self, "edge_loss_factor", _nonnegative(
            self.edge_loss_factor, "edge_loss_factor",
        ))

    def first_mode_hz(self, mass_kg_m2: float, bending_stiffness_nm: float) -> float:
        """Simply supported f11, Bies et al. (2024), equation 7.45.

        f11 = pi/2 sqrt(D/m') (1/a² + 1/b²). A limp sheet has f11=0;
        it does not have the bending stiffness of a rigid supported plate.
        This is a diagnostic and does not add a resonance to the TL spectrum.
        """
        mass = _positive_scalar(mass_kg_m2, "mass_kg_m2")
        stiffness = _nonnegative(bending_stiffness_nm, "bending_stiffness_nm")
        if stiffness == 0:
            return 0.0
        try:
            log_geometry = np.logaddexp(-2 * math.log(self.width_m),
                                       -2 * math.log(self.height_m))
            value = math.exp(math.log(math.pi / 2) + (math.log(stiffness) - math.log(mass)) / 2
                             + log_geometry)
        except OverflowError as exc:
            raise ValueError("First panel mode is outside the representable range") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError("First panel mode is outside the representable range")
        return value

    def davy_sine_squared_limit(
        self, frequencies_hz: ArrayLike, sound_speed: float = 343.0,
    ) -> FloatArray:
        """Return sin²(theta_L) using Bies et al. (2024), equation 7.56.

        cos²(theta_L) = min(0.9, lambda * P / (8*pi*A)). For a rectangle,
        P/A = 2/a + 2/b. This stable form avoids multiplying two lengths.
        The result is in [0.1, 1]. This is Davy's finite-size angular limit,
        not Sewell's low-frequency solution or the user's field cutoff.
        """
        frequencies = _real_array(frequencies_hz, "frequencies_hz")
        if np.any(frequencies <= 0):
            raise ValueError("frequencies_hz must be positive")
        speed = _positive_scalar(sound_speed, "sound_speed")
        # Evaluate the capped expression in log space, also for very small
        # geometries or frequencies, without overflow or accidental NaNs.
        log_perimeter_over_area = np.logaddexp(
            math.log(2) - math.log(self.width_m), math.log(2) - math.log(self.height_m),
        )
        log_cos_squared = (math.log(speed) - np.log(frequencies)
                           + log_perimeter_over_area - math.log(8 * math.pi))
        cos_squared = np.exp(np.minimum(math.log(0.9), log_cos_squared))
        return np.asarray(1 - cos_squared)

    def total_loss_factor(self, internal_loss_factor: float) -> float:
        """Add independent material and specified edge loss, equation 11.75.

        No extra radiation term is included here: the transfer model explicitly
        loads the sheet with the fluids. A measured effective *structural* loss
        (material plus mounting, radiation excluded) should use edge_loss_factor=0.
        A total measured loss including radiation cannot be substituted without
        assessing and separating that contribution (Bies et al., p. 714).
        """
        internal = _nonnegative(internal_loss_factor, "internal_loss_factor")
        total = internal + self.edge_loss_factor
        if not math.isfinite(total):
            raise ValueError("Total loss factor is outside the representable range")
        return total

    def stiffness_asymptote_tl(
        self,
        frequencies_hz: ArrayLike,
        mass_kg_m2: float,
        bending_stiffness_nm: float,
        *,
        air_density: float = 1.21,
        sound_speed: float = 343.0,
    ) -> FloatArray:
        """Low-frequency single-plate reference, Bies et al. (2024), eq. 7.67.

        TL = 20 log10[s/(4*pi*f*rho*c)] with
        s = pi**4*D*(1/a**2 + 1/b**2)**2, for f < 0.5*f11.

        This is the published stiffness asymptote for a simply supported plate,
        not a continuous modal prediction or a correction for several leaves.
        It is deliberately separate from the transfer spectrum. Inputs outside
        its stated frequency domain, or yielding negative asymptotic TL, are
        rejected instead of clipping them or blending to another model.
        Near unity impedance ratio its asymptotic approximation is weak; no
        experimental accuracy is implied by returning a positive result.
        """
        frequencies = _real_array(frequencies_hz, "frequencies_hz")
        if np.any(frequencies <= 0):
            raise ValueError("frequencies_hz must be positive")
        fundamental = self.first_mode_hz(mass_kg_m2, bending_stiffness_nm)
        if np.any(frequencies >= 0.5 * fundamental):
            raise ValueError("Stiffness asymptote requires f < 0.5*f11")
        density = _positive_scalar(air_density, "air_density")
        speed = _positive_scalar(sound_speed, "sound_speed")
        # s = m*(2*pi*f11)**2. Work in log space rather than forming s,
        # which could overflow for inputs whose TL remains representable.
        log_stiffness = (math.log(mass_kg_m2)
                         + 2 * (math.log(2 * math.pi) + math.log(fundamental)))
        log_ratio = (log_stiffness - math.log(4 * math.pi) - np.log(frequencies)
                     - math.log(density) - math.log(speed))
        if np.any(log_ratio < 0):
            raise ValueError("Stiffness asymptote is not valid at this fluid impedance ratio")
        return np.asarray(20 / math.log(10) * log_ratio)
