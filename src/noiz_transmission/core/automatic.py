"""Automatic Double estimate: Davy airborne plus a Sharp rigid bridge path.

This is an explicitly combined engineering approximation, not a reproduction
of INSUL or a new calibration of Davy. The airborne path retains the Davy
finite-size and cavity-absorption treatment. The rigid structural path uses
Sharp (1978), equations 4, 20, 22–24. Neither a material name nor a thin steel
section determines connection compliance, so this model does not invent one.

Equation 24 is Sharp's *design approximation*, not an algebraic simplification
of equations 21–22 (the two differ even for identical leaves). A continuous
stud flange is a line contact even when attached with discrete screws. The
point-on-one-leaf case needs an actual discrete contact geometry; independent
frames have no shared bridge. See docs/v71-reference-review.md.

The below-resonance response is the total-mass airborne approximation only.
The bridge asymptote is added above the physical mass–air–mass resonance;
Hansen's logarithmic interpolation convention is applied using the combined
model's endpoint. This endpoint is an extension, not a published hybrid formula.
Thus the same mass-controlled response is never counted as two paths.
"""

from __future__ import annotations

import math
from threading import Event

import numpy as np
from numpy.typing import ArrayLike, NDArray

from noiz_transmission.core.davy import (
    DavyResult,
    DavyStud,
    _cancel,
    _frequencies,
    _mass_tau,
    _plate_values,
    _result,
    davy_double_bands,
)
from noiz_transmission.core.physics import _positive_scalar
from noiz_transmission.core.transfer import NOMINAL_BANDS_HZ, Plate

AUTOMATIC_MODEL_ID = "davy-air-sharp-bridge-1"
_BRIDGES = {"none", "line", "point", "point_pair"}


def sharp_bridge_tl(
    frequencies_hz: ArrayLike, mass1: float, mass2: float, fc1: float, fc2: float,
    *, spacing_m: float, connection: str = "line", point_supported_panel: int = 2,
) -> NDArray[np.float64]:
    """Sharp's rigid bridge-dominated TL, with SI masses and spacing.

    ``line`` is the published design approximation (24), using the *other*
    leaf's mass relative to the leaf with the highest critical frequency.
    For coincident critical frequencies and unequal masses, the lower-TL
    choice is used: this conservative tie policy prevents orientation changing
    the result, but is not an extra measured correction.

    ``point`` is equation 23, with a point contact on the specified leaf and
    line contact on the other. ``point_pair`` is equations 20 and 22 with the
    two point impedances of equation 17; it is reciprocal without choosing a
    receiving side. Spacing for point cases is the side of an equivalent square
    lattice, sqrt(horizontal_spacing * vertical_spacing), not the stud width.

    The standard-air mass law is equation 4 (20 log10(m f) - 48). These are
    asymptotes, not a resolved coincidence or thick-plate structural solver.
    In particular they may be negative outside their useful low-TL regime;
    passivity is enforced when combining complete transmission coefficients.
    """
    f = _frequencies(frequencies_hz)
    m1, m2, critical1, critical2, spacing = (
        _positive_scalar(value, name) for value, name in (
            (mass1, "mass1"), (mass2, "mass2"), (fc1, "fc1"), (fc2, "fc2"),
            (spacing_m, "spacing_m"),
        )
    )
    if connection not in _BRIDGES - {"none"}:
        raise ValueError("connection must be line, point or point_pair")
    if type(point_supported_panel) is not int or point_supported_panel not in (1, 2):
        raise ValueError("point_supported_panel must be 1 or 2")
    mass_total = m1 + m2
    mass_law = 20 * np.log10(f) + 20 * math.log10(mass_total) - 48
    if connection == "line":
        if math.isclose(critical1, critical2, rel_tol=1e-12):
            other_mass = min(m1, m2)
        else:
            other_mass = m1 if critical2 > critical1 else m2
        gain = (10 * math.log10(spacing * max(critical1, critical2))
                + 20 * math.log10(other_mass / mass_total) - 18)
    elif connection == "point":
        critical, other_mass = ((critical1, m2) if point_supported_panel == 1
                                else (critical2, m1))
        gain = (20 * math.log10(spacing * critical)
                + 20 * math.log10(other_mass / mass_total) - 45)
    else:
        # Full point–point impedance formula, Sharp 20+22 with 17.
        critical = (m1 * critical2 + m2 * critical1) / mass_total
        gain = 20 * math.log10(spacing * critical) - 45
    result = np.asarray(mass_law + gain)
    if np.any(~np.isfinite(result)):
        raise ValueError("Sharp bridge asymptote is outside the representable range")
    return result


