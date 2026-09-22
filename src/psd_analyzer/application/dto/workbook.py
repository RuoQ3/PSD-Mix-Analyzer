"""Public import results and issues; independent of the workbook reader implementation."""

from dataclasses import dataclass

from ...domain.models.material import Material, MaterialBatch
from ...domain.models.psd import PSDMeasurement
from ...domain.models.recipe import RecipeVersion


@dataclass(frozen=True)
class ImportIssue:
    """An actionable cell or workbook error; rows are Excel's one-based positions."""

    file: str
    sheet: str
    row: int | None
    column: str | None
    value: object
    code: str
    message: str
    severity: str = "error"


class ExcelImportError(Exception):
    """An import failed atomically; all collected issues are available to callers."""

    def __init__(self, issues: tuple[ImportIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.sheet}:{i.row or '-'} {i.message}" for i in issues))


@dataclass(frozen=True)
class ImportedWorkbook:
    """Validated domain objects; choosing a batch/measurement is an upper-layer concern."""

    materials: tuple[Material, ...]
    batches: tuple[MaterialBatch, ...]
    measurements: tuple[PSDMeasurement, ...]
    recipes: tuple[RecipeVersion, ...]
    source_hash: str
