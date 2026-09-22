"""Fixed-recipe orchestration; numerical work remains in domain services."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ...domain.exceptions import DomainValidationError
from ...domain.models.analysis_profile import AnalysisProfile, TailPolicy
from ...domain.models.analysis_result import (
    AnalysisResult,
    Diagnostic,
    ErrorMetrics,
    EvaluatedCurve,
    FitResult,
    FitStatus,
    KeyPassing,
)
from ...domain.models.psd import PSD, DistributionBasis
from ...domain.models.recipe import MixtureComponent, RecipeVersion
from ...domain.protocols import (
    LossFunction,
    PackingModel,
    PSDGridBuilder,
    PSDInterpolator,
    QFittableModel,
)
from ...domain.services.grid import ParticleSizeGridBuilder
from ...domain.services.interpolation import LogLinearInterpolator
from ...domain.services.losses import SquaredErrorLoss
from ...domain.services.metrics import calculate_metrics
from ...domain.services.packing_models import ModifiedAndreasen
from ...domain.services.psd_mixing import PSDMixingService
from ...domain.services.q_fitting import fit_q
from ...domain.services.queries import evaluate_at_sizes
from ...domain.validation import fractions, sizes
from ..exceptions import InvalidAnalysisConfiguration
from ..ports.analysis import KeySizeEvaluator, MixingFactory, PSDMixer, QFitter
from .selection import select_components


@dataclass(frozen=True)
class _FixedGrid:
    nodes: tuple[float, ...]

    def build(self, psds: Sequence[PSD]) -> tuple[float, ...]:
        return self.nodes


def _mixing_factory(grid_builder: PSDGridBuilder, tail_policy: TailPolicy) -> PSDMixer:
    return PSDMixingService(grid_builder, tail_policy)


@dataclass(frozen=True)
class AnalyzeRecipePSD:
    """Analyze released recipes with explicitly selected batches and immutable proportions.

    The default calculation grid is the measured-node union. A factory binds the
    injected mixer to the chosen grid and profile boundary policy, allowing paired
    comparisons to use exactly the same nodes before fitting either result.
    """

    grid_builder: PSDGridBuilder = field(default_factory=ParticleSizeGridBuilder)
    interpolator: PSDInterpolator = field(default_factory=LogLinearInterpolator)
    model: PackingModel = field(default_factory=ModifiedAndreasen)
    loss: LossFunction = field(default_factory=SquaredErrorLoss)
    mixing_factory: MixingFactory = _mixing_factory
    q_fitter: QFitter = fit_q
    metrics_service: Callable[[Sequence[float], Sequence[float]], ErrorMetrics] = calculate_metrics
    key_size_evaluator: KeySizeEvaluator = evaluate_at_sizes

    def execute(
        self,
        recipe: RecipeVersion,
        components: Sequence[MixtureComponent],
        profile: AnalysisProfile,
        *,
        fit_enabled: bool = True,
    ) -> AnalysisResult:
        """Analyze a released recipe; drafts must explicitly use SimulateRecipe."""
        ordered = select_components(recipe, components)
        return self._on_grid(
            recipe, ordered, profile, self.calculation_grid(ordered), fit_enabled=fit_enabled
        )

    def calculation_grid(self, components: Sequence[MixtureComponent]) -> tuple[float, ...]:
        """Delegate calculation nodes to the injected domain grid strategy."""
        return sizes(
            self.grid_builder.build(tuple(c.measurement.psd for c in components)), minimum_count=2
        )

    def _validate_configuration(self, profile: AnalysisProfile, fit_enabled: bool) -> None:
        if type(fit_enabled) is not bool:
            raise InvalidAnalysisConfiguration("fit_enabled must be boolean")
        if profile.mix_basis != DistributionBasis.MASS:
            raise InvalidAnalysisConfiguration("Recipe use cases currently support MASS only")
        if (
            self.interpolator.method_id != profile.interpolation.value
            or self.model.model_id != profile.model_id
            or self.loss.loss_id != profile.loss_id
        ):
            raise InvalidAnalysisConfiguration(
                "Injected strategies must match the analysis profile"
            )

    def _on_grid(
        self,
        recipe: RecipeVersion,
        ordered: tuple[MixtureComponent, ...],
        profile: AnalysisProfile,
        grid: tuple[float, ...],
        *,
        fit_enabled: bool,
        simulation: bool = False,
    ) -> AnalysisResult:
        self._validate_configuration(profile, fit_enabled)
        diagnostics = self._measurement_diagnostics(ordered, profile)
        recipe_fractions = {line.line_id: line.mass_fraction for line in recipe.lines}
        input_weights = tuple(recipe_fractions[c.line_id] for c in ordered)
        actual_weights, raw_sum = fractions(input_weights)
        mixer = self.mixing_factory(_FixedGrid(grid), profile.tail_policy)
        mixed = mixer.mix(
            tuple(c.measurement.psd for c in ordered), input_weights, self.interpolator
        )
        if mixed.particle_size_um != grid or mixed.basis != profile.mix_basis:
            raise DomainValidationError(
                "Mixing service returned an incompatible calculation grid/basis"
            )
        mixed_curve = EvaluatedCurve(grid, mixed.cumulative_passing, mixed.basis)
        fit = self._fit(mixed, profile, fit_enabled)
        fitted = (
            None if fit.equivalent_q is None else self._model_curve(grid, fit.equivalent_q, profile)
        )
        target = (
            None if profile.target_q is None else self._model_curve(grid, profile.target_q, profile)
        )
        target_metrics = None
        if target is not None:
            target_metrics = self.metrics_service(
                mixed.cumulative_passing,
                tuple(p for p in target.cumulative_passing if p is not None),
            )
        queried = self.key_size_evaluator(
            mixed, profile.key_sizes_um, self.interpolator, tail_policy=profile.tail_policy
        )
        if queried.particle_size_um != profile.key_sizes_um or queried.basis != mixed.basis:
            raise DomainValidationError("Key-size evaluator returned an incompatible grid/basis")
        keys = tuple(
            KeyPassing(d, p, None if p is not None else "outside_supported_coverage")
            for d, p in zip(queried.particle_size_um, queried.cumulative_passing, strict=True)
        )
        if fit.status != FitStatus.SUCCESS:
            diagnostics.append(Diagnostic(f"FIT_{fit.status.value.upper()}", fit.message))
        if any(key.cumulative_passing is None for key in keys):
            diagnostics.append(Diagnostic("KEY_SIZE_UNAVAILABLE", "Some key sizes lack coverage"))
        return AnalysisResult(
            profile,
            ordered,
            mixed_curve,
            fit,
            fitted,
            target,
            fit.metrics,
            target_metrics,
            keys,
            tuple(diagnostics),
            actual_weights,
            raw_sum,
            recipe=recipe,
            is_simulation=simulation,
        )

    @staticmethod
    def _measurement_diagnostics(
        components: tuple[MixtureComponent, ...], profile: AnalysisProfile
    ) -> list[Diagnostic]:
        protocols = {
            (c.measurement.method, c.measurement.protocol_id)
            for c in components
            if c.mass_fraction > 0
        }
        if len(protocols) <= 1:
            return []
        if not profile.measurement_compatibility_confirmed:
            raise DomainValidationError(
                "Mixed measurement protocols require explicit compatibility confirmation"
            )
        return [
            Diagnostic(
                "MEASUREMENT_COMPATIBILITY_ASSUMPTION",
                "Different measurement protocols accepted by the analysis profile",
            )
        ]

    def _fit(self, mixed: PSD, profile: AnalysisProfile, enabled: bool) -> FitResult:
        if not enabled or not isinstance(self.model, QFittableModel):
            return FitResult(
                FitStatus.NOT_APPLICABLE,
                message="Fitting disabled or model does not support q fitting",
            )
        return self.q_fitter(
            mixed.particle_size_um,
            mixed.cumulative_passing,
            profile=profile,
            model=self.model,
            loss=self.loss,
        )

    def _model_curve(
        self, grid: tuple[float, ...], q: float, profile: AnalysisProfile
    ) -> EvaluatedCurve:
        passing = self.model.cumulative_passing(
            grid, q=q, d_min_um=profile.d_min_um, d_max_um=profile.d_max_um
        )
        return EvaluatedCurve(grid, passing, profile.mix_basis)
