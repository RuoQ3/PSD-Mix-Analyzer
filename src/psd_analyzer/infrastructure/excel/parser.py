"""Parse cells into typed input records; percentages remain on a 0..100 scale here."""

import math
import re

from .records import (
    ImportIssue,
    ImportRecords,
    MaterialImportRecord,
    MeasurementImportRecord,
    PSDImportRecord,
    RecipeImportRecord,
    SheetRow,
)


class SheetParser:
    """Collect independent cell failures, keeping original values and Excel row numbers."""

    def __init__(self, filename: str, issues: list[ImportIssue]) -> None:
        self.filename = filename
        self.issues = issues

    def issue(self, row: SheetRow, column: str, code: str, message: str) -> None:
        self.issues.append(
            ImportIssue(
                self.filename, row.sheet, row.row, column, row.cell(column).value, code, message
            )
        )

    def text(self, row: SheetRow, column: str, *, optional: bool = False) -> str | None:
        cell = row.cell(column)
        if cell.is_formula:
            self.issue(
                row, column, "formula_not_supported", "Replace formula with an explicit value"
            )
            return None
        value = cell.value
        if value is None or (isinstance(value, str) and not value.strip()):
            if not optional:
                self.issue(row, column, "required_value", "A nonblank text value is required")
            return None
        if not isinstance(value, str):
            self.issue(
                row, column, "invalid_text", "Expected text, preserving identifier formatting"
            )
            return None
        return value.strip()

    def number(
        self, row: SheetRow, column: str, *, optional: bool = False, percent: bool = False
    ) -> float | None:
        cell = row.cell(column)
        if cell.is_formula:
            self.issue(
                row, column, "formula_not_supported", "Replace formula with an explicit value"
            )
            return None
        raw = cell.value
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if not optional:
                self.issue(row, column, "required_value", "A numeric value is required")
            return None
        try:
            if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
                raise ValueError("Expected a number")
            text_percent = isinstance(raw, str) and raw.strip().endswith("%")
            numeric = raw.strip()[:-1].strip() if text_percent and isinstance(raw, str) else raw
            value = float(numeric)
            if text_percent and not percent:
                raise ValueError("Percent notation is only allowed in percentage columns")
            # Only a real Excel percentage format changes numeric-cell units. Never guess by value.
            format_code = re.sub(r'"[^\"]*"|\\.', "", cell.number_format)
            if percent and not isinstance(raw, str) and "%" in format_code:
                value *= 100
            if not math.isfinite(value):
                raise ValueError("Value must be finite (NaN and infinity are not allowed)")
        except (ValueError, OverflowError) as exc:
            self.issue(row, column, "invalid_number", str(exc))
            return None
        if percent and not 0 <= value <= 100:
            self.issue(row, column, "percentage_out_of_range", "Percentage must be within [0, 100]")
            return None
        if column in ("particle_size_um", "density") and value <= 0:
            self.issue(row, column, "nonpositive_value", "Value must be greater than zero")
            return None
        return value

    def parse(self, rows: tuple[SheetRow, ...]) -> ImportRecords:
        """Parse all sheets, retaining all independent row issues before domain mapping."""
        return ImportRecords(
            tuple(
                material_record
                for row in rows
                if row.sheet == "Materials"
                if (material_record := self._material(row)) is not None
            ),
            tuple(
                measurement_record
                for row in rows
                if row.sheet == "Measurements"
                if (measurement_record := self._measurement(row)) is not None
            ),
            tuple(
                psd_record
                for row in rows
                if row.sheet == "PSD"
                if (psd_record := self._psd(row)) is not None
            ),
            tuple(
                recipe_record
                for row in rows
                if row.sheet == "Recipe"
                if (recipe_record := self._recipe(row)) is not None
            ),
        )

    def _material(self, row: SheetRow) -> MaterialImportRecord | None:
        count = len(self.issues)
        material = self.text(row, "material_code")
        name = self.text(row, "material_name")
        batch = self.text(row, "batch_key")
        batch_no = self.text(row, "batch_no")
        supplier = self.text(row, "supplier", optional=True)
        grade = self.text(row, "grade", optional=True)
        notes = self.text(row, "notes", optional=True)
        density = self.number(row, "density", optional=True)
        kind = self.text(row, "density_kind", optional=True)
        if (density is None) != (kind is None):
            self.issue(row, "density_kind", "density_pair", "Supply density and kind together")
        if kind is not None and kind not in ("particle", "true", "bulk"):
            self.issue(row, "density_kind", "invalid_density_kind", "Use particle, true or bulk")
        if len(self.issues) == count:
            assert material and name and batch and batch_no
            return MaterialImportRecord(
                row, material, name, batch, batch_no, supplier, grade, notes, density, kind
            )
        return None

    def _measurement(self, row: SheetRow) -> MeasurementImportRecord | None:
        count = len(self.issues)
        measurement = self.text(row, "measurement_key")
        batch = self.text(row, "batch_key")
        basis = self.text(row, "basis")
        method = self.text(row, "method")
        protocol = self.text(row, "protocol")
        version = self.text(row, "version", optional=True) or "1"
        if basis is not None and basis not in ("mass", "volume", "number", "unknown"):
            self.issue(row, "basis", "invalid_basis", "Use mass, volume, number or unknown")
        if len(self.issues) == count:
            assert measurement and batch and basis and method and protocol
            return MeasurementImportRecord(
                row, measurement, batch, basis, method, protocol, version
            )
        return None

    def _psd(self, row: SheetRow) -> PSDImportRecord | None:
        count = len(self.issues)
        measurement = self.text(row, "measurement_key")
        size = self.number(row, "particle_size_um")
        passing = self.number(row, "cumulative_passing_pct", percent=True)
        if len(self.issues) == count:
            assert measurement and size is not None and passing is not None
            return PSDImportRecord(row, measurement, size, passing)
        return None

    def _recipe(self, row: SheetRow) -> RecipeImportRecord | None:
        count = len(self.issues)
        recipe = self.text(row, "recipe_code")
        name = self.text(row, "recipe_name", optional=True) or recipe
        version = self.text(row, "recipe_version")
        line = self.text(row, "line_key")
        material = self.text(row, "material_code")
        fraction = self.number(row, "mass_fraction_pct", percent=True)
        if len(self.issues) == count:
            assert recipe and name and version and line and material and fraction is not None
            return RecipeImportRecord(row, recipe, name, version, line, material, fraction)
        return None
