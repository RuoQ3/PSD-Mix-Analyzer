"""Application contracts, fixed-proportion policies and replaceable orchestration."""

from dataclasses import replace

import pytest

from psd_analyzer.application.exceptions import InvalidAnalysisConfiguration, MissingMaterialPSD
from psd_analyzer.application.use_cases import (
    AnalyzeRecipePSD,
    CompareMaterialSubstitution,
    ComparePSDAnalysis,
    SimulateRecipe,
)
from psd_analyzer.domain.exceptions import CoverageError, DomainValidationError, RecipeLockedError
from psd_analyzer.domain.models.analysis_profile import TailPolicy
from psd_analyzer.domain.models.analysis_result import (
    ErrorMetrics,
    EvaluatedCurve,
    FitResult,
    FitStatus,
)
from psd_analyzer.domain.models.psd import PSD, DistributionBasis
from psd_analyzer.domain.models.recipe import RecipeLine, RecipeStatus, RecipeVersion
from psd_analyzer.domain.services.packing_models import ModifiedAndreasen


def recipe_for(*components, status=RecipeStatus.RELEASED):
    return RecipeVersion(
        "fixed",
        "Fixed recipe",
        "v1",
        tuple(RecipeLine(c.line_id, c.batch.material_id, c.mass_fraction) for c in components),
        status,
        "approved-v1" if status == RecipeStatus.RELEASED else "",
    )


def generated(component, q, *, grid=(1, 3, 10, 30, 100), **kwargs):
    passing = ModifiedAndreasen().evaluate_q(grid, q=q, d_min_um=1, d_max_um=100)
    return component(grid=grid, passing=passing, **kwargs)


def test_fixed_recipe_analysis_returns_identified_result(component, profile):
    c = generated(component, 0.25)
    recipe = recipe_for(c)
    result = AnalyzeRecipePSD().execute(recipe, [c], profile)
    assert result.recipe is recipe
    assert not result.is_simulation
    assert result.mixed_psd == c.measurement.psd
    assert result.equivalent_q == pytest.approx(0.25, abs=1e-6)
    assert result.key_passing[1].particle_size_um == 10
    assert result.key_passing[1].cumulative_passing == c.measurement.psd.cumulative_passing[2]
    assert result.key_passing[-1].cumulative_passing is None
    assert result.fit_metrics is result.fit.metrics


def test_target_is_independent_and_optional(component, profile):
    c = generated(component, 0.25)
    analyzer = AnalyzeRecipePSD()
    result = analyzer.execute(recipe_for(c), [c], replace(profile, target_q=0.4))
    assert result.target_q == 0.4
    assert result.equivalent_q == pytest.approx(0.25, abs=1e-6)
    assert result.target_psd is not None and result.target_metrics.rmse > 0
    no_target = analyzer.execute(recipe_for(c), [c], replace(profile, target_q=None))
    assert no_target.target_q is no_target.target_psd is no_target.target_metrics is None


def test_identical_batches_have_zero_differences(component, profile):
    c = generated(component, 0.3)
    result = ComparePSDAnalysis().execute(recipe_for(c), [c], [c], profile)
    assert result.baseline.recipe == result.current.recipe
    assert result.delta_q == 0
    assert all(d == 0 for d in result.delta_psd)
    assert result.metrics.sse == result.metrics.mae == result.metrics.max_absolute_deviation == 0


def test_changed_batch_produces_differences_on_common_grid(component, profile):
    a = generated(component, 0.25)
    b = generated(component, 0.4, grid=(1, 5, 10, 50, 100), batch_id="current")
    result = ComparePSDAnalysis().execute(recipe_for(a), [a], [b], profile)
    expected = (1, 3, 5, 10, 30, 50, 100)
    assert result.particle_size_um == expected
    assert result.baseline.mixed_psd.particle_size_um == expected
    assert result.current.mixed_psd.particle_size_um == expected
    assert result.baseline.fit.point_count == result.current.fit.point_count == len(expected)
    assert result.delta_q > 0
    assert result.metrics.rmse > 0
    assert result.delta_psd[expected.index(10)] < 0


