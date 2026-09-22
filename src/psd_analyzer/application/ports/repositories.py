"""History persistence boundary; implementations never leak sessions or SQL queries."""

from typing import Protocol

from ..dto.history import AnalysisSummary, HistoryFilter, StoredAnalysis


class AnalysisRepository(Protocol):
    def save_analysis(self, analysis: StoredAnalysis) -> StoredAnalysis: ...

    def get_analysis(self, analysis_id: str) -> StoredAnalysis: ...

    def list_analyses(self, filters: HistoryFilter) -> tuple[AnalysisSummary, ...]: ...

    def set_baseline(self, analysis_id: str) -> None: ...

    def get_baseline(self, recipe_id: str, recipe_version: str) -> StoredAnalysis | None: ...
