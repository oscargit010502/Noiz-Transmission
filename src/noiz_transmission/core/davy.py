"""Davy single/double-wall engineering estimates from Bies et al., 6th edition.

This independent implementation follows chapter 7 equations 7.49–7.107 and
mechanical-radiation expressions in section 4.15. A forced-radiation reference
from chapter 6 equation 6.91 is provided separately. It is not Strutt's code and does not imply Strutt's
validation or an experimental error margin. The double-wall expressions are
band-centre engineering estimates, not a coherent multilayer transfer matrix.
All mechanical quantities use SI; the empirical steel ``gauge`` variable is
exceptionally the numerical gauge coordinate of the published regression.
Its convention is not specified in the consulted textbook and is reported as
an explicit unresolved calibration assumption whenever used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from threading import Event

import numpy as np
from numpy.typing import ArrayLike, NDArray

from noiz_transmission.core.finite_panel import FinitePanel
from noiz_transmission.core.physics import _positive_scalar, _real_array
from noiz_transmission.core.transfer import (
    NOMINAL_BANDS_HZ,
    Plate,
    miki_characteristics,
    predict_multilayer,
)

DAVY_MODEL_ID = "davy-single-double-1"
FloatArray = NDArray[np.float64]
_SECTIONS = {"TC": 1.0, "AWS": 3.39, "LR": 1.96, "S": .98, "O": .73}


def _frequencies(value: ArrayLike) -> FloatArray:
    frequency = _real_array(value, "frequencies_hz")
    if np.any(frequency <= 0):
        raise ValueError("frequencies_hz must be positive")
    return frequency


def _nonnegative(value: float, name: str) -> float:
    raw = _real_array(value, name)
    if raw.ndim or float(raw) < 0:
        raise ValueError(f"{name} must be a finite nonnegative scalar")
    return float(raw)


def _cancel(event: Event | None) -> None:
    if event is not None:
        if not isinstance(event, Event):
            raise ValueError("cancel_event must be a threading.Event")
        if event.is_set():
            raise ValueError("Cálculo cancelado")


def _plate_values(plate: Plate, speed: float) -> tuple[float, float, float]:
    if not isinstance(plate, Plate) or plate.bending_stiffness_nm <= 0:
        raise ValueError("Davy requires a Plate with positive bending stiffness")
    eta = _positive_scalar(plate.effective_loss_factor, "effective panel loss factor")
    fc = speed**2 / (2 * math.pi) * math.sqrt(
        plate.mass_kg_m2 / plate.bending_stiffness_nm,
    )
    return plate.mass_kg_m2, fc, eta


@dataclass(frozen=True)
class DavyStud:
    """Declared shared support, or mechanically independent leaves.

    Timber uses rigid point connections (CM=0). Steel accepts explicit point
    and line compliances in their different SI units; the gauge regression is
    available only through an explicitly supplied gauge coordinate. Auto steel
    switches from line to point attachment when screw spacing exceeds one
    quarter of the shorter leaf bending wavelength (Hansen p.436).
    """

    kind: str = "independent"
    spacing_m: float = .6
    fastener_spacing_m: float = .3
    attachment: str = "auto"
    steel_gauge: float | None = None
    steel_section: str = "TC"
    point_compliance_m_n: float | None = None
    line_compliance_m2_n: float | None = None

    def __post_init__(self):
        if self.kind not in ("independent", "timber", "steel"):
            raise ValueError("kind must be independent, timber or steel")
        if self.attachment not in ("auto", "point", "line"):
            raise ValueError("attachment must be auto, point or line")
        if self.kind == "timber" and self.attachment == "line":
            raise ValueError("The consulted Davy model specifies point connections for timber")
        if self.steel_section not in _SECTIONS:
            raise ValueError("steel_section must be TC, AWS, LR, S or O")
        for key in ("spacing_m", "fastener_spacing_m"):
            object.__setattr__(self, key, _positive_scalar(getattr(self, key), key))
        if self.steel_gauge is not None:
            object.__setattr__(self, "steel_gauge", _positive_scalar(self.steel_gauge, "steel_gauge"))
        for key in ("point_compliance_m_n", "line_compliance_m2_n"):
            value = getattr(self, key)
            if value is not None:
                object.__setattr__(self, key, _nonnegative(value, key))
        if self.kind == "steel" and all(value is None for value in (
            self.steel_gauge, self.point_compliance_m_n, self.line_compliance_m2_n,
        )):
            raise ValueError("Steel requires explicit connection compliance or a declared gauge coordinate")


@dataclass(frozen=True)
class DavyResult:
    frequencies_hz: tuple[float, ...]
    tl_db: tuple[float, ...]
    airborne_tau: tuple[float, ...]
    studborne_tau: tuple[float, ...]
    resonance_hz: float | None
    warnings: tuple[str, ...]


def davy_radiation_efficiency(
    frequencies_hz: ArrayLike, area_m2: float, perimeter_m: float, sound_speed: float = 343.0,
) -> FloatArray:
    """Forced radiation efficiency, Hansen eq.6.91, evaluated stably.

    This is a standalone forced-response reference; the structural connection
    path uses ``resonant_radiation_efficiency`` instead. This fitted expression
    is not extended across its low-ka singularity; invalid geometries fail.
    Radiation efficiency is a ratio and may legitimately exceed one.
    """
    f = _frequencies(frequencies_hz)
    area = _positive_scalar(area_m2, "area_m2")
    perimeter = _positive_scalar(perimeter_m, "perimeter_m")
    speed = _positive_scalar(sound_speed, "sound_speed")
    ka = 2 * np.pi * f / speed * (2 * area / perimeter)
    h_denominator = .67 * np.sqrt(2 * ka / np.pi) - .124
    if np.any(h_denominator <= 0):
        raise ValueError("Davy radiation fit is outside its positive-H domain for this panel/support size")
    h = 1 / h_denominator
    q = np.pi / (2 * ka**2)
    ff = 1.3 * np.sqrt(np.pi / (2 * ka))
    b = h / ff - 1
    difference = np.arcsinh(h / q) - np.arcsinh(ff / q)
    second = np.empty_like(f)
    small = np.abs(b) < 1e-6
    second[small] = ff[small] / np.hypot(h[small], q[small])
    second[~small] = difference[~small] / b[~small]
    result = np.arcsinh(1 / q) - np.arcsinh(ff / q) + second
    if not np.all(np.isfinite(result)) or np.any(result <= 0):
        raise ValueError("Davy radiation fit produced an invalid radiation efficiency")
    return np.asarray(result)


def steel_compliance(
    frequencies_hz: ArrayLike, *, mass1: float, mass2: float, spacing_m: float,
    fastener_spacing_m: float, steel_gauge: float, area_m2: float,
    attachment: str, section: str = "TC",
) -> FloatArray:
    """Hansen Table7.8 regression, with declared gauge/calibration assumptions.

    Returns m/N for point attachment, m²/N for line attachment. The source
    coordinate g is called 'gauge', with no convention/conversion supplied;
    thickness in metres or mm must never be substituted automatically.
    The TC data were obtained for nominal 92 mm C studs. Section factors are
    from Table7.9; they are not proprietary connection/isolator models.
    """
    f = _frequencies(frequencies_hz)
    m1, m2 = _positive_scalar(mass1, "mass1"), _positive_scalar(mass2, "mass2")
    spacing = _positive_scalar(spacing_m, "spacing_m")
    fastener = _positive_scalar(fastener_spacing_m, "fastener_spacing_m")
    gauge = _positive_scalar(steel_gauge, "steel_gauge")
    area = _positive_scalar(area_m2, "area_m2")
    if attachment not in ("point", "line") or section not in _SECTIONS:
        raise ValueError("Invalid attachment or steel section for compliance regression")
    mr = m1 * m2 / (m1 + m2)
    low = f <= 250
    if attachment == "line":
        lower = 6.07e-4 * f**-1.04 * mr**-1.4 * gauge**.666
        upper = 2.58e-4 * f**-1.52 * mr**-1.12 * spacing**-.257 * gauge**1.52
    else:
        count = 1 / (spacing * fastener)
        lower = 4.06e-5 * f**-.76 * mr**-1.96 * gauge**1.68
        upper = 4.94e-7 * f**-1.16 * mr**-1.18 * count**.747 * gauge**2.49 * area**.355
    return np.asarray(np.where(low, lower, upper) * _SECTIONS[section])


def resonant_radiation_efficiency(
    frequencies_hz: ArrayLike, critical_frequency_hz: float, first_mode_hz: float, *,
    width_m: float, height_m: float, perimeter_m: float, sound_speed: float = 343.0,
) -> FloatArray:
    """Mechanically excited plate radiation, Hansen §4.15, eqs.4.180–4.186.

    The invalid delta1 contribution is omitted following Leppington. Around
    coincidence the asymptotes are bounded by the finite critical-frequency
    value and the 5 dB practical radiation-ratio limit stated on p.243. This
    is an engineering closure of the source's unspecified transition interval.
    The low-mode interval is interpolated log-log exactly as directed there.
    """
    f = _frequencies(frequencies_hz)
    fc, f1 = _positive_scalar(critical_frequency_hz, "critical_frequency_hz"), _positive_scalar(first_mode_hz, "first_mode_hz")
    width, height = _positive_scalar(width_m, "width_m"), _positive_scalar(height_m, "height_m")
    perimeter = _positive_scalar(perimeter_m, "perimeter_m")
    c = _positive_scalar(sound_speed, "sound_speed")
    area = width * height
    cap = min(math.sqrt(2 * math.pi * fc * min(width, height) / c) / 2, 10**.5)

    def asymptote(freq):
        ratio = np.asarray(freq, dtype=float) / fc
        # Evaluate each side separately: no invalid logarithms or coincidence
        # singularities are generated on the discarded branch.
        below = ratio < 1
        out = np.full_like(ratio, cap)
        xi = np.sqrt(ratio[below])
        one_minus = 1 - xi**2
        delta2 = (one_minus * (np.log1p(xi) - np.log1p(-xi)) + 2 * xi)
        delta2 /= 4 * np.pi**2 * one_minus**1.5
        out[below] = perimeter * c / (fc * area) * delta2
        above = ratio > 1
        out[above] = 1 / np.sqrt(1 - 1 / ratio[above])
        return np.minimum(out, cap)

    result = asymptote(f)
    piston = 4 * area * f**2 / c**2
    result = np.where(f <= f1, np.minimum(piston, cap), result)
    transition = (f > f1) & (f < 2 * f1)
    if np.any(transition):
        lower = min(4 * area * f1**2 / c**2, cap)
        upper = float(asymptote(np.asarray(2 * f1)))
        fraction = np.log2(f[transition] / f1)
        result[transition] = np.exp((1 - fraction) * math.log(lower) + fraction * math.log(upper))
    return result


def point_connection_tau(
    frequencies_hz: ArrayLike, mass1: float, mass2: float, fc1: float, fc2: float,
    eta1: float, eta2: float, sigma1: ArrayLike, sigma2: ArrayLike,
    point_density_m2: float, compliance_m_n: ArrayLike,
    air_density: float = 1.21, sound_speed: float = 343.0,
) -> FloatArray:
    """Structure-borne point connection coefficient, Hansen eqs.7.93–7.94."""
    f = _frequencies(frequencies_hz)
    m1, m2, fc1, fc2, eta1, eta2, count, rho, c = (
        _positive_scalar(value, name) for value, name in zip(
            (mass1, mass2, fc1, fc2, eta1, eta2, point_density_m2, air_density, sound_speed),
            ("mass1", "mass2", "fc1", "fc2", "eta1", "eta2", "point_density_m2", "air_density", "sound_speed"),
            strict=True,
        )
    )
    s1, s2 = _real_array(sigma1, "sigma1"), _real_array(sigma2, "sigma2")
    cm = _real_array(compliance_m_n, "compliance_m_n")
    if np.any(s1 <= 0) or np.any(s2 <= 0) or np.any(cm < 0):
        raise ValueError("Radiation efficiencies must be positive and compliance nonnegative")
    q = np.pi * fc1 * s1 / (4 * f * eta1) + (f < fc1)
    r = np.pi * fc2 * s2 / (4 * f * eta2) + (f < fc2)
    denominator = np.pi**5 * f**2 * (
        (m1 * fc2 + m2 * fc1)**2 + 64 * f**2 * m1**2 * m2**2 * c**4 * cm**2
    )
    return np.asarray(16 * count * rho**2 * c**4 * q * r / denominator)


def line_connection_tau(
    frequencies_hz: ArrayLike, mass1: float, mass2: float, fc1: float, fc2: float,
    eta1: float, eta2: float, sigma1: ArrayLike, sigma2: ArrayLike,
    spacing_m: float, compliance_m2_n: ArrayLike,
    air_density: float = 1.21, sound_speed: float = 343.0,
) -> FloatArray:
    """Structure-borne line connection coefficient, Hansen eqs.7.94–7.96."""
    f = _frequencies(frequencies_hz)
    m1, m2, fc1, fc2, eta1, eta2, spacing, rho, c = (
        _positive_scalar(value, name) for value, name in zip(
            (mass1, mass2, fc1, fc2, eta1, eta2, spacing_m, air_density, sound_speed),
            ("mass1", "mass2", "fc1", "fc2", "eta1", "eta2", "spacing_m", "air_density", "sound_speed"),
            strict=True,
        )
    )
    s1, s2 = _real_array(sigma1, "sigma1"), _real_array(sigma2, "sigma2")
    cm = _real_array(compliance_m2_n, "compliance_m2_n")
    if np.any(s1 <= 0) or np.any(s2 <= 0) or np.any(cm < 0):
        raise ValueError("Radiation efficiencies must be positive and compliance nonnegative")
    q = s1 / (2 * eta1) * np.sqrt(fc1 / f) + (f < fc1)
    r = s2 / (2 * eta2) * np.sqrt(fc2 / f) + (f < fc2)
    g = m1 * math.sqrt(fc2) + m2 * math.sqrt(fc1)
    denominator = (g**2 + (8 * np.pi * f**1.5 * m1 * m2 * c * cm - g)**2)
    denominator *= spacing * np.pi**3 * f**2
    return np.asarray(8 * rho**2 * c**3 * q * r / denominator)


def _compliance(f, stud, attachment, mass1, mass2, area):
    supplied = (stud.point_compliance_m_n if attachment == "point"
                else stud.line_compliance_m2_n)
    if supplied is not None:
        return np.full_like(f, supplied)
    # A distributed line and its regularly spaced screws describe equivalent
    # compliance only under the declared uniform load-sharing assumption.
    other = (stud.line_compliance_m2_n if attachment == "point"
             else stud.point_compliance_m_n)
    if other is not None:
        return np.full_like(f, other / stud.fastener_spacing_m if attachment == "point"
                            else other * stud.fastener_spacing_m)
    return steel_compliance(f, mass1=mass1, mass2=mass2, spacing_m=stud.spacing_m,
                            fastener_spacing_m=stud.fastener_spacing_m,
                            steel_gauge=stud.steel_gauge, area_m2=area,
                            attachment=attachment, section=stud.steel_section)


def studborne_tau(
    frequencies_hz: ArrayLike, plate1: Plate, plate2: Plate, stud: DavyStud, *,
    width_m: float, height_m: float, air_density: float = 1.21, sound_speed: float = 343.0,
) -> FloatArray:
    """Shared timber/steel path; no shared path for explicitly independent leaves."""
    f = _frequencies(frequencies_hz)
    if not isinstance(stud, DavyStud):
        raise ValueError("stud must be a DavyStud")
    width, height = _positive_scalar(width_m, "width_m"), _positive_scalar(height_m, "height_m")
    rho, c = _positive_scalar(air_density, "air_density"), _positive_scalar(sound_speed, "sound_speed")
    m1, fc1, eta1 = _plate_values(plate1, c)
    m2, fc2, eta2 = _plate_values(plate2, c)
    if stud.kind == "independent":
        return np.zeros_like(f)
    area = width * height
    perimeter = 2 * (width + height) + 2 * area / stud.spacing_m
    sigmas = [resonant_radiation_efficiency(
        f, fc, math.pi / (2 * stud.spacing_m**2) * math.sqrt(plate.bending_stiffness_nm / mass),
        width_m=width, height_m=height, perimeter_m=perimeter, sound_speed=c,
    ) for plate, mass, fc in ((plate1, m1, fc1), (plate2, m2, fc2))]
    common = (f, m1, m2, fc1, fc2, eta1, eta2, *sigmas)
    if stud.kind == "timber":
        return point_connection_tau(*common, 1 / (stud.spacing_m * stud.fastener_spacing_m),
                                    0., rho, c)
    point = point_connection_tau(*common, 1 / (stud.spacing_m * stud.fastener_spacing_m),
                                _compliance(f, stud, "point", m1, m2, area), rho, c)
    line = line_connection_tau(*common, stud.spacing_m,
                              _compliance(f, stud, "line", m1, m2, area), rho, c)
    if stud.attachment == "point":
        return point
    if stud.attachment == "line":
        return line
    shorter_bending_wavelength = c / np.sqrt(f * max(fc1, fc2))
    return np.where(stud.fastener_spacing_m <= shorter_bending_wavelength / 4, line, point)


def _cos_limit(f, width, height, c, double=False):
    cosine_squared = np.minimum(.9, c / f * (2 / width + 2 / height) / (8 * np.pi))
    return np.maximum(cosine_squared, math.cos(math.radians(61))**2) if double else cosine_squared


def _mass_tau(f, mass, width, height, rho, c):
    aa = (np.pi * f * mass / (rho * c))**2
    cosine = _cos_limit(f, width, height, c)
    return np.log1p(aa * (1 - cosine) / (1 + aa * cosine)) / aa


def _result(f, air, stud, resonance, warnings):
    air, stud = np.asarray(air, dtype=float), np.asarray(stud, dtype=float)
    total = air + stud
    if np.any(~np.isfinite(total)) or np.any(total <= 0) or np.any(air < 0) or np.any(stud < 0):
        raise ValueError("Davy engineering approximation produced an invalid transmission coefficient")
    excess = total > 1
    if np.any(excess):
        warnings.append("La aproximación excede τ=1 en bandas de baja pérdida; se aplica el límite "
                        "pasivo TL=0 dB, conservando la proporción de los caminos. No es una solución modal.")
        scale = np.maximum(total, 1)
        air, stud = air / scale, stud / scale
        total = air + stud
    return DavyResult(tuple(float(x) for x in f.flat), tuple(float(x) for x in -10 * np.log10(total.flat)),
                      tuple(float(x) for x in air.flat), tuple(float(x) for x in stud.flat),
                      resonance, tuple(warnings))


def davy_single_reference_bands(
    plate: Plate, *, width_m: float, height_m: float,
    frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21, sound_speed: float = 343.0,
    thickness_m: float | None = None, longitudinal_speed_m_s: float | None = None,
    cancel_event: Event | None = None,
) -> DavyResult:
    """Hansen Davy band-centre scheme, eqs.7.67–7.72; optional thickness cap.

    The low-frequency stiffness/resonance asymptotes and published piecewise
    coincidence rules are reported as approximations, not an interpolated modal
    solver. Optional homogeneous-panel dimensions enable eqs.7.76–7.77.
    """
    _cancel(cancel_event)
    f = _frequencies(frequencies_hz)
    w, h = _positive_scalar(width_m, "width_m"), _positive_scalar(height_m, "height_m")
    rho, c = _positive_scalar(air_density, "air_density"), _positive_scalar(sound_speed, "sound_speed")
    mass, fc, eta = _plate_values(plate, c)
    mass_tau = _mass_tau(f, mass, w, h, rho, c)
    a2 = (np.pi * f * mass / (rho * c))**2
    bandwidth_ratio = 10**.05 - 10**-.05
    coincidence_tau = np.pi / (a2 * 2 * eta * bandwidth_ratio)
    high_tau = np.pi / (a2 * 2 * eta * np.maximum(f / fc - 1, np.finfo(float).tiny))
    tau = np.where(f <= .95 * fc, mass_tau, coincidence_tau)
    tau = np.where((f > .5 * fc) & (f <= .95 * fc), np.minimum(mass_tau, coincidence_tau), tau)
    tau = np.where(f >= 1.05 * fc, high_tau, tau)
    tau = np.where((f >= 1.05 * fc) & (f < 2 * fc), np.minimum(high_tau, coincidence_tau), tau)
    finite = FinitePanel(w, h)
    f11 = finite.first_mode_hz(mass, plate.bending_stiffness_nm)
    stiffness = mass * (2 * np.pi * f11)**2
    tau = np.where(f < .5 * f11, (4 * np.pi * f * rho * c / stiffness)**2, tau)
    modal = (f >= .5 * f11) & (f <= 1.5 * f11)
    resonance_tau = (rho * c / (np.pi * f11 * mass * eta))**2
    tau = np.where(modal, np.where(eta > rho * c / (2 * np.pi * f * mass), resonance_tau, 1.), tau)
    warnings = ["Single Davy: estimación por centros de tercio de octava, Hansen 7.67–7.72; "
                "los tramos publicados no constituyen una solución modal ni una mezcla ajustada con Sharp."]
    if (thickness_m is None) != (longitudinal_speed_m_s is None):
        raise ValueError("Thickness correction requires both thickness and longitudinal wave speed")
    if thickness_m is not None:
        thickness = _positive_scalar(thickness_m, "thickness_m")
        cl = _positive_scalar(longitudinal_speed_m_s, "longitudinal_speed_m_s")
        limit = math.sqrt(plate.bending_stiffness_nm / (thickness**4 * mass))
        maximum_tl = 20 * math.log10(mass * cl / (4 * rho * c * thickness)) + 10 * math.log10(eta) + 17
        tau = np.where(f > limit, np.maximum(tau, 10**(-maximum_tl / 10)), tau)
        warnings.append(f"Límite de espesor de Hansen 7.76–7.77 activo por encima de {limit:.6g} Hz; "
                        "aproximación de placa gruesa, no un solucionador completo de ondas de corte.")
    if np.any(f <= 1.5 * f11):
        warnings.append(f"Región f ≤ 1,5 f₁₁ ({1.5 * f11:.6g} Hz): asintotas de rigidez/resonancia "
                        "Hansen; dependen del apoyo simplemente apoyado y no resuelven modos individuales.")
    _cancel(cancel_event)
    return _result(f, tau, np.zeros_like(f), f11, warnings)


def davy_single_bands(
    plate: Plate, *, width_m: float, height_m: float,
    frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21, sound_speed: float = 343.0,
    thickness_m: float | None = None, longitudinal_speed_m_s: float | None = None,
    angle_limit_deg: float = 78.0, cancel_event: Event | None = None,
) -> DavyResult:
    """Finite-panel angular integration with a declared high-frequency cap.

    Uses Hansen eqs.7.49–7.57 rather than the discontinuous closed-form
    approximation 7.69–7.72. Band energy and angular integration preserve the
    previously verified adaptive integration. The thin/thick correction is a
    band-centre upper bound from eqs.7.76–7.77, not a Mindlin wave solver.
    Frequencies below 1.5*f11 retain the application's extrapolation flags;
    no empirical stitching to the separate stiffness reference is performed.
    """
    _cancel(cancel_event)
    f = _frequencies(frequencies_hz)
    w, h = _positive_scalar(width_m, "width_m"), _positive_scalar(height_m, "height_m")
    rho, c = _positive_scalar(air_density, "air_density"), _positive_scalar(sound_speed, "sound_speed")
    mass, _fc, eta = _plate_values(plate, c)
    finite = FinitePanel(w, h)
    effective = Plate(mass, plate.bending_stiffness_nm, eta, finite)
    tl = predict_multilayer((effective,), frequencies_hz=f, air_density=rho, sound_speed=c,
                           incidence="diffuse", angle_limit_deg=angle_limit_deg,
                           cancel_event=cancel_event)
    warnings = ["Single V7: integración energética de placa finita Hansen 7.49–7.57, "
                "corte angular de Davy, pérdidas declaradas y coincidencia. No es una solución modal de Sewell."]
    if (thickness_m is None) != (longitudinal_speed_m_s is None):
        raise ValueError("Thickness correction requires both thickness and longitudinal wave speed")
    if thickness_m is not None:
        thickness = _positive_scalar(thickness_m, "thickness_m")
        cl = _positive_scalar(longitudinal_speed_m_s, "longitudinal_speed_m_s")
        limit = math.sqrt(plate.bending_stiffness_nm / (thickness**4 * mass))
        maximum_tl = 20 * math.log10(mass * cl / (4 * rho * c * thickness)) + 10 * math.log10(eta) + 17
        tl = np.where(f > limit, np.minimum(tl, maximum_tl), tl)
        warnings.append(f"Límite de placa gruesa Hansen 7.76–7.77 aplicado a centros de banda > {limit:.6g} Hz. "
                        "No es un solucionador completo de ondas de corte; requiere una hoja homogénea.")
    f11 = finite.first_mode_hz(mass, plate.bending_stiffness_nm)
    if np.any(f <= 1.5 * f11):
        warnings.append(f"Por debajo de 1,5 f₁₁ ({1.5 * f11:.6g} Hz), la aproximación de placa "
                        "requiere extrapolación y no resuelve la región de rigidez ni sus modos individuales.")
    _cancel(cancel_event)
    return _result(f, 10**(-tl / 10), np.zeros_like(f), f11, warnings)


def _miki_absorption(f, thickness, sigma, rho, c):
    """Diffuse absorption of a rigidly backed porous slab, as a cavity proxy.

    This is an explicitly declared engineering substitution for alpha-bar,
    not an equation attributed to Davy or a measured cavity absorption.
    """
    nodes, weights = np.polynomial.legendre.leggauss(48)
    u, weights = (nodes + 1) / 2, weights / 2
    z, k = miki_characteristics(f[..., None], sigma, air_density=rho, sound_speed=c)
    kz = np.sqrt(k**2 - (2 * np.pi * f[..., None] / c)**2 * u + 0j)
    kz = np.where(kz.imag > 0, -kz, kz)
    surface = -1j * z * k / kz / np.tan(kz * thickness)
    exterior = rho * c / np.sqrt(1 - u)
    reflection = (surface - exterior) / (surface + exterior)
    alpha = (1 - abs(reflection)**2) @ weights
    if np.any(~np.isfinite(alpha)) or np.any(alpha <= 0) or np.any(alpha > 1 + 1e-10):
        raise ValueError("Miki cavity-absorption proxy is nonpassive or outside its numerical domain")
    return np.minimum(alpha, 1)


def davy_double_bands(
    plate1: Plate, plate2: Plate, depth_m: float, *, width_m: float, height_m: float,
    stud: DavyStud = DavyStud(), absorber_thickness_m: float = 0.0,
    cavity_absorption: float | None = None, flow_resistivity_pa_s_m2: float | None = None,
    ideal_absorber: bool = False, frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21, sound_speed: float = 343.0,
    minimum_background_absorption: float | None = None,
    cancel_event: Event | None = None,
) -> DavyResult:
    """Airborne + studborne Davy double leaf, Hansen eqs.7.88–7.107.

    Empty cavity alpha=min(.1,kd). Declared adequate mineral-fibre absorption
    >=50 mm may use alpha=min(1,kd). Other fills need an explicit cavity alpha
    or measured flow resistivity for the separately labelled Miki proxy.

    ``minimum_background_absorption`` is an opt-in engineering envelope for
    the Miki proxy used by the V7.1 automatic model. It is not a published Davy
    correction. Its default is None, preserving the saved V7 route exactly.
    """
    _cancel(cancel_event)
    f = _frequencies(frequencies_hz)
    w, h = _positive_scalar(width_m, "width_m"), _positive_scalar(height_m, "height_m")
    depth = _positive_scalar(depth_m, "depth_m")
    rho, c = _positive_scalar(air_density, "air_density"), _positive_scalar(sound_speed, "sound_speed")
    if not isinstance(stud, DavyStud):
        raise ValueError("stud must be a DavyStud")
    m1, fc1, eta1 = _plate_values(plate1, c)
    m2, fc2, eta2 = _plate_values(plate2, c)
    thickness = _nonnegative(absorber_thickness_m, "absorber_thickness_m")
    if thickness > depth:
        raise ValueError("Absorber thickness cannot exceed the cavity depth")
    if cavity_absorption is not None:
        cavity_absorption = _positive_scalar(cavity_absorption, "cavity_absorption")
        if cavity_absorption > 1:
            raise ValueError("cavity_absorption must be in (0,1]")
    if flow_resistivity_pa_s_m2 is not None:
        flow_resistivity_pa_s_m2 = _positive_scalar(flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2")
    if minimum_background_absorption is not None:
        minimum_background_absorption = _positive_scalar(
            minimum_background_absorption, "minimum_background_absorption")
        if minimum_background_absorption > 1:
            raise ValueError("minimum_background_absorption must be in (0,1]")
    if ideal_absorber and thickness < .05:
        raise ValueError("The ideal mineral-fibre cavity approximation requires at least 50 mm")
    if thickness > 0 and cavity_absorption is None and flow_resistivity_pa_s_m2 is None and not ideal_absorber:
        raise ValueError("Absorbing fill requires cavity absorption, flow resistivity, or declared adequate >=50 mm mineral fibre")
    warnings = ["Double Davy: suma energética de caminos aéreo y estructural; centros de tercios "
                "de octava según Hansen 7.88–7.107. Precisión experimental de Noiz no cuantificada."]
    if cavity_absorption is not None:
        warnings.append("Absorción media de cámara declarada explícitamente; no se obtiene del Damping del XML.")
    elif thickness and flow_resistivity_pa_s_m2:
        warnings.append("Absorción de cámara aproximada mediante absorción difusa Miki de una capa con "
                        "respaldo rígido. Esta sustitución propia de α no equivale a un ensayo de la cámara.")
        if minimum_background_absorption is not None:
            warnings.append(
                f"Envolvente de ingeniería para absorción: α=min(kd,max({minimum_background_absorption:g}, "
                "α_Miki)). Conserva la referencia de pérdidas de la cámara vacía al añadir relleno. "
                "No es una corrección publicada de Davy ni una demostración experimental."
            )
        if np.any((f / flow_resistivity_pa_s_m2 <= .01) | (f / flow_resistivity_pa_s_m2 >= 1)):
            warnings.append("Miki se extrapola fuera de 0,01 < f/σ < 1; incertidumbre no cuantificada.")
    elif thickness:
        warnings.append("Absorción ideal α=min(1,kd): hipótesis declarada de lana mineral/fibra adecuada ≥50 mm, Hansen p.437.")
    else:
        warnings.append("Cámara vacía: α=min(0,1,kd), extremo inferior del intervalo 0,1–0,15 de Hansen p.437.")
    if stud.kind == "steel":
        if stud.steel_gauge is not None and stud.point_compliance_m_n is None and stud.line_compliance_m2_n is None:
            warnings.append("Regresión de compliance de acero, tabla 7.8: 'gauge' introducido explícitamente. "
                            "El texto consultado no especifica la convención de gauge; la calibración NO está verificada. "
                            "Datos originales de montantes C de 92 mm; fuera de 63–5000 Hz se extrapola.")
        else:
            warnings.append("Compliance de unión de acero introducida explícitamente; m/N por punto y m²/N por línea. "
                            "Si falta una, se convierte suponiendo reparto uniforme a la separación de tornillos declarada.")
    if stud.kind != "independent":
        warnings.append("Perímetro radiativo incluye 2A/b de longitud de montantes, aproximación de una matriz regular. "
                        "La separación de tornillos se declara; no se infiere de la fotografía o del fabricante.")
        warnings.append("Radiación del camino estructural: respuesta resonante Hansen §4.15, ecuaciones "
                        "4.180–4.186 (δ₁ omitido); se limita por σ de coincidencia y 5 dB conforme a p.243. "
                        "Se resuelve así la referencia cruzada inconsistente a §6.8.2, que describe respuesta forzada.")
    # Eq7.89, no empirical thickness multiplier is guessed without a verified
    # calibration/gauge relation. Independent leaves have no inter-stud span.
    bending = ([math.pi / (2 * stud.spacing_m**2) * math.sqrt(p.bending_stiffness_nm / p.mass_kg_m2)
                for p in (plate1, plate2)] if stud.kind != "independent" else [0., 0.])
    fa1 = rho * c**2 / (4 * math.pi**2 * depth * m1)
    fa2 = rho * c**2 / (4 * math.pi**2 * depth * m2)
    p = -(bending[0]**2 + bending[1]**2 + fa1 + fa2)
    q = bending[0]**2 * bending[1]**2 + bending[0]**2 * fa2 + bending[1]**2 * fa1
    f0 = math.sqrt(-p / 2 + math.sqrt(max(0., p**2 - 4 * q)) / 2)
    if f0 >= .9 * min(fc1, fc2):
        raise ValueError("Davy Double requiere f₀ < 0,9 min(fc₁,fc₂). Esta combinación de "
                         "rigidez, separación y cámara está fuera del orden de regímenes del modelo.")

    def paths(frequency):
        kd = 2 * np.pi * frequency / c * depth
        if cavity_absorption is not None:
            alpha = np.minimum(kd, cavity_absorption)
        elif thickness > 0 and flow_resistivity_pa_s_m2 is not None:
            alpha = _miki_absorption(frequency, thickness, flow_resistivity_pa_s_m2, rho, c)
            if minimum_background_absorption is not None:
                alpha = np.maximum(alpha, minimum_background_absorption)
            alpha = np.minimum(kd, alpha)
        else:
            alpha = np.minimum(kd, 1. if thickness > 0 else .1)
        a1, a2 = np.pi * frequency * m1 / (rho * c), np.pi * frequency * m2 / (rho * c)
        cosine = _cos_limit(frequency, w, h, c, double=True)
        mass_ratio = (m1**2 + m2**2) / (2 * m1 * m2)
        air_low = (1 - cosine) / ((mass_ratio + a1 * a2 * alpha * cosine)
                                  * (mass_ratio + a1 * a2 * alpha))
        xi1, xi2 = np.sqrt(frequency / fc1), np.sqrt(frequency / fc2)
        q1, q2 = eta1 * xi2 + eta2 * xi1, 2 * (xi1 - xi2)
        air_high = np.pi * q1 / (2 * a1**2 * a2**2 * eta1 * eta2 * (q1**2 + q2**2) * alpha**2)
        air = np.where(frequency < .9 * min(fc1, fc2), air_low, air_high)
        structural = studborne_tau(frequency, plate1, plate2, stud, width_m=w, height_m=h,
                                  air_density=rho, sound_speed=c)
        return air, structural

    # Do not evaluate the above-resonance fitted radiation law at invalid low
    # frequencies merely to discard it afterwards.
    evaluated_f = np.maximum(f, f0)
    air, structural = paths(evaluated_f)
    low = f <= 2 * f0 / 3
    air = np.where(low, _mass_tau(f, m1 + m2, w, h, rho, c), air)
    structural = np.where(low, 0., structural)
    transition = (f > 2 * f0 / 3) & (f < f0)
    if np.any(transition):
        start_tau = float(_mass_tau(np.asarray(2 * f0 / 3), m1 + m2, w, h, rho, c))
        end_air, end_stud = paths(np.asarray(f0))
        end_tau = float(end_air + end_stud)
        weight = np.log(f[transition] / (2 * f0 / 3)) / math.log(1.5)
        total = np.exp((1 - weight) * math.log(start_tau) + weight * math.log(end_tau))
        # The handbook defines only TOTAL transmission in this transition;
        # split below is an explicitly disclosed bookkeeping convention.
        fraction = weight * float(end_stud / end_tau)
        air[transition], structural[transition] = total * (1 - fraction), total * fraction
        warnings.append("Entre 2f₀/3 y f₀, TL se interpola contra log(f), como prescribe Hansen. "
                        "El reparto entre caminos en ese tramo es contable, no una descomposición física identificable.")
    warnings.append("La transición de compliance a 250 Hz y el cambio de fórmula aérea en 0,9fc "
                    "siguen los tramos publicados; no se ocultan mediante un suavizado arbitrario.")
    _cancel(cancel_event)
    return _result(f, air, structural, f0, warnings)
