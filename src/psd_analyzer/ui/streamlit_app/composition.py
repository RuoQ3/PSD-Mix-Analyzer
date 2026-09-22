"""Single composition root; pages receive use cases rather than persistence details."""

import os
from pathlib import Path

from ...application.dto.container import ApplicationContainer
from ...application.use_cases.history import (
    CompareHistoricalAnalyses,
    GetAnalysisDetail,
    GetBaselineAnalysis,
    ListAnalysisHistory,
    SaveAnalysis,
    SetBaselineAnalysis,
)
from ...application.use_cases.workbook_analysis import WorkbookAnalysis
from ...application.use_cases.workbook_input import GenerateWorkbookTemplate, ImportWorkbook
from ...infrastructure.excel.gateway import ExcelWorkbookGateway
from ...infrastructure.persistence import create_repository


def build_container(database_path: str | Path | None = None) -> ApplicationContainer:
    """Configure a SQLite repository; each operation owns and closes its transaction."""
    path = (
        database_path
        if database_path is not None
        else os.environ.get("PSD_ANALYZER_DB", "data/psd_analyzer.db")
    )
    repository = create_repository(path)
    gateway = ExcelWorkbookGateway()
    return ApplicationContainer(
        ImportWorkbook(gateway),
        GenerateWorkbookTemplate(gateway),
        WorkbookAnalysis(),
        SaveAnalysis(repository),
        ListAnalysisHistory(repository),
        GetAnalysisDetail(repository),
        CompareHistoricalAnalyses(repository),
        SetBaselineAnalysis(repository),
        GetBaselineAnalysis(repository),
    )
