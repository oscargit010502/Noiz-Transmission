"""Airborne transmission through up to four thin plates and sealed gas gaps.

This is an independently derived thin-plate / plane-wave transfer-matrix model,
not an implementation of INSUL's prediction methods. By default the plates are
infinite. Optional FinitePanel parameters add the Davy angular size correction
and explicit edge loss, but do not resolve finite modes or support conditions.
Shear deformation, frame bridges, flanking and impact excitation are excluded.
Each gas cavity conserves the exterior tangential wavenumber, including
evanescent propagation and the finite critical-angle matrix limit. An optional
porous facing lies on the incident side. A porous slab can also stand alone.
Optional porous fill uses Miki's empirical rigid-frame equivalent fluid, with a
warning for extrapolation beyond 0.01 < f/sigma < 1 (sigma in Pa*s/m²). Source:
Miki 1990, J. Acoust. Soc. Jpn. (E) 11(1), equations 30–34 as reproduced by
Phonometry 3.3.0; coefficients rounded to 0.070, 0.107, 0.109 and 0.160.

With the e**(j*omega*t) convention, a plate has series impedance
Zp = j*omega*m' - j*D*(1+j*eta)*kt**4/omega; hence Re(Zp) >= 0.
Pressure and normal particle velocity are continuous through an air layer, with
matrix [[cos(kz*d), j*Zn*sin(kz*d)], [j*sin(kz*d)/Zn, cos(kz*d)]].
Transmission is 4/abs(A+B/Zn+C*Zn+D)**2 between identical air half spaces.

Band results use exact base-10 third-octave edges, *uniform incident power per
Hz*, and an energy (not dB) angular average. A band centre input must be one of
NOMINAL_BANDS_HZ. ``narrowband_tau`` accepts arbitrary positive frequencies.
"""

from __future__ import annotations

import cmath
import math
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from threading import Event

import numpy as np
from numpy.polynomial.legendre import leggauss
from numpy.typing import ArrayLike, NDArray
from scipy.integrate import IntegrationWarning, quad
from scipy.optimize import brentq, minimize_scalar

from noiz_transmission.core.finite_panel import FinitePanel
from noiz_transmission.core.physics import (
    _positive_scalar,
    _real_array,
    mass_law_diffuse_tl,
)

FloatArray = NDArray[np.float64]

MODEL_ID = "transfer-matrix-plate-1"
NOMINAL_BANDS_HZ = np.array(
    [50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500,
     630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000],
    dtype=float,
)
EXACT_BAND_CENTRES_HZ = 1000.0 * 10.0 ** (np.arange(-13, 8) / 10.0)
NOMINAL_BANDS_HZ.setflags(write=False)
EXACT_BAND_CENTRES_HZ.setflags(write=False)


class NumericalConvergenceError(ValueError):
    """The requested band integration did not meet its numerical tolerance."""


class MikiExtrapolationWarning(UserWarning):
    """The empirical porous-fluid fit is used outside 0.01 < f/sigma < 1."""


def _nonnegative(value: float, name: str) -> float:
    raw = _real_array(value, name)
    if raw.ndim != 0 or float(raw) < 0:
        raise ValueError(f"{name} must be a finite nonnegative scalar")
    return float(raw)


@dataclass(frozen=True)
class Plate:
    """A thin plate; D=0 is an ideal limp sheet, not a rigid plate.

    For a homogeneous isotropic plate D=E*h**3/[12*(1-nu**2)] in N*m.
    Loss factor is the nonnegative structural hysteretic loss of bending.
    Optional finite_size adds explicit edge loss and a Davy diffuse cutoff;
    it does not replace the plane-wave impedance with a finite modal solution.
    """

    mass_kg_m2: float
    bending_stiffness_nm: float = 0.0
    loss_factor: float = 0.0
    finite_size: FinitePanel | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mass_kg_m2", _positive_scalar(self.mass_kg_m2, "mass_kg_m2"))
        object.__setattr__(self, "bending_stiffness_nm", _nonnegative(
            self.bending_stiffness_nm, "bending_stiffness_nm",
        ))
        object.__setattr__(self, "loss_factor", _nonnegative(self.loss_factor, "loss_factor"))
        if self.finite_size is not None:
            if not isinstance(self.finite_size, FinitePanel):
                raise ValueError("finite_size must be a FinitePanel or None")
            self.finite_size.total_loss_factor(self.loss_factor)

    @property
    def effective_loss_factor(self) -> float:
        return self.loss_factor + (self.finite_size.edge_loss_factor if self.finite_size else 0)


