from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from psd_analyzer.domain.exceptions import DomainValidationError
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.models.material import DensityKind, Material, MaterialBatch
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.domain.models.recipe import RecipeLine, RecipeStatus, RecipeVersion
from psd_analyzer.domain.validation import finite, fractions


@pytest.mark.parametrize(
    "grid,passing",
    [
        ((1,), (0,)),
        ((0, 1), (0, 1)),
        ((-1, 1), (0, 1)),
        ((1, 1), (0, 1)),
        ((2, 1), (0, 1)),
        ((1, 2), (0,)),
        ((1, 2), (-0.01, 1)),
        ((1, 2), (0, 1.01)),
        ((1, 2), (0.6, 0.4)),
        ((1, float("nan")), (0, 1)),
        ((1, 2), (0, float("inf"))),
    ],
)
def test_invalid_psd(grid, passing):
    with pytest.raises(DomainValidationError):
        PSD(grid, passing)


def test_psd_defensive_copy():
    grid = np.array([1.0, 2.0])
    passing = [0.0, 1.0]
    psd = PSD(grid, passing)
    grid[0] = 9
    passing[1] = 0.5
    assert psd.particle_size_um == (1, 2)
    assert psd.cumulative_passing == (0, 1)
    with pytest.raises(FrozenInstanceError):
        psd.basis = DistributionBasis.VOLUME


@pytest.mark.parametrize(
    "kwargs",
    [
        {"basis": "mass"},
        {"lower_tail_confirmed": 1},
        {"upper_tail_confirmed": "yes"},
        {"lower_tail_confirmed": True},
        {"upper_tail_confirmed": True},
    ],
)
def test_invalid_psd_metadata(kwargs):
    with pytest.raises(DomainValidationError):
        PSD((1, 2), (0.1, 0.9), **kwargs)


@pytest.mark.parametrize("value", [True, None, "bad", float("nan"), float("inf")])
def test_finite_rejects_invalid_values(value):
    with pytest.raises(DomainValidationError):
        finite(value, "x")


@pytest.mark.parametrize("values", [(), (0.3, 0.6), (-0.1, 1.1), (0, 0)])
def test_invalid_fraction_sums(values):
    with pytest.raises(DomainValidationError):
        fractions(values)


def test_fraction_tolerance_does_not_hide_missing_material():
    norm, original = fractions((0.5, 0.500000001))
    assert sum(norm) == pytest.approx(1)
    assert original != 1
    with pytest.raises(DomainValidationError):
        fractions((0.5, 0.4999))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"d_min_um": 0},
        {"d_max_um": 1},
        {"grid_points": 2},
        {"grid_points": True},
        {"scan_points": 4},
        {"mix_basis": DistributionBasis.NUMBER},
        {"mix_basis": "mass"},
        {"interpolation": "cubic"},
        {"tail_policy": "extrapolate"},
        {"q_bounds": (1, 0)},
        {"q_bounds": (0,)},
        {"q_tolerance": 2},
        {"q_tolerance": 0},
        {"weak_loss_span": 0},
        {"key_sizes_um": (45, 10)},
        {"target_q": float("nan")},
        {"version": ""},
    ],
)
def test_invalid_profile(profile, kwargs):
    with pytest.raises(DomainValidationError):
        replace(profile, **kwargs)


def test_profile_defensive_copy():
    keys = [1, 10]
    bounds = [0, 1]
    p = AnalysisProfile("a", "1", 1, 100, key_sizes_um=keys, q_bounds=bounds)
    keys.append(100)
    bounds[1] = 9
    assert p.key_sizes_um == (1, 10) and p.q_bounds == (0, 1)


def test_material_and_density_validation():
    assert Material("m", "quartz").name == "quartz"
    with pytest.raises(DomainValidationError):
        Material("", "name")
    with pytest.raises(DomainValidationError):
        MaterialBatch("b", "m", "s", "1", 2500)
    with pytest.raises(DomainValidationError):
        MaterialBatch("b", "m", "s", "1", 0, DensityKind.TRUE)
    with pytest.raises(DomainValidationError):
        MaterialBatch("b", "m", "s", "1", 2500, "true")


def test_measurement_and_component_validation(component):
    c = component()
    with pytest.raises(DomainValidationError):
        replace(c.measurement, psd="bad")
    with pytest.raises(DomainValidationError):
        replace(c, measurement=replace(c.measurement, batch_id="x"))
    with pytest.raises(DomainValidationError):
        replace(c, batch="bad")
    with pytest.raises(DomainValidationError):
        replace(c, mass_fraction=-1)
    with pytest.raises(DomainValidationError):
        replace(c, uniform_density_confirmed=1)
    with pytest.raises(DomainValidationError):
        replace(c.measurement, version="")


def test_recipe_validation():
    a = RecipeLine("a", "m", 1)
    assert a.allowed_material_ids == ("m",)
    with pytest.raises(DomainValidationError):
        RecipeLine("a", "m", -1)
    with pytest.raises(DomainValidationError):
        RecipeLine("a", "m", 1, ("",))
    with pytest.raises(DomainValidationError):
        RecipeVersion("r", "R", "1", (a, a))
    with pytest.raises(DomainValidationError):
        RecipeVersion("r", "R", "1", ("bad",))
    with pytest.raises(DomainValidationError):
        RecipeVersion("r", "R", "1", (a,), "released")
    with pytest.raises(DomainValidationError):
        RecipeVersion("r", "R", "1", (a,), RecipeStatus.RELEASED)


def test_evaluated_curve_validates_plugin_output():
    from psd_analyzer.domain.models.analysis_result import EvaluatedCurve

    basis = DistributionBasis.MASS
    values = [None, 0.5, 1]
    curve = EvaluatedCurve((1, 10, 100), values, basis)
    values[-1] = 0.4
    assert curve.cumulative_passing == (None, 0.5, 1)
    for passing in [(0, 1), (0, 1.1, 1), (0, 0.9, 0.8)]:
        with pytest.raises(DomainValidationError):
            EvaluatedCurve((1, 10, 100), passing, basis)
    with pytest.raises(DomainValidationError):
        EvaluatedCurve((1, 10, 100), (0, 0.5, 1), "mass")


def test_protocol_confirmation_is_boolean(profile):
    with pytest.raises(DomainValidationError):
        replace(profile, measurement_compatibility_confirmed="yes")
