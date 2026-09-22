"""Small orchestration boundary: workbook → schema → records → domain objects."""

from dataclasses import dataclass, field
from pathlib import Path

from .mapper import DomainMapper
from .parser import SheetParser
from .reader import ExcelSchemaValidator, WorkbookReader
from .records import ImportedWorkbook, ImportIssue


@dataclass(frozen=True)
class ExcelImporter:
    """Import atomically; readers and schema validators can be injected for alternate sources."""

    reader: WorkbookReader = field(default_factory=WorkbookReader)
    schema: ExcelSchemaValidator = field(default_factory=ExcelSchemaValidator)

    def import_workbook(self, path: str | Path) -> ImportedWorkbook:
        workbook = self.reader.read(path)
        rows = self.schema.validate(workbook)
        issues: list[ImportIssue] = []
        parser = SheetParser(workbook.filename, issues)
        records = parser.parse(rows)
        return DomainMapper(parser).map(records, workbook.source_hash)


def import_excel_workbook(path: str | Path) -> ImportedWorkbook:
    """Read a standard workbook and return immutable, validated domain objects."""
    return ExcelImporter().import_workbook(path)