@dataclass(frozen=True)
class Gap:
    """A sealed cavity with optional centred porous fill and no structural bridge.

    Explicit gas density and sound speed override only this cavity. None uses
    the exterior air values. Custom gas cannot be combined with Miki fill.
    The absorber is a homogeneous isotropic rigid-frame Miki equivalent fluid;
    any residual air space is split equally on its two sides. This idealisation
    cannot represent a mechanically coupled core or an attached resilient layer.
    """

    depth_m: float
    flow_resistivity_pa_s_m2: float | None = None
    absorber_thickness_m: float = 0.0
    gas_density_kg_m3: float | None = None
    gas_sound_speed_m_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "depth_m", _positive_scalar(self.depth_m, "depth_m"))
        if self.flow_resistivity_pa_s_m2 is not None:
            object.__setattr__(self, "flow_resistivity_pa_s_m2", _positive_scalar(
                self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2",
            ))
        thickness = _nonnegative(self.absorber_thickness_m, "absorber_thickness_m")
        if thickness > self.depth_m:
            raise ValueError("absorber_thickness_m cannot exceed depth_m")
        if (thickness > 0) != (self.flow_resistivity_pa_s_m2 is not None):
            raise ValueError("Porous fill requires both positive thickness and flow resistivity")
        object.__setattr__(self, "absorber_thickness_m", thickness)

        if (self.gas_density_kg_m3 is None) != (self.gas_sound_speed_m_s is None):
            raise ValueError("Gas requires both density and sound speed")
        if self.gas_density_kg_m3 is not None:
            object.__setattr__(self, "gas_density_kg_m3", _positive_scalar(
                self.gas_density_kg_m3, "gas_density_kg_m3"))
            object.__setattr__(self, "gas_sound_speed_m_s", _positive_scalar(
                self.gas_sound_speed_m_s, "gas_sound_speed_m_s"))
            if thickness > 0:
                raise ValueError("Miki porous fill is calibrated for air, not a custom cavity gas")


