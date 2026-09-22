"""Immutable Excel records retain source positions without becoming domain models."""

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
class CellValue:
    value: object
    number_format: str = "General"
    is_formula: bool = False


@dataclass(frozen=True)
class SheetRow:
    sheet: str
    row: int
    cells: tuple[tuple[str, CellValue], ...]

    def cell(self, column: str) -> CellValue:
        return dict(self.cells).get(column, CellValue(None))


@dataclass(frozen=True)
class MaterialImportRecord:
    source: SheetRow
    material_code: str
    material_name: str
    batch_key: str
    batch_no: str
    supplier: str | None
    grade: str | None
    notes: str | None
    density: float | None
    density_kind: str | None


@dataclass(frozen=True)
class MeasurementImportRecord:
    source: SheetRow
    measurement_key: str
    batch_key: str
    basis: str
    method: str
    protocol: str
    version: str


@dataclass(frozen=True)
class PSDImportRecord:
    source: SheetRow
    measurement_key: str
    particle_size_um: float
    cumulative_passing_pct: float


@dataclass(frozen=True)
class RecipeImportRecord:
    source: SheetRow
    recipe_code: str
    recipe_name: str
    recipe_version: str
    line_key: str
    material_code: str
    mass_fraction_pct: float


@dataclass(frozen=True)
class ImportRecords:
    materials: tuple[MaterialImportRecord, ...]
    measurements: tuple[MeasurementImportRecord, ...]
    psds: tuple[PSDImportRecord, ...]
    recipes: tuple[RecipeImportRecord, ...]


@dataclass(frozen=True)
class ImportedWorkbook:
    """Validated domain objects; choosing a batch/measurement is an upper-layer concern."""

    materials: tuple[Material, ...]
    batches: tuple[MaterialBatch, ...]
    measurements: tuple[PSDMeasurement, ...]
    recipes: tuple[RecipeVersion, ...]
    source_hash: str
