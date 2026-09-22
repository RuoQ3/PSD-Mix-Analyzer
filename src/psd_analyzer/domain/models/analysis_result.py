"""Immutable results; missing values are explicit, never numeric zero substitutes."""

from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import DomainValidationError
from ..validation import finite, sizes
from .analysis_profile import AnalysisProfile
from .psd import DistributionBasis
from .recipe import MixtureComponent


class FitStatus(StrEnum):
    SUCCESS = "success"
    AT_BOUND = "at_bound"
    WEAKLY_IDENTIFIED = "weakly_identified"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class EvaluatedCurve:
    particle_size_um: tuple[float, ...]
    cumulative_passing: tuple[float | None, ...]
    basis: DistributionBasis

    def __post_init__(self) -> None:
        grid = sizes(self.particle_size_um)
        values = tuple(None if v is None else finite(v, "passing") for v in self.cumulative_passing)
        valid = tuple(v for v in values if v is not None)
        if len(grid) != len(values):
            raise DomainValidationError("Curve sizes and values must have equal lengths")
        if any(v < 0 or v > 1 for v in valid) or any(
            a > b for a, b in zip(valid, valid[1:], strict=False)
        ):
            raise DomainValidationError("Evaluated curve must be cumulative fractions in [0, 1]")
        if not isinstance(self.basis, DistributionBasis):
            raise DomainValidationError("Curve basis must be explicit")
        object.__setattr__(self, "particle_size_um", grid)
        object.__setattr__(self, "cumulative_passing", values)

    @property
    def complete(self) -> bool:
        return all(value is not None for value in self.cumulative_passing)


@dataclass(frozen=True)
class ErrorMetrics:
    rmse: float
    mae: float
    sse: float
    max_absolute_deviation: float
    n: int


@dataclass(frozen=True)
class FitResult:
    status: FitStatus
    equivalent_q: float | None = None
    objective_value: float | None = None
    evaluations: int = 0
    message: str = ""


@dataclass(frozen=True)
class KeyPassing:
    particle_size_um: float
    cumulative_passing: float | None
    reason: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    profile: AnalysisProfile
    components: tuple[MixtureComponent, ...]
    mixed_curve: EvaluatedCurve
    fit: FitResult
    fitted_curve: EvaluatedCurve | None
    target_curve: EvaluatedCurve | None
    fit_metrics: ErrorMetrics | None
    target_metrics: ErrorMetrics | None
    key_passing: tuple[KeyPassing, ...]
    diagnostics: tuple[Diagnostic, ...]
    actual_weights: tuple[float, ...]
    input_fraction_sum: float
    algorithm_version: str = "domain-core-0.1.1"


@dataclass(frozen=True)
class ComparisonResult:
    particle_size_um: tuple[float, ...]
    delta_psd: tuple[float, ...]
    delta_q: float | None
    key_delta: tuple[KeyPassing, ...]
    max_absolute_deviation: float
    diagnostics: tuple[Diagnostic, ...] = ()