def automatic_double_bands(
    plate1: Plate, plate2: Plate, depth_m: float, *, width_m: float, height_m: float,
    bridge: str = "line", stud_spacing_m: float = .6, point_spacing_m: float | None = None,
    point_supported_panel: int = 2, absorber_thickness_m: float = 0.,
    flow_resistivity_pa_s_m2: float | None = None,
    frequencies_hz: ArrayLike = NOMINAL_BANDS_HZ,
    air_density: float = 1.21, sound_speed: float = 343.,
    cancel_event: Event | None = None,
) -> DavyResult:
    """Combine a cavity path and a declared rigid contact topology in energy.

    No flow-resistivity default is guessed in the core: the application chooses
    a traceable reference fibre when the user selects a generic porous fill.
    Both measured and assumed resistivities are evaluated at the actual fill
    thickness using Miki, without a switch at 50 mm.

    The resonance is the physical two-mass/air-spring frequency, without Sharp's
    historical 113/sqrt(me*d) design transition or a fitted interstud multiplier.
    The Sharp bridge response has no adjustable compliance. It is a rigid-contact
    estimate for flexible steel, not a prediction of its resilience benefit.
    """
    _cancel(cancel_event)
    if bridge not in _BRIDGES:
        raise ValueError("bridge must be none, line, point or point_pair")
    if type(point_supported_panel) is not int or point_supported_panel not in (1, 2):
        raise ValueError("point_supported_panel must be 1 or 2")
    f = _frequencies(frequencies_hz)
    width = _positive_scalar(width_m, "width_m")
    height = _positive_scalar(height_m, "height_m")
    depth = _positive_scalar(depth_m, "depth_m")
    spacing = _positive_scalar(stud_spacing_m, "stud_spacing_m")
    points = spacing if point_spacing_m is None else _positive_scalar(point_spacing_m, "point_spacing_m")
    rho, c = _positive_scalar(air_density, "air_density"), _positive_scalar(sound_speed, "sound_speed")
    m1, fc1, _ = _plate_values(plate1, c)
    m2, fc2, _ = _plate_values(plate2, c)
    f0 = math.sqrt(rho * c**2 * (m1 + m2) / (4 * math.pi**2 * depth * m1 * m2))

    # The last evaluation anchors the new combined transition at exactly f0.
    # Calling the existing isolated-airborne route retains its validation and
    # absorption formulas without altering saved V7 projects or its public API.
    sampled_f = np.concatenate((f.ravel(), np.asarray([f0])))
    airborne_result = davy_double_bands(
        plate1, plate2, depth, width_m=width, height_m=height,
        stud=DavyStud(kind="independent"),
        absorber_thickness_m=absorber_thickness_m,
        flow_resistivity_pa_s_m2=flow_resistivity_pa_s_m2,
        minimum_background_absorption=.1,
        frequencies_hz=sampled_f, air_density=rho, sound_speed=c, cancel_event=cancel_event,
    )
    air = np.asarray(airborne_result.airborne_tau[:-1]).reshape(f.shape).copy()
    anchor_air = airborne_result.airborne_tau[-1]
    warnings = [
        "V7.1 automático: aproximación combinada, vía aérea Davy/Hansen y puente rígido "
        "Sharp (1978). No es una calibración de INSUL ni un modelo de montante flexible.",
        "f₀ procede del sistema físico masa–aire–masa; no se utiliza la transición empírica "
        "113/√(mₑd) de Sharp ni un factor ajustado de resonancia entre montantes.",
    ]
    warnings.extend(
        message for message in airborne_result.warnings
        if not message.startswith(("Double Davy:", "Entre 2f₀/3", "La transición de compliance"))
    )
    structural = np.zeros_like(f)
    if bridge != "none":
        bridge_spacing = spacing if bridge == "line" else points
        tl_bridge = sharp_bridge_tl(
            sampled_f, m1, m2, fc1, fc2, spacing_m=bridge_spacing,
            connection=bridge, point_supported_panel=point_supported_panel,
        )
        with np.errstate(over="ignore", invalid="ignore"):
            tau_bridge = 10. ** (-tl_bridge / 10)
        if np.any(~np.isfinite(tau_bridge)):
            raise ValueError("Sharp bridge transmission is outside the representable range")
        structural = tau_bridge[:-1].reshape(f.shape).copy()
        # Total mass controls the low region. No independent bridge is counted
        # there; the transition is to the combined paths at f0, not to V7's
        # no-bridge anchor followed by a discontinuous addition of bridges.
        low = f <= 2 * f0 / 3
        structural[low] = 0.
        transition = (f > 2 * f0 / 3) & (f < f0)
        if np.any(transition):
            start_tau = float(_mass_tau(np.asarray(2 * f0 / 3), m1 + m2, width, height, rho, c))
            end_stud = float(tau_bridge[-1])
            end_tau = anchor_air + end_stud
            weight = np.log(f[transition] / (2 * f0 / 3)) / math.log(1.5)
            total = np.exp((1 - weight) * math.log(start_tau) + weight * math.log(end_tau))
            fraction = weight * end_stud / end_tau
            air[transition], structural[transition] = total * (1 - fraction), total * fraction
        warnings.append(
            "El puente rígido representa el contacto genérico. No atribuye mejoras de "
            "aislamiento a la flexibilidad de un perfil, clip o aislador comercial."
        )
        if bridge == "line":
            warnings.append(
                "Contacto lineal: aproximación de diseño Sharp 24, con la frecuencia crítica "
                "mayor y la masa de la otra hoja. No equivale algebraicamente a Sharp 21–22. "
                "Si coinciden las fc, se elige la menor masa como criterio conservador."
            )
        elif bridge == "point":
            warnings.append(
                f"Contacto puntual en Panel {point_supported_panel}, lineal en la otra hoja: "
                "Sharp 23. Los tornillos sobre una pestaña continua no justifican esta hipótesis."
            )
        else:
            warnings.append(
                "Puentes puntuales en ambas hojas: Sharp 20 y 22 con impedancias puntuales "
                "de 17; malla cuadrada equivalente, no modelo dinámico de resorte o elastómero."
            )
        warnings.append(
            "La vía estructural usa la asíntota de masa de Sharp para aire de referencia. "
            "Su continuación por la región de coincidencia es una aproximación; las pérdidas "
            "y la coincidencia de hojas se resuelven en la vía aérea Davy, no mediante un "
            "solucionador estructural de onda completa. No demuestra un límite inferior universal."
        )
        if np.any(transition):
            warnings.append(
                "Entre 2f₀/3 y f₀ se interpola TL total frente a log(f). El reparto aéreo/puente "
                "en ese intervalo es contable y no una identificación física de mecanismos."
            )
    else:
        warnings.append("Bastidores independientes: sin puente común entre hojas; no equivale a montantes alternados con soleras compartidas.")
    _cancel(cancel_event)
    return _result(f, air, structural, f0, warnings)
