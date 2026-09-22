"""Explicit use-case bundle; no framework state or open database sessions."""

from dataclasses import dataclass

from ..use_cases.history import (
    CompareHistoricalAnalyses,
    GetAnalysisDetail,
    GetBaselineAnalysis,
    ListAnalysisHistory,
    SaveAnalysis,
    SetBaselineAnalysis,
)
from ..use_cases.workbook_analysis import WorkbookAnalysis
from ..use_cases.workbook_input import GenerateWorkbookTemplate, ImportWorkbook


@dataclass(frozen=True)
class ApplicationContainer:
    import_workbook: ImportWorkbook
    generate_template: GenerateWorkbookTemplate
    workflow: WorkbookAnalysis
    save_analysis: SaveAnalysis
    list_history: ListAnalysisHistory
    get_detail: GetAnalysisDetail
    compare_history: CompareHistoricalAnalyses
    set_baseline: SetBaselineAnalysis
    get_baseline: GetBaselineAnalysis