def test_equal_proportion_substitution_retains_unchanged_other_inputs(component, profile):
    a = generated(component, 0.25, weight=0.4)
    b = generated(component, 0.3, line="B", material="m2", weight=0.6)
    replacement = generated(component, 0.4, weight=0.4, material="domestic", batch_id="new")
    recipe = recipe_for(a, b)
    result = CompareMaterialSubstitution().execute(recipe, [a, b], {"A": replacement}, profile)
    assert result.baseline.components == (a, b)
    assert result.current.components == (replacement, b)
    assert result.current.recipe is recipe
    assert tuple(line.mass_fraction for line in recipe.lines) == (0.4, 0.6)
    assert result.metrics.rmse > 0
    with pytest.raises(RecipeLockedError, match="proportions"):
        CompareMaterialSubstitution().execute(
            recipe, [a, b], {"A": replace(replacement, mass_fraction=0.5)}, profile
        )
    with pytest.raises(RecipeLockedError, match="existing"):
        CompareMaterialSubstitution().execute(recipe, [a, b], {"missing": replacement}, profile)


def test_batch_comparison_cannot_change_material_even_if_allowed(component, profile):
    a = generated(component, 0.25)
    b = generated(component, 0.3, material="m2")
    recipe = replace(recipe_for(a), lines=(RecipeLine("A", "m1", 1, ("m1", "m2")),))
    with pytest.raises(RecipeLockedError, match="cannot change materials"):
        ComparePSDAnalysis().execute(recipe, [a], [b], profile)


def test_simulation_is_explicit_draft_only(component, profile):
    c = generated(component, 0.3)
    draft = recipe_for(c, status=RecipeStatus.DRAFT)
    result = SimulateRecipe().execute(draft, [c], profile)
    assert result.is_simulation and result.recipe is draft
    with pytest.raises(RecipeLockedError, match="released"):
        AnalyzeRecipePSD().execute(draft, [c], profile)
    with pytest.raises(RecipeLockedError, match="draft"):
        SimulateRecipe().execute(recipe_for(c), [c], profile)
    with pytest.raises(RecipeLockedError, match="fractions"):
        SimulateRecipe().execute(draft, [replace(c, mass_fraction=0.9)], profile)
    with pytest.raises(RecipeLockedError, match="does not belong"):
        SimulateRecipe().execute(draft, [generated(component, 0.3, material="other")], profile)


def test_selection_errors_are_specific(component, profile):
    c = generated(component, 0.3)
    recipe = recipe_for(c)
    with pytest.raises(MissingMaterialPSD, match="A"):
        AnalyzeRecipePSD().execute(recipe, [], profile)
    with pytest.raises(RecipeLockedError, match="Duplicate"):
        AnalyzeRecipePSD().execute(recipe, [c, c], profile)
    with pytest.raises(RecipeLockedError, match="proportions"):
        AnalyzeRecipePSD().execute(recipe, [replace(c, mass_fraction=0.9)], profile)


def test_disabled_fit_and_configuration_errors(component, profile):
    c = generated(component, 0.3)
    recipe = recipe_for(c)
    result = AnalyzeRecipePSD().execute(recipe, [c], profile, fit_enabled=False)
    assert result.fit.status == FitStatus.NOT_APPLICABLE and result.equivalent_q is None
    assert result.target_psd is not None
    with pytest.raises(InvalidAnalysisConfiguration, match="boolean"):
        AnalyzeRecipePSD().execute(recipe, [c], profile, fit_enabled="yes")
    with pytest.raises(InvalidAnalysisConfiguration, match="MASS"):
        AnalyzeRecipePSD().execute(
            recipe, [c], replace(profile, mix_basis=DistributionBasis.VOLUME)
        )
    with pytest.raises(InvalidAnalysisConfiguration, match="strategies"):
        AnalyzeRecipePSD().execute(recipe, [c], replace(profile, model_id="other"))


