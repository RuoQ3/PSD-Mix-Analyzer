"""Input entry points for presentation clients."""

from dataclasses import dataclass

from ..dto.workbook import ImportedWorkbook
from ..ports.workbook import WorkbookGateway


@dataclass(frozen=True)
class ImportWorkbook:
    gateway: WorkbookGateway

    def execute(self, contents: bytes, filename: str) -> ImportedWorkbook:
        return self.gateway.import_bytes(contents, filename)


@dataclass(frozen=True)
class GenerateWorkbookTemplate:
    gateway: WorkbookGateway

    def execute(self) -> bytes:
        return self.gateway.template_bytes()
