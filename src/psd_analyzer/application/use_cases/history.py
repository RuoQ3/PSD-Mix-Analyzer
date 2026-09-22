"""Explicit save, query and baseline operations through the repository port."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ...domain.models.analysis_result import AnalysisResult, ComparisonResult
from ...domain.services.comparison import compare_results
from ..dto.history import AnalysisSummary, AnalysisType, HistoryError, HistoryFilter, StoredAnalysis
from ..ports.repositories import AnalysisRepository


@dataclass(frozen=True)
class SaveAnalysis:
    repository: AnalysisRepository

    def execute(
        self,
        result: AnalysisResult | ComparisonResult,
        analysis_type: AnalysisType,
        *,
        analysis_id: str,
        created_at: datetime | None = None,
    ) -> StoredAnalysis:
        """Save only on an explicit request; repeat IDs with identical data are idempotent."""
        return self.repository.save_analysis(
            StoredAnalysis(analysis_id, created_at or datetime.now(UTC), analysis_type, result)
        )


@dataclass(frozen=True)
class ListAnalysisHistory:
    repository: AnalysisRepository

    def execute(self, filters: HistoryFilter | None = None) -> tuple[AnalysisSummary, ...]:
        return self.repository.list_analyses(filters or HistoryFilter())


@dataclass(frozen=True)
class GetAnalysisDetail:
    repository: AnalysisRepository

    def execute(self, analysis_id: str) -> StoredAnalysis:
        return self.repository.get_analysis(analysis_id)


@dataclass(frozen=True)
class SetBaselineAnalysis:
    repository: AnalysisRepository

    def execute(self, analysis_id: str) -> None:
        self.repository.set_baseline(analysis_id)


@dataclass(frozen=True)
class GetBaselineAnalysis:
    repository: AnalysisRepository

    def execute(self, recipe_id: str, recipe_version: str) -> StoredAnalysis | None:
        return self.repository.get_baseline(recipe_id, recipe_version)


@dataclass(frozen=True)
class CompareHistoricalAnalyses:
    repository: AnalysisRepository

    def execute(self, baseline_id: str, current_id: str) -> ComparisonResult:
        baseline = self.repository.get_analysis(baseline_id)
        current = self.repository.get_analysis(current_id)
        if baseline.analysis_type != current.analysis_type:
            raise HistoryError("History comparisons require the same analysis type")
        left, right = baseline.current, current.current
        if (
            left.recipe is None
            or right.recipe is None
            or (left.recipe.recipe_id, left.recipe.version)
            != (right.recipe.recipe_id, right.recipe.version)
        ):
            raise HistoryError("History comparisons require the same recipe and version")
        return compare_results(right, left)
