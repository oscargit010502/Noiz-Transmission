"""Analytical building blocks for element airborne sound transmission, in SI units.

The mass-law functions describe an infinite, perfectly limp, passive sheet between
identical semi-infinite air spaces. They exclude bending stiffness, coincidence,
damping, finite size, leaks, framing and flanking transmission. Their diffuse
average is an energy average over incident angles up to the declared cutoff;
78 degrees is a modeling choice, not a fitted or experimentally validated value.

Critical frequency and mass-air-mass resonance are separate idealized diagnostics.
They do not turn the mass-law spectrum into a plate or double-leaf prediction.
These functions calculate element transmission loss R (also called TL), not
room-to-room level differences or impact sound insulation.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]

THIRD_OCTAVE_NOMINAL_HZ: FloatArray = np.array(
    [100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
     1600, 2000, 2500, 3150, 4000, 5000],
    dtype=np.float64,
)
THIRD_OCTAVE_NOMINAL_HZ.setflags(write=False)

_DB_PER_NEPER = 10.0 / math.log(10.0)


def _positive_scalar(value: float, name: str) -> float:
    """Reject invalid physical scalars instead of silently clipping them."""
    array = np.asarray(value)
    if array.ndim != 0 or array.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a finite positive scalar")
    try:
        number = float(array)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite positive scalar") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive scalar")
    return number


def _real_array(values: ArrayLike, name: str) -> FloatArray:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain finite real numbers")
    # Preserve the strict scalar domain for Python sequences: NumPy would
    # otherwise silently turn [100, True] into an integer frequency array.
    if isinstance(values, (list, tuple)) and any(
        isinstance(item, (bool, np.bool_))
        for item in np.asarray(values, dtype=object).flat
    ):
        raise ValueError(f"{name} must contain finite real numbers, not booleans")
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain finite real numbers") from exc
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain finite real numbers")
    return array


def _positive_result_from_log(log_value: float, name: str) -> float:
    try:
        result = math.exp(log_value)
    except OverflowError as exc:
        raise ValueError(f"{name} is outside the representable positive range") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} is outside the representable positive range")
    return result


def _mass_law_log_x_squared(
    frequencies_hz: ArrayLike,
    surface_density_kg_m2: float,
    air_density_kg_m3: float,
    sound_speed_m_s: float,
) -> FloatArray:
    frequencies = _real_array(frequencies_hz, "frequencies_hz")
    if np.any(frequencies <= 0):
        raise ValueError("frequencies_hz must be positive")
    mass = _positive_scalar(surface_density_kg_m2, "surface_density_kg_m2")
    density = _positive_scalar(air_density_kg_m3, "air_density_kg_m3")
    speed = _positive_scalar(sound_speed_m_s, "sound_speed_m_s")
    # Logarithms avoid overflow in f*m and x**2 for otherwise valid inputs.
    return np.asarray(2.0 * (
        math.log(math.pi) + np.log(frequencies) + math.log(mass)
        - math.log(density) - math.log(speed)
    ))


def surface_density(density_kg_m3: float, thickness_m: float) -> float:
    """Return areal mass m' = density * thickness, in kg/m²."""
    density = _positive_scalar(density_kg_m3, "density_kg_m3")
    thickness = _positive_scalar(thickness_m, "thickness_m")
    result = density * thickness
    if not math.isfinite(result) or result <= 0:
        raise ValueError("surface density is outside the representable positive range")
    return result


def mass_law_normal_tl(
    frequencies_hz: ArrayLike,
    surface_density_kg_m2: float,
    air_density_kg_m3: float = 1.21,
    sound_speed_m_s: float = 343.0,
) -> FloatArray:
    """Return normal-incidence TL in dB: 10 log10[1 + (πfm'/(ρc))²].

    This exact limp-sheet expression approaches zero at low frequency. It does
    not apply the high-frequency approximation 20 log10(f m') minus a constant.
    Input frequency shape is preserved, including a scalar as a 0-D array.
    """
    log_x_squared = _mass_law_log_x_squared(
        frequencies_hz, surface_density_kg_m2, air_density_kg_m3, sound_speed_m_s,
    )
    return np.asarray(_DB_PER_NEPER * np.logaddexp(0.0, log_x_squared))


