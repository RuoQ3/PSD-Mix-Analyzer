"""Byte-oriented input adapter; temporary files never escape into the presentation layer."""

from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from ...application.dto.workbook import ExcelImportError, ImportedWorkbook, ImportIssue
from .importer import ExcelImporter
from .template import generate_excel_template


@dataclass(frozen=True)
class ExcelWorkbookGateway:
    importer: ExcelImporter = field(default_factory=ExcelImporter)

    def import_bytes(self, contents: bytes, filename: str) -> ImportedWorkbook:
        """Keep the supplied filename for diagnostics, never use it as a filesystem path."""
        try:
            with TemporaryDirectory(prefix="psd-import-") as directory:
                path = Path(directory) / "input.xlsx"
                path.write_bytes(contents)
                return self.importer.import_workbook(path)
        except ExcelImportError as exc:
            raise ExcelImportError(tuple(replace(i, file=filename) for i in exc.issues)) from exc
        except OSError as exc:
            raise ExcelImportError(
                (
                    ImportIssue(
                        filename,
                        "Workbook",
                        None,
                        None,
                        None,
                        "file_io",
                        "Cannot read uploaded workbook",
                    ),
                )
            ) from exc

    def template_bytes(self) -> bytes:
        try:
            with TemporaryDirectory(prefix="psd-template-") as directory:
                return generate_excel_template(Path(directory) / "template.xlsx").read_bytes()
        except OSError as exc:
            raise ExcelImportError(
                (
                    ImportIssue(
                        "template.xlsx",
                        "Workbook",
                        None,
                        None,
                        None,
                        "file_io",
                        "Cannot generate workbook template",
                    ),
                )
            ) from exc
