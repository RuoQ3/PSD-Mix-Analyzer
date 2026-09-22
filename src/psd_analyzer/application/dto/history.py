"""Immutable persistence requests and read models, independent of a database library."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from ...domain.models.analysis_result import AnalysisResult, ComparisonResult, FitStatus
from ...domain.models.recipe import RecipeStatus
from ..exceptions import AnalysisError


class HistoryError(AnalysisError):
    """An invalid history request or unavailable stored analysis."""


class RepositoryError(HistoryError):
    """Storage could not complete the requested operation."""


class AnalysisNotFound(HistoryError):
    """The requested analysis does not exist."""


class AnalysisConflict(HistoryError):
    """An analysis UUID already identifies a different immutable snapshot."""


class AnalysisType(StrEnum):
    PRODUCTION_MONITORING = "production_monitoring"
    MATERIAL_SUBSTITUTION = "material_substitution"
    RECIPE_SIMULATION = "recipe_simulation"


def utc_datetime(value: datetime) -> datetime:
    """Reject ambiguous naive timestamps and normalize aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise HistoryError("History timestamps must include a timezone")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class StoredAnalysis:
    analysis_id: str
    created_at: datetime
    analysis_type: AnalysisType
    result: AnalysisResult | ComparisonResult
    is_baseline: bool = False

    def __post_init__(self) -> None:
        try:
            identifier = str(UUID(self.analysis_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise HistoryError("analysis_id must be a UUID") from exc
        object.__setattr__(self, "analysis_id", identifier)
        object.__setattr__(self, "created_at", utc_datetime(self.created_at))
        if not isinstance(self.analysis_type, AnalysisType):
            raise HistoryError("An explicit AnalysisType is required")
        current = self.current
        if current.recipe is None:
            raise HistoryError("A versioned recipe snapshot is required for history")
        if self.analysis_type == AnalysisType.RECIPE_SIMULATION:
            if current.recipe.status != RecipeStatus.DRAFT:
                raise HistoryError("Simulation history requires a draft recipe")
        elif current.recipe.status != RecipeStatus.RELEASED:
            raise HistoryError("Production and substitution history require a released recipe")
        if self.analysis_type == AnalysisType.MATERIAL_SUBSTITUTION:
            if not isinstance(self.result, ComparisonResult) or self.result.baseline is None:
                raise HistoryError("Substitution history requires both comparison snapshots")
        elif isinstance(self.result, ComparisonResult):
            raise HistoryError("Only substitution history accepts a comparison result")
        if current.is_simulation != (self.analysis_type == AnalysisType.RECIPE_SIMULATION):
            raise HistoryError("Simulation flag and analysis type disagree")
        if self.is_baseline and self.analysis_type != AnalysisType.PRODUCTION_MONITORING:
            raise HistoryError("Only production monitoring can be a default baseline")

    @property
    def current(self) -> AnalysisResult:
        """Primary result used by history summaries and baseline selection."""
        if isinstance(self.result, AnalysisResult):
            return self.result
        if self.result.current is None:
            raise HistoryError("Comparison has no current snapshot")
        return self.result.current


@dataclass(frozen=True)
class HistoryFilter:
    recipe_id: str | None = None
    recipe_version: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    analysis_type: AnalysisType | None = None
    batch_no: str | None = None
    limit: int = 1000

    def __post_init__(self) -> None:
        for name in ("date_from", "date_to"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, utc_datetime(value))
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise HistoryError("History start date must not follow end date")
        if type(self.limit) is not int or not 1 <= self.limit <= 10000:
            raise HistoryError("History limit must be an integer between 1 and 10000")
        if self.analysis_type is not None and not isinstance(self.analysis_type, AnalysisType):
            raise HistoryError("History type must be an AnalysisType")


@dataclass(frozen=True)
class AnalysisSummary:
    analysis_id: str
    created_at: datetime
    analysis_type: AnalysisType
    recipe_id: str
    recipe_name: str
    recipe_version: str
    equivalent_q: float | None
    target_q: float | None
    rmse: float | None
    mae: float | None
    max_absolute_deviation: float | None
    is_baseline: bool
    fit_status: FitStatus
    convention_key: str = ""