def test_boundary_policy_is_bound_to_mixer(component, profile):
    a = component(grid=(1, 10, 100), passing=(0, 0.5, 1), weight=0.5)
    b = component(grid=(2, 20, 200), passing=(0, 0.5, 1), line="B", weight=0.5)
    recipe = recipe_for(a, b)
    with pytest.raises(CoverageError):
        AnalyzeRecipePSD().execute(recipe, [a, b], profile)
    result = AnalyzeRecipePSD().execute(
        recipe, [a, b], replace(profile, tail_policy=TailPolicy.CLAMP)
    )
    assert result.mixed_psd is not None
    assert result.profile.tail_policy == TailPolicy.CLAMP


def test_protocol_compatibility_remains_explicit(component, profile):
    a = component(weight=0.5)
    b = component(line="B", weight=0.5, protocol="other")
    recipe = recipe_for(a, b)
    with pytest.raises(DomainValidationError, match="compatibility"):
        AnalyzeRecipePSD().execute(recipe, [a, b], profile)
    result = AnalyzeRecipePSD().execute(
        recipe, [a, b], replace(profile, measurement_compatibility_confirmed=True)
    )
    assert result.diagnostics[0].code == "MEASUREMENT_COMPATIBILITY_ASSUMPTION"


def test_orchestration_with_fake_services_and_no_numerical_work(component, profile):
    c = component()
    calls = []
    metrics = ErrorMetrics(0.1, 0.1, 0.03, 0.1, 3)

    class Grid:
        def build(self, psds):
            calls.append("grid")
            return (1.0, 10.0, 100.0)

    class Mixer:
        def mix(self, psds, mass_fractions, interpolator):
            calls.append("mix")
            assert mass_fractions == (1.0,)
            return PSD((1, 10, 100), (0, 0.5, 1))

    def mixer_factory(grid_builder, tail_policy):
        assert grid_builder.build(()) == (1, 10, 100)
        assert tail_policy == profile.tail_policy
        return Mixer()

    class Model:
        model_id = "modified-andreasen"

        def evaluate_q(self, sizes, **kwargs):
            raise AssertionError("Fitter fake must not execute the numerical model")

        def cumulative_passing(self, sizes, *, q, **kwargs):
            calls.append(("curve", q))
            return (0, 0.4, 1)

    def fitter(sizes, values, **kwargs):
        calls.append("fit")
        return FitResult(FitStatus.SUCCESS, 0.25, metrics=metrics, point_count=3)

    def metric_service(actual, target):
        calls.append("target metrics")
        return metrics

    def keys(psd, sizes, interpolator, *, tail_policy):
        calls.append("keys")
        return EvaluatedCurve(tuple(sizes), (0, 0.4, 0.6, 1, None), psd.basis)

    result = AnalyzeRecipePSD(
        grid_builder=Grid(),
        mixing_factory=mixer_factory,
        model=Model(),
        q_fitter=fitter,
        metrics_service=metric_service,
        key_size_evaluator=keys,
    ).execute(recipe_for(c), [c], profile)
    assert calls == [
        "grid",
        "mix",
        "fit",
        ("curve", 0.25),
        ("curve", 0.3),
        "target metrics",
        "keys",
    ]
    assert result.equivalent_q == 0.25 and result.target_q == 0.3
    assert result.fit_metrics is result.target_metrics is metrics


def test_fitting_failure_remains_diagnostic(component, profile):
    c = component()

    def failed(*args, **kwargs):
        return FitResult(FitStatus.FAILED, message="numerical reason")

    result = AnalyzeRecipePSD(q_fitter=failed).execute(recipe_for(c), [c], profile)
    assert result.equivalent_q is None and result.fit_metrics is None
    assert any(
        d.code == "FIT_FAILED" and d.message == "numerical reason" for d in result.diagnostics
    )
    assert result.target_psd is not None


def test_query_strategy_cannot_replace_requested_key_sizes(component, profile):
    c = component()

    def wrong_keys(psd, sizes, interpolator, *, tail_policy):
        return EvaluatedCurve((2, 20), (0.1, 0.5), psd.basis)

    with pytest.raises(DomainValidationError, match="Key-size evaluator"):
        AnalyzeRecipePSD(key_size_evaluator=wrong_keys).execute(recipe_for(c), [c], profile)