@dataclass(frozen=True)
class PorousLayer:
    """Homogeneous rigid-frame Miki layer in air, attached on the incident side.

    A zero thickness layer is exactly absent; its positive resistivity is retained
    for editing. The mechanical skeleton does not transmit a structural load.
    """

    thickness_m: float
    flow_resistivity_pa_s_m2: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "thickness_m", _nonnegative(self.thickness_m, "thickness_m"))
        object.__setattr__(self, "flow_resistivity_pa_s_m2", _positive_scalar(
            self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2"))


def ideal_gas_properties(
    gas: str, *, temperature_c: float = 20.0, pressure_pa: float = 101325.0,
) -> tuple[float, float]:
    """Return ideal-gas density (kg/m³) and adiabatic sound speed (m/s).

    rho=p*M/(R*T), c=sqrt(gamma*R*T/M), R=8.31446261815324 J/(mol K).
    M: dry air 28.96546, Ar 39.948, Kr 83.798, Xe 131.293 g/mol;
    gamma=1.4 for air and 5/3 for the monatomic noble gases. These are pure,
    ideal, dry gases; no mixtures, thermal boundary losses or temperature gradient.
    The exterior medium is independent of this cavity-property helper.
    """
    molar_masses = {"air": 0.02896546, "argon": 0.039948,
                    "krypton": 0.083798, "xenon": 0.131293}
    if not isinstance(gas, str) or gas not in molar_masses:
        raise ValueError("gas must be air, argon, krypton or xenon")
    temperature = _real_array(temperature_c, "temperature_c")
    if temperature.ndim != 0 or float(temperature) <= -273.15:
        raise ValueError("temperature_c must be a finite scalar above absolute zero")
    pressure = _positive_scalar(pressure_pa, "pressure_pa")
    thermal_energy = 8.31446261815324 * (float(temperature) + 273.15)
    mass = molar_masses[gas]
    gamma = 1.4 if gas == "air" else 5 / 3
    return pressure * mass / thermal_energy, math.sqrt(gamma * thermal_energy / mass)


def _assembly(plates: Sequence[Plate], gaps: Sequence[Gap]) -> tuple[tuple, tuple]:
    plates, gaps = tuple(plates), tuple(gaps)
    if not 1 <= len(plates) <= 4 or len(gaps) != len(plates) - 1:
        raise ValueError("Provide one to four plates and exactly one gap between each pair")
    if not all(isinstance(plate, Plate) for plate in plates):
        raise ValueError("plates must contain Plate objects")
    if not all(isinstance(gap, Gap) for gap in gaps):
        raise ValueError("gaps must contain Gap objects")
    finite = [plate.finite_size is not None for plate in plates]
    if any(finite) and not all(finite):
        raise ValueError("All plates must use finite_size, or all must use the infinite model")
    if all(finite):
        dimensions = {tuple(sorted((plate.finite_size.width_m, plate.finite_size.height_m)))
                      for plate in plates}
        if len(dimensions) != 1:
            raise ValueError("Finite plates must share common width and height")
    return plates, gaps


def miki_valid_frequency_range(flow_resistivity_pa_s_m2: float) -> tuple[float, float]:
    """Return open empirical-fit frequency bounds in Hz; not a validation claim."""
    sigma = _positive_scalar(flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2")
    return 0.01 * sigma, sigma


def miki_characteristics(
    frequencies_hz: ArrayLike,
    flow_resistivity_pa_s_m2: float,
    *,
    air_density: float = 1.21,
    sound_speed: float = 343.0,
) -> tuple[NDArray[np.complex128], NDArray[np.complex128]]:
    """Return characteristic impedance (Pa*s/m) and wavenumber (rad/m).

    This helper evaluates the published empirical formula, including outside its
    fitted frequency interval. The prediction functions emit an extrapolation
    warning; callers of this helper should check ``miki_valid_frequency_range``.
    With e**(j*omega*t), a forward damped wave has Im(k) < 0.
    """
    frequencies = _real_array(frequencies_hz, "frequencies_hz")
    if np.any(frequencies <= 0):
        raise ValueError("frequencies_hz must be positive")
    sigma = _positive_scalar(flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2")
    density = _positive_scalar(air_density, "air_density")
    speed = _positive_scalar(sound_speed, "sound_speed")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        y = frequencies / sigma
        impedance = density * speed * (1 + (0.070 - 0.107j) * y**-0.632)
        wave_number = 2 * np.pi * frequencies / speed * (1 + (0.109 - 0.160j) * y**-0.618)
    if np.any(~np.isfinite(impedance)) or np.any(~np.isfinite(wave_number)):
        raise ValueError("Miki calculation exceeds the representable numerical range")
    return np.asarray(impedance), np.asarray(wave_number)


def _warn_miki_extrapolation(
    frequencies: FloatArray, gaps: tuple[Gap, ...], facing: PorousLayer | None = None,
) -> None:
    if facing is not None and facing.thickness_m > 0:
        lower, upper = miki_valid_frequency_range(facing.flow_resistivity_pa_s_m2)
        if np.any(frequencies <= lower) or np.any(frequencies >= upper):
            warnings.warn(
                f"Facing/porous layer: Miki fit is extrapolated outside "
                f"{lower:g} < f < {upper:g} Hz; uncertainty is unquantified",
                MikiExtrapolationWarning, stacklevel=3,
            )
    for index, gap in enumerate(gaps):
        if gap.flow_resistivity_pa_s_m2 is not None:
            lower, upper = miki_valid_frequency_range(gap.flow_resistivity_pa_s_m2)
            if np.any(frequencies <= lower) or np.any(frequencies >= upper):
                warnings.warn(
                    f"Cavity {index + 1}: Miki fit is extrapolated outside "
                    f"{lower:g} < f < {upper:g} Hz; uncertainty is unquantified",
                    MikiExtrapolationWarning, stacklevel=3,
                )


def _coefficients(
    frequencies: FloatArray,
    sine_squared: FloatArray,
    plates: tuple[Plate, ...],
    gaps: tuple[Gap, ...],
    density: float,
    speed: float,
    facing: PorousLayer | None = None,
) -> tuple:
    """Broadcasted internal calculation, normalized by exterior wave impedance."""
    with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
        omega = 2 * np.pi * frequencies
        cosine = np.sqrt(1 - sine_squared)
        air_impedance = density * speed / cosine
        tangential_fourth = (omega / speed) ** 4 * sine_squared**2
        a, b, c, d = 1.0 + 0j, 0j, 0j, 1.0 + 0j
        def fluid_layer(thickness, z_characteristic, k, matched_exterior=False):
            nonlocal a, b, c, d
            if matched_exterior:
                phase = omega / speed * cosine * thickness
                co, js = np.cos(phase), 1j * np.sin(phase)
                a, b, c, d = (a * co + b * js, a * js + b * co,
                               c * co + d * js, c * js + d * co)
                return
            # The branch has Im(kz)<=0 for exp(j*omega*t); ratios cancel the
            # branch sign in the matrix. sinc gives the finite critical-angle
            # limit kz -> 0 without an infinity times zero product.
            kz = np.sqrt(np.asarray(k**2 - (omega / speed)**2 * sine_squared, dtype=complex))
            kz = np.where(kz.imag > 0, -kz, kz)
            phase = kz * thickness
            co = np.cos(phase)
            sin_over_kz = thickness * np.sinc(phase / np.pi)
            upper = 1j * z_characteristic * k * sin_over_kz / air_impedance
            lower = 1j * kz**2 * sin_over_kz * air_impedance / (z_characteristic * k)
            a, b, c, d = (a * co + b * lower, a * upper + b * co,
                           c * co + d * lower, c * upper + d * co)

        def porous_layer(thickness, sigma):
            z, k = miki_characteristics(frequencies, sigma,
                                       air_density=density, sound_speed=speed)
            fluid_layer(thickness, z, k)

        if facing is not None and facing.thickness_m > 0:
            porous_layer(facing.thickness_m, facing.flow_resistivity_pa_s_m2)
        for index, plate in enumerate(plates):
            stiffness = plate.bending_stiffness_nm * (1 + 1j * plate.effective_loss_factor)
            impedance = (
                1j * omega * plate.mass_kg_m2 - 1j * stiffness * tangential_fourth / omega
            ) / air_impedance
            # Right multiply by the sheet; b and c are normalized by Zn and 1/Zn.
            b, d = a * impedance + b, c * impedance + d
            if index < len(gaps):
                gap = gaps[index]
                gas_density = density if gap.gas_density_kg_m3 is None else gap.gas_density_kg_m3
                gas_speed = speed if gap.gas_sound_speed_m_s is None else gap.gas_sound_speed_m_s
                if gap.absorber_thickness_m > 0:
                    residual = (gap.depth_m - gap.absorber_thickness_m) / 2
                    fluid_layer(residual, density * speed, omega / speed, matched_exterior=True)
                    porous_layer(gap.absorber_thickness_m, gap.flow_resistivity_pa_s_m2)
                    fluid_layer(residual, density * speed, omega / speed, matched_exterior=True)
                else:
                    fluid_layer(gap.depth_m, gas_density * gas_speed, omega / gas_speed,
                                matched_exterior=(gas_density == density and gas_speed == speed))
    return a, b, c, d


def _angular_coefficients(
    frequency: float, plates: tuple[Plate, ...], gaps: tuple[Gap, ...],
    density: float, speed: float, facing: PorousLayer | None = None,
) -> Callable:
    """Prepare frequency-only terms once for a resonance-resolved angular integral.

    Root bracketing evaluates hundreds of scalar angles at the same frequency.
    Revalidating and recomputing each porous medium at every angle dominated the
    solver cost. This kernel keeps the exact transfer matrices and uses scalar
    complex arithmetic for roots, broadcasting NumPy for integration batches.
    Its lifetime is one frequency evaluation; no cross-project mutable cache.
    """
    omega = 2 * math.pi * frequency
    air_k = omega / speed
    air_z = density * speed
    layers = []
    porous_media = {}

    def fluid(thickness, z, k, matched=False):
        if thickness > 0:
            layers.append(("air" if matched else "fluid", thickness, z, k))

    def porous(thickness, sigma):
        if sigma not in porous_media:
            z, k = miki_characteristics(np.asarray(frequency), sigma,
                                       air_density=density, sound_speed=speed)
            porous_media[sigma] = complex(z), complex(k)
        fluid(thickness, *porous_media[sigma])

    if facing is not None and facing.thickness_m > 0:
        porous(facing.thickness_m, facing.flow_resistivity_pa_s_m2)
    for index, plate in enumerate(plates):
        stiffness = plate.bending_stiffness_nm * (1 + 1j * plate.effective_loss_factor)
        layers.append(("plate", 1j * omega * plate.mass_kg_m2 / air_z,
                       -1j * stiffness * air_k**4 / (omega * air_z), 0))
        if index < len(gaps):
            gap = gaps[index]
            if gap.absorber_thickness_m > 0:
                residual = (gap.depth_m - gap.absorber_thickness_m) / 2
                fluid(residual, air_z, air_k, True)
                porous(gap.absorber_thickness_m, gap.flow_resistivity_pa_s_m2)
                fluid(residual, air_z, air_k, True)
            else:
                rho = density if gap.gas_density_kg_m3 is None else gap.gas_density_kg_m3
                c = speed if gap.gas_sound_speed_m_s is None else gap.gas_sound_speed_m_s
                fluid(gap.depth_m, rho * c, omega / c, rho == density and c == speed)

    def coefficients(sine_squared):
        scalar = isinstance(sine_squared, (float, int, np.floating))
        u = float(sine_squared) if scalar else np.asarray(sine_squared)
        cosine = math.sqrt(1 - u) if scalar else np.sqrt(1 - u)
        a, b, c, d = 1.0 + 0j, 0j, 0j, 1.0 + 0j
        # Equal products/gaps occur repeatedly in Triple/Quad assemblies.
        # At a fixed angle their matrices are identical; evaluate trigonometry
        # and porous propagation once per distinct layer, then multiply.
        matrices = {}
        for layer in layers:
            kind, first, second, third = layer
            if kind == "plate":
                impedance = (first + second * u**2) * cosine
                b, d = a * impedance + b, c * impedance + d
                continue
            if layer in matrices:
                co, upper, lower = matrices[layer]
            elif kind == "air":
                phase = air_k * cosine * first
                co = math.cos(phase) if scalar else np.cos(phase)
                upper = lower = 1j * (math.sin(phase) if scalar else np.sin(phase))
            else:
                kz_squared = third**2 - air_k**2 * u
                kz = cmath.sqrt(kz_squared) if scalar else np.sqrt(kz_squared + 0j)
                phase = kz * first
                co = cmath.cos(phase) if scalar else np.cos(phase)
                # cos(kz*d) and sin(kz*d)/kz are even in kz: either root
                # gives the same matrix, including the evanescent branch.
                if scalar:
                    sin_over_kz = (first * (1 - phase**2 / 6 + phase**4 / 120)
                                   if abs(phase) < 1e-8 else cmath.sin(phase) / kz)
                else:
                    sin_over_kz = first * np.sinc(phase / np.pi)
                upper = 1j * second * third * sin_over_kz * cosine / air_z
                lower = 1j * kz_squared * sin_over_kz * air_z / (cosine * second * third)
            matrices[layer] = co, upper, lower
            a, b, c, d = (a * co + b * lower, a * upper + b * co,
                           c * co + d * lower, c * upper + d * co)
        return a, b, c, d

    return coefficients


def _tau_from_coefficients(coefficients: tuple) -> FloatArray:
    a, b, c, d = coefficients
    with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
        result = np.asarray(4 / np.abs(a + b + c + d) ** 2, dtype=float)
    if np.any(~np.isfinite(result)) or np.any(result <= 0):
        raise ValueError("Transfer calculation exceeds the representable numerical range")
    if np.any(result > 1 + 1e-9):
        raise ValueError("Transfer calculation violates passivity; inputs exceed numerical accuracy")
    return np.minimum(result, 1.0)


def _tau(
    frequencies: FloatArray, sine_squared: FloatArray, plates: tuple[Plate, ...],
    gaps: tuple[Gap, ...], density: float, speed: float,
    facing: PorousLayer | None = None,
) -> FloatArray:
    return _tau_from_coefficients(
        _coefficients(frequencies, sine_squared, plates, gaps, density, speed, facing),
    )


def narrowband_tau(
    frequencies_hz: ArrayLike,
    plates: Sequence[Plate],
    gaps: Sequence[Gap] = (),
    *,
    incidence_angle_deg: float = 0.0,
    air_density: float = 1.21,
    sound_speed: float = 343.0,
    facing: PorousLayer | None = None,
) -> FloatArray:
    """Return narrowband power transmission at one angle, preserving input shape.

    Angles are measured from the normal and must be in [0, 90) degrees.
    """
    plates, gaps = _assembly(plates, gaps)
    if facing is not None and not isinstance(facing, PorousLayer):
        raise ValueError("facing must be a PorousLayer or None")
    frequencies = _real_array(frequencies_hz, "frequencies_hz")
    if np.any(frequencies <= 0):
        raise ValueError("frequencies_hz must be positive")
    angle = _nonnegative(incidence_angle_deg, "incidence_angle_deg")
    if angle >= 90:
        raise ValueError("incidence_angle_deg must be in [0, 90)")
    density = _positive_scalar(air_density, "air_density")
    speed = _positive_scalar(sound_speed, "sound_speed")
    _warn_miki_extrapolation(frequencies, gaps, facing)
    return _tau(frequencies, np.asarray(math.sin(math.radians(angle)) ** 2),
                plates, gaps, density, speed, facing)


@lru_cache(maxsize=12)
def _nodes(order: int) -> tuple[FloatArray, FloatArray]:
    nodes, weights = leggauss(order)
    # Both frequency and sin²(theta) are uniform normalized power integration variables.
    nodes, weights = (nodes + 1) / 2, weights / 2
    nodes.setflags(write=False)
    weights.setflags(write=False)
    return nodes, weights


def _angular_domain(frequencies, plates, user_limit, speed):
    """Davy finite aperture: truncate the integral without renormalising it."""
    limit = np.asarray(user_limit)
    finite = bool(plates and plates[0].finite_size is not None)
    if finite:
        for plate in plates:
            limit = np.minimum(limit, plate.finite_size.davy_sine_squared_limit(frequencies, speed))
    return limit, 1.0 if finite else user_limit


def _band_tau(
    centre: float, plates: tuple[Plate, ...], gaps: tuple[Gap, ...],
    density: float, speed: float, sine_squared_limit: float,
    angular_order: int, frequency_order: int,
    facing: PorousLayer | None = None,
) -> float:
    f_nodes, f_weights = _nodes(frequency_order)
    lower, upper = centre * 10 ** (-1 / 20), centre * 10 ** (1 / 20)
    frequencies = lower + (upper - lower) * f_nodes
    if sine_squared_limit == 0:
        result = _tau(frequencies, np.asarray(0.0), plates, gaps, density, speed, facing)
    else:
        a_nodes, a_weights = _nodes(angular_order)
        limit, normalization = _angular_domain(frequencies, plates, sine_squared_limit, speed)
        result = (_tau(frequencies[:, None], np.asarray(limit)[..., None] * a_nodes,
                       plates, gaps, density, speed, facing) @ a_weights) * limit / normalization
    return float(result @ f_weights)


def _adaptive_band_tau(
    centre: float, plates: tuple[Plate, ...], gaps: tuple[Gap, ...],
    density: float, speed: float, sine_squared_limit: float, relative_tolerance: float = 1e-4,
    cancel_event: Event | None = None,
    facing: PorousLayer | None = None,
) -> float:
    lower, upper = centre * 10 ** (-1 / 20), centre * 10 ** (1 / 20)
    with warnings.catch_warnings():
        warnings.simplefilter("error", IntegrationWarning)
        try:
            return _resonance_resolved_band_tau(
                lower, upper, plates, gaps, density, speed,
                sine_squared_limit, relative_tolerance, cancel_event, facing,
            )
        except IntegrationWarning as exc:
            raise NumericalConvergenceError("Adaptive band energy integration did not converge") from exc


def _resonance_points(
    lower: float, upper: float, coefficients: Callable, samples: int,
) -> list[float]:
    """Bracket resonances and seed their local widths, independently of integration nodes.

    Both Im(reflection numerator) and Im(transmission denominator) are examined.
    Agreement of two unseeded quadrature grids is NOT a convergence criterion for
    a narrow cavity mode: both grids can miss its entire transmitted energy.
    """
    if samples > 8193:
        raise NumericalConvergenceError("Too many cavity resonances for reliable bracketing")
    grid = np.linspace(lower, upper, samples)
    a, b, c, d = coefficients(grid)
    functions = (lambda v: np.asarray(sum(coefficients(v)).imag),
                 lambda v: np.asarray((lambda a, b, c, d: a + b - c - d)(*coefficients(v)).imag))
    roots = []
    for function, values in zip(functions, ((a + b + c + d).imag, (a + b - c - d).imag),
                                 strict=True):
        crossings = np.flatnonzero(np.signbit(values[:-1]) != np.signbit(values[1:]))
        for index in crossings:
            roots.append(brentq(function, grid[index], grid[index + 1], xtol=1e-13))
        # Coupled cavities produce close pairs of modes. Their two roots can
        # fall inside one sample interval with identical endpoint signs. Locate
        # intervening extrema independently, then bracket on each side of them.
        differences = np.diff(values)
        turning = np.flatnonzero(differences[:-1] * differences[1:] < 0) + 1
        for index in turning:
            direction = 1 if differences[index - 1] < 0 else -1
            extremum = minimize_scalar(
                lambda value: direction * float(function(value)),
                bounds=(grid[index - 1], grid[index + 1]), method="bounded",
                options={"xatol": (upper - lower) * 1e-13},
            )
            if not extremum.success:
                raise NumericalConvergenceError("Coupled-mode extremum could not be resolved")
            pivot = extremum.x
            pivot_value = float(function(pivot))
            for endpoint in (grid[index - 1], grid[index + 1]):
                if np.signbit(float(function(endpoint))) != np.signbit(pivot_value):
                    roots.append(brentq(function, min(endpoint, pivot), max(endpoint, pivot),
                                         xtol=1e-13))
    points = list(roots)
    # Endpoints also need neighborhoods if a resonance falls just outside the band.
    for root in [lower, *roots, upper]:
        delta = (upper - lower) * 1e-6
        left, right = max(lower, root - delta), min(upper, root + delta)
        denominator = sum(coefficients(np.asarray([left, root, right])))
        derivative = abs((denominator[2] - denominator[0]) / (right - left))
        if derivative > 0:
            width = abs(denominator[1]) / derivative
            if width <= (upper - lower) * 1e-15:
                raise NumericalConvergenceError("Resonance linewidth exceeds floating-point resolution")
            # Resolve Lorentzian tails too: stopping at 64 linewidths can leave
            # a narrow, non-negligible tail at the end of a huge next interval.
            multiplier = 1.0
            while multiplier * width < 4 * (upper - lower):
                for direction in (-1, 1):
                    point = root + direction * multiplier * width
                    if lower < point < upper:
                        points.append(point)
                multiplier *= 4
    ordered = sorted(point for point in points if lower < point < upper)
    unique = []
    for point in ordered:
        if not unique or point - unique[-1] > (upper - lower) * 1e-12:
            unique.append(point)
    return unique


def _resonance_resolved_band_tau(
    lower: float, upper: float, plates: tuple[Plate, ...], gaps: tuple[Gap, ...],
    density: float, speed: float, sine_squared_limit: float, relative_tolerance: float,
    cancel_event: Event | None = None,
    facing: PorousLayer | None = None,
) -> float:
    """Resolve resonances before adaptive energy integration in both dimensions.

    Normal incidence explicitly brackets frequency resonances. For diffuse
    incidence the angular integrand is segmented at each resonance and its local
    linewidth; frequency breakpoints mark modes entering/exiting the angular
    domain. The root search is independent of quadrature order and its sample
    count scales with the number of cavity wavelengths.
    """
    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ValueError("Cálculo cancelado")

    check_cancelled()
    travel_time = sum(gap.depth_m / (gap.gas_sound_speed_m_s or speed) for gap in gaps)
    if facing is not None:
        travel_time += facing.thickness_m / speed
    frequency_samples = max(129, 32 * math.ceil(2 * (upper - lower) * travel_time) + 1)

    def frequency_average(u: float) -> float:
        check_cancelled()

        def coefficients(f):
            return _coefficients(np.asarray(f), np.asarray(u), plates, gaps, density, speed, facing)

        points = _resonance_points(lower, upper, coefficients, frequency_samples)
        edges = np.asarray([lower, *points, upper])
        widths = np.diff(edges)
        previous = None
        # These grids are applied separately to each root/linewidth segment.
        # Unlike an unseeded whole-band grid, each narrow resonance is sampled.
        for order in (16, 32, 64):
            nodes, weights = _nodes(order)
            frequencies = edges[:-1, None] + widths[:, None] * nodes
            integral = float(np.sum((_tau(frequencies, np.asarray(u), plates, gaps,
                                          density, speed, facing) @ weights) * widths))
            if previous is not None and abs(integral - previous) <= integral * relative_tolerance / 5:
                break
            previous = integral
        else:
            integral, error = quad(
                lambda f: float(_tau(np.asarray(f), np.asarray(u), plates, gaps, density, speed, facing)),
                lower, upper, points=points, epsabs=1e-24,
                epsrel=relative_tolerance / 5, limit=max(400, len(points) * 3),
            )
            if integral <= 0 or error > integral * relative_tolerance * 2:
                raise NumericalConvergenceError("Frequency resonances did not converge")
        return integral / (upper - lower)

    if sine_squared_limit == 0:
        return frequency_average(0.0)
    if (len(plates) == 1 and plates[0].bending_stiffness_nm == 0
            and plates[0].finite_size is None
            and (facing is None or facing.thickness_m == 0)):
        # The exact angular limp-sheet integral also handles the grazing limit.
        def limp_power(frequency):
            check_cancelled()
            loss = mass_law_diffuse_tl(
                frequency, plates[0].mass_kg_m2, density, speed,
                math.degrees(math.asin(math.sqrt(sine_squared_limit))),
            )
            return float(10 ** (-loss / 10))

        value, error = quad(limp_power, lower, upper, epsabs=1e-24, epsrel=relative_tolerance)
        if value <= 0 or error > value * relative_tolerance * 10:
            raise NumericalConvergenceError("Limp-sheet band integration failed")
        return value / (upper - lower)
    # The exact grazing endpoint has zero measure; coefficients use its limiting side.
    angular_samples = max(257, 32 * math.ceil(2 * upper * travel_time) + 1)

    def angular_average(frequency: float) -> float:
        check_cancelled()

        coefficients = _angular_coefficients(frequency, plates, gaps, density, speed, facing)

        angular_limit, normalization = _angular_domain(frequency, plates, sine_squared_limit, speed)
        angular_limit = float(angular_limit)
        points = _resonance_points(0, min(angular_limit, 1 - 1e-12), coefficients, angular_samples)
        edges = np.asarray([0, *points, angular_limit])
        widths = np.diff(edges)
        previous = None
        for order in (16, 32, 64):
            nodes, weights = _nodes(order)
            angles = edges[:-1, None] + widths[:, None] * nodes
            integral = float(np.sum((_tau_from_coefficients(coefficients(angles)) @ weights) * widths))
            if previous is not None and abs(integral - previous) <= integral * relative_tolerance / 5:
                break
            previous = integral
        else:
            integral, error = quad(
                lambda u: float(_tau_from_coefficients(coefficients(u))),
                0, angular_limit, points=points, epsabs=1e-24,
                epsrel=relative_tolerance / 5, limit=max(400, len(points) * 3),
            )
            if integral <= 0 or error > integral * relative_tolerance * 2:
                raise NumericalConvergenceError("Angular resonances did not converge")
        return integral / normalization

    frequency_points = []
    # Davy's cap and the user's truncation introduce continuous derivative
    # changes. Seed them explicitly rather than relying on sampled discovery.
    size_scale = 0.0
    for plate in plates:
        if plate.finite_size is not None:
            geometry = plate.finite_size
            log_scale = (math.log(speed) - math.log(8 * math.pi)
                         + float(np.logaddexp(math.log(2) - math.log(geometry.width_m),
                                              math.log(2) - math.log(geometry.height_m))))
            if log_scale < math.log(upper):
                size_scale = max(size_scale, math.exp(log_scale))
            for cos_squared in (.9, 1 - sine_squared_limit):
                if cos_squared > 0:
                    log_transition = log_scale - math.log(cos_squared)
                    if math.log(lower) < log_transition < math.log(upper):
                        frequency_points.append(math.exp(log_transition))
    for boundary in ("normal", "limit"):
        def coefficients(f):
            u = 0.0 if boundary == "normal" else np.minimum(
                _angular_domain(f, plates, sine_squared_limit, speed)[0], 1 - 1e-12,
            )
            return _coefficients(np.asarray(f), np.asarray(u), plates, gaps, density, speed, facing)

        frequency_points.extend(_resonance_points(lower, upper, coefficients, frequency_samples))
    # Critical-frequency onsets are additional changes in resonance topology.
    for plate in plates:
        if plate.bending_stiffness_nm > 0:
            critical = speed**2 / (2 * math.pi) * math.sqrt(plate.mass_kg_m2 / plate.bending_stiffness_nm)
            for frequency in (critical, critical / sine_squared_limit, critical + size_scale):
                if lower < frequency < upper:
                    frequency_points.append(frequency)
    integral, error = quad(
        angular_average, lower, upper, points=sorted(set(frequency_points)),
        epsabs=1e-24, epsrel=relative_tolerance, limit=max(400, len(frequency_points) * 3),
    )
    if integral <= 0 or error > integral * relative_tolerance * 10:
        raise NumericalConvergenceError("Frequency average of resolved angular resonances failed")
    return integral / (upper - lower)


def predict_multilayer(
    plates: Sequence[Plate],
    gaps: Sequence[Gap] = (),
    *,
    frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21,
    sound_speed: float = 343.0,
    incidence: str = "diffuse",
    angle_limit_deg: float = 78.0,
    quadrature_tolerance_db: float = 0.05,
    cancel_event: Event | None = None,
    facing: PorousLayer | None = None,
) -> FloatArray:
    """Return third-octave element TL, with convergence-checked energy integration.

    Incidence is ``normal`` or ``diffuse``. Legacy infinite diffuse weight is
    2*sin(theta)*cos(theta)/sin(theta_max)**2. FinitePanel uses the Davy upper
    angular limit and unnormalised 2*sin(theta)*cos(theta), also truncated at
    the user limit. The 78° default is a modelling choice, not a universal
    laboratory correction. Finite parameters do not add modal dynamics or
    structural frame coupling. Incident power is uniform
    per Hz within each exact third-octave band. This spectrum is not the value
    at its nominal band centres. Input order and shape are preserved.

    Resonances are bracketed independently of integration grids using transfer
    and reflection phases. Their local linewidths seed angular and frequency
    intervals; local Gauss-Legendre integration and adaptive quadrature then
    resolve those intervals. Agreement of unseeded whole-band grids is never
    used as proof of convergence. An explicit NumericalConvergenceError is raised
    if integration fails. ``quadrature_tolerance_db`` allocates the numerical
    error-estimate budget, with separate inner and outer targets. This is not
    a rigorous error bound or experimental accuracy claim. Extremely sharp
    undamped resonances may not converge. ``cancel_event`` permits cooperative
    cancellation between integration evaluations and raises ValueError when set.
    """
    plates, gaps = _assembly(plates, gaps)
    return _predict_bands(
        plates, gaps, frequencies_hz=frequencies_hz, air_density=air_density,
        sound_speed=sound_speed, incidence=incidence, angle_limit_deg=angle_limit_deg,
        quadrature_tolerance_db=quadrature_tolerance_db, cancel_event=cancel_event, facing=facing,
    )


def predict_porous_layer(
    layer: PorousLayer,
    *,
    frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21,
    sound_speed: float = 343.0,
    incidence: str = "diffuse",
    angle_limit_deg: float = 78.0,
    quadrature_tolerance_db: float = 0.05,
    cancel_event: Event | None = None,
) -> FloatArray:
    """Third-octave transmission of an unbacked rigid-frame Miki slab in air.

    This predicts transmitted power, not the rigid-backed absorption coefficient.
    A zero thickness returns zero TL. Band averaging and numerical controls are
    identical to ``predict_multilayer``; there is no fictitious bounding plate.
    """
    if not isinstance(layer, PorousLayer):
        raise ValueError("layer must be a PorousLayer")
    return _predict_bands(
        (), (), frequencies_hz=frequencies_hz, air_density=air_density,
        sound_speed=sound_speed, incidence=incidence, angle_limit_deg=angle_limit_deg,
        quadrature_tolerance_db=quadrature_tolerance_db, cancel_event=cancel_event, facing=layer,
    )


def _predict_bands(
    plates: tuple[Plate, ...], gaps: tuple[Gap, ...], *, frequencies_hz: ArrayLike,
    air_density: float, sound_speed: float, incidence: str, angle_limit_deg: float,
    quadrature_tolerance_db: float, cancel_event: Event | None, facing: PorousLayer | None,
) -> FloatArray:
    if facing is not None and not isinstance(facing, PorousLayer):
        raise ValueError("facing must be a PorousLayer or None")
    nominal = _real_array(frequencies_hz, "frequencies_hz")
    centres = []
    for frequency in nominal.flat:
        matching = np.flatnonzero(NOMINAL_BANDS_HZ == frequency)
        if matching.size != 1:
            raise ValueError("frequencies_hz must use supported nominal third-octave bands 50–5000")
        centres.append(EXACT_BAND_CENTRES_HZ[matching[0]])
    density = _positive_scalar(air_density, "air_density")
    speed = _positive_scalar(sound_speed, "sound_speed")
    tolerance = _positive_scalar(quadrature_tolerance_db, "quadrature_tolerance_db")
    if tolerance > 0.1:
        raise ValueError("quadrature_tolerance_db cannot exceed 0.1 dB")
    if incidence not in ("normal", "diffuse"):
        raise ValueError("incidence must be 'normal' or 'diffuse'")
    angle = _positive_scalar(angle_limit_deg, "angle_limit_deg")
    if angle > 90:
        raise ValueError("angle_limit_deg must be in (0, 90]")
    sine_squared = 0.0 if incidence == "normal" else math.sin(math.radians(angle)) ** 2
    _warn_miki_extrapolation(np.asarray([min(centres) * 10 ** (-1 / 20),
                                       max(centres) * 10 ** (1 / 20)]), gaps, facing)
    if cancel_event is not None and cancel_event.is_set():
        raise ValueError("Cálculo cancelado")
    if not plates and (facing is None or facing.thickness_m == 0):
        return np.zeros_like(nominal)
    result = []
    for nominal_frequency, centre in zip(nominal.flat, centres, strict=True):
        try:
            coefficient = _adaptive_band_tau(
                centre, plates, gaps, density, speed, sine_squared,
                # Reserve ten parts for outer frequency integration and two
                # for the inner angular estimator. These are numerical error
                # estimates, not an experimental accuracy or rigorous bound.
                -math.expm1(-tolerance * math.log(10) / 10) / 12, cancel_event, facing,
            )
        except NumericalConvergenceError as exc:
            raise NumericalConvergenceError(
                f"Band {nominal_frequency:g} Hz did not converge: {exc}",
            ) from exc
        result.append(-10 * math.log10(coefficient))
    return np.asarray(result).reshape(nominal.shape)
