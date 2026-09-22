"""Replaceable file input port; the application does not depend on Excel libraries."""

from typing import Protocol

from ..dto.workbook import ImportedWorkbook


class WorkbookGateway(Protocol):
    def import_bytes(self, contents: bytes, filename: str) -> ImportedWorkbook: ...

    def template_bytes(self) -> bytes: ...
