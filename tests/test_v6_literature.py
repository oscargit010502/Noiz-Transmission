"""Independent published rating example; no claim of predictor validation."""

import json
from pathlib import Path

import pytest

from noiz_transmission.application.assemblies import AssemblyProject, Cavity, Layer, Panel
from noiz_transmission.application.assembly_services import _resonances
from noiz_transmission.core.finite_panel import FinitePanel
from noiz_transmission.core.physics import (
    critical_frequency,
    mass_air_mass_resonance,
    surface_density,
)
from noiz_transmission.core.ratings import legacy_stc
from noiz_transmission.core.transfer import Plate


def test_legacy_stc_reproduces_barron_worked_example_4_11():
    case_path = Path(__file__).resolve().parents[1] / "validation" / "v6-rating-barron.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))

    result = legacy_stc(case["frequencies_hz"], case["transmission_loss_db"])

    # Expected STC comes from Barron, Table 4-5 / Example 4-11, not this engine.
    assert result.stc == case["expected_stc"] == 25
    assert result.reference_curve_db[6] == 25  # 500 Hz ordinate defines STC.
    assert case["absolute_rating_tolerance"] == 0
    assert case["validates_predictor_accuracy"] is False


def test_barron_example_4_8_published_glass_resonance_diagnostics():
    # Barron pp.124–126: 1 x 2 m glass panes, 6 mm each, 75 mm air gap.
    # Expected results are published rounded values, not the computed TL curve.
    density, thickness, young, poisson = 2500.0, 0.006, 71e9, 0.21
    mass = surface_density(density, thickness)
    rigidity = young * thickness**3 / (12 * (1 - poisson**2))
    assert mass == 15.0
    assert critical_frequency(density, thickness, young, poisson, 345.6) == pytest.approx(
        2014, abs=0.5, rel=0,
    )
    assert FinitePanel(1, 2).first_mode_hz(mass, rigidity) == pytest.approx(
        18.5, abs=0.05, rel=0,
    )
    assert mass_air_mass_resonance(mass, mass, 0.075, 1.188, 345.6) == pytest.approx(
        79.9, abs=0.05, rel=0,
    )

    glass = Layer("Barron example 4-8 glass", 6, density, young, 0.002, poisson)
    project = AssemblyProject(
        "Barron example 4-8", panels=(Panel((glass,)), Panel((glass,))),
        cavities=(Cavity(depth_mm=75),), width_m=1, height_m=2,
        air_density_kg_m3=1.188, sound_speed_m_s=345.6,
    )
    # A second implementation uses the coupled mass-spring eigenproblem.
    coupled_modes = _resonances((Plate(mass, rigidity), Plate(mass, rigidity)), project)
    assert coupled_modes == pytest.approx((79.9,), abs=0.05, rel=0)