def mass_law_diffuse_tl(
    frequencies_hz: ArrayLike,
    surface_density_kg_m2: float,
    air_density_kg_m3: float = 1.21,
    sound_speed_m_s: float = 343.0,
    limiting_angle_deg: float = 78.0,
) -> FloatArray:
    """Return TL of a normalized, angular energy average of the limp-sheet model.

    For x = πfm'/(ρc), τ(θ) = 1/(1 + x² cos²θ). The diffuse transmission
    coefficient is ∫₀^θmax τ(θ) 2 sinθ cosθ dθ / sin²θmax, or analytically
    ln[(1+x²)/(1+x² cos²θmax)] / (x² sin²θmax). Thus a perfectly transmitting
    sheet has zero TL for every cutoff. Angles must lie in (0, 90] degrees.

    The integral is evaluated in logarithmic form, with a weak-sheet expansion
    to avoid cancellation. No correction for coincidence or structural losses
    is included, and the average is over energy, not arithmetic dB values.
    """
    log_x_squared = _mass_law_log_x_squared(
        frequencies_hz, surface_density_kg_m2, air_density_kg_m3, sound_speed_m_s,
    )
    angle = _positive_scalar(limiting_angle_deg, "limiting_angle_deg")
    if angle > 90:
        raise ValueError("limiting_angle_deg must be in (0, 90]")
    radians = math.radians(angle)
    sine = math.sin(radians)
    if sine == 0:
        raise ValueError("limiting_angle_deg is too small to represent in radians")
    log_cos_squared = -math.inf if angle == 90 else 2.0 * math.log(math.cos(radians))
    log_denominator = np.logaddexp(0.0, log_x_squared + log_cos_squared)
    # t = x² sin²θmax / (1+x² cos²θmax); τ̄ = [ln(1+t)/t] / denominator.
    log_t = np.asarray(log_x_squared + 2.0 * math.log(sine) - log_denominator)
    log_ratio = np.empty_like(log_t)
    small = log_t < -18.0
    t_small = np.exp(log_t[small])
    log_ratio[small] = -0.5 * t_small + (5.0 / 24.0) * t_small**2
    log_ratio[~small] = np.log(np.logaddexp(0.0, log_t[~small])) - log_t[~small]
    return np.asarray(_DB_PER_NEPER * (log_denominator - log_ratio))


def critical_frequency(
    density_kg_m3: float,
    thickness_m: float,
    young_modulus_pa: float,
    poisson_ratio: float,
    sound_speed_m_s: float = 343.0,
) -> float:
    """Return thin, homogeneous isotropic plate critical frequency in Hz.

    f_c = c²/(2π) sqrt(m'/D), D = E h³/[12(1-ν²)]. Isotropic elastic stability
    requires E > 0 and -1 < ν < 0.5. This is a diagnostic frequency, not a
    coincidence correction to the mass-law spectrum.
    """
    density = _positive_scalar(density_kg_m3, "density_kg_m3")
    thickness = _positive_scalar(thickness_m, "thickness_m")
    modulus = _positive_scalar(young_modulus_pa, "young_modulus_pa")
    speed = _positive_scalar(sound_speed_m_s, "sound_speed_m_s")
    ratio_array = _real_array(poisson_ratio, "poisson_ratio")
    if ratio_array.ndim != 0:
        raise ValueError("poisson_ratio must be a scalar in (-1, 0.5)")
    ratio = float(ratio_array)
    if not -1.0 < ratio < 0.5:
        raise ValueError("poisson_ratio must be in (-1, 0.5) for isotropic elastic stability")
    log_frequency = (
        2.0 * math.log(speed) - math.log(2.0 * math.pi) - math.log(thickness)
        + 0.5 * (math.log(12.0) + math.log(density) + math.log1p(-ratio * ratio)
                 - math.log(modulus))
    )
    return _positive_result_from_log(log_frequency, "critical frequency")


def mass_air_mass_resonance(
    mass_1_kg_m2: float,
    mass_2_kg_m2: float,
    cavity_depth_m: float,
    air_density_kg_m3: float = 1.21,
    sound_speed_m_s: float = 343.0,
) -> float:
    """Return ideal air-spring resonance of two uncoupled limp leaves, in Hz.

    f₀ = sqrt[(ρc²/d)(1/m₁' + 1/m₂')]/(2π). Assumes a sealed, uniform cavity
    in the long-wavelength limit, with no structural connections. This scalar
    diagnostic does not predict the TL of a double-leaf construction.
    """
    mass_1 = _positive_scalar(mass_1_kg_m2, "mass_1_kg_m2")
    mass_2 = _positive_scalar(mass_2_kg_m2, "mass_2_kg_m2")
    depth = _positive_scalar(cavity_depth_m, "cavity_depth_m")
    density = _positive_scalar(air_density_kg_m3, "air_density_kg_m3")
    speed = _positive_scalar(sound_speed_m_s, "sound_speed_m_s")
    log_inverse_mass_sum = float(np.logaddexp(-math.log(mass_1), -math.log(mass_2)))
    log_frequency = (
        0.5 * (math.log(density) + 2.0 * math.log(speed) - math.log(depth)
               + log_inverse_mass_sum) - math.log(2.0 * math.pi)
    )
    return _positive_result_from_log(log_frequency, "mass-air-mass resonance")


def tl_to_tau(transmission_loss_db: ArrayLike) -> FloatArray:
    """Convert finite passive-sheet TL ≥ 0 dB to power coefficient 0 < τ ≤ 1.

    Values whose positive transmission coefficient underflows float64 raise
    ValueError; they are not silently clipped to zero.
    """
    loss = _real_array(transmission_loss_db, "transmission_loss_db")
    if np.any(loss < 0):
        raise ValueError("transmission_loss_db must be nonnegative for a passive element")
    tau = np.asarray(np.exp(-loss / _DB_PER_NEPER))
    if np.any(tau == 0):
        raise ValueError("transmission coefficient is outside the representable positive range")
    return tau


def tau_to_tl(transmission_coefficient: ArrayLike) -> FloatArray:
    """Convert passive power transmission coefficient 0 < τ ≤ 1 to finite TL dB."""
    tau = _real_array(transmission_coefficient, "transmission_coefficient")
    if np.any((tau <= 0) | (tau > 1)):
        raise ValueError("transmission_coefficient must be in (0, 1] for a passive element")
    return np.asarray(-_DB_PER_NEPER * np.log(tau))
