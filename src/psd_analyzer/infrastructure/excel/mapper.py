"""Cross-record validation followed by construction of existing domain objects."""

from collections import defaultdict
from math import fsum

from ...domain.exceptions import DomainValidationError
from ...domain.models.material import DensityKind, Material, MaterialBatch
from ...domain.models.psd import PSD, DistributionBasis, PSDMeasurement
from ...domain.models.recipe import RecipeLine, RecipeVersion
from ...domain.validation import FRACTION_TOLERANCE
from .parser import SheetParser
from .records import (
    ExcelImportError,
    ImportedWorkbook,
    ImportRecords,
    MaterialImportRecord,
    MeasurementImportRecord,
    PSDImportRecord,
    RecipeImportRecord,
    SheetRow,
)


class DomainMapper:
    """Validate relationships and invariants without silently repairing user data."""

    def __init__(self, parser: SheetParser) -> None:
        self.parser = parser

    def validate(self, records: ImportRecords) -> None:
        issue = self.parser.issue
        for sheet, data in (
            ("Materials", records.materials),
            ("Measurements", records.measurements),
            ("PSD", records.psds),
            ("Recipe", records.recipes),
        ):
            if not data:
                issue(
                    SheetRow(sheet, 2, ()), "", "empty_sheet", "At least one data row is required"
                )
        materials, batch_keys = self._validate_materials(records.materials)
        measurement_keys = self._validate_measurements(records.measurements, batch_keys)
        self._validate_psds(records.psds, records.measurements, measurement_keys)
        self._validate_recipes(records.recipes, materials)

    def _validate_materials(
        self, records: tuple[MaterialImportRecord, ...]
    ) -> tuple[dict[str, MaterialImportRecord], set[str]]:
        issue = self.parser.issue
        materials: dict[str, MaterialImportRecord] = {}
        batch_keys: set[str] = set()
        for record in records:
            if record.batch_key in batch_keys:
                issue(record.source, "batch_key", "duplicate_batch", "Batch key must be unique")
            batch_keys.add(record.batch_key)
            previous = materials.get(record.material_code)
            identity = (record.material_name, record.grade, record.notes)
            if previous and identity != (previous.material_name, previous.grade, previous.notes):
                issue(
                    record.source,
                    "material_code",
                    "conflicting_material",
                    "Rows for a material must agree on name, grade and notes",
                )
            materials[record.material_code] = record
        return materials, batch_keys

    def _validate_measurements(
        self, records: tuple[MeasurementImportRecord, ...], batch_keys: set[str]
    ) -> set[str]:
        issue = self.parser.issue
        measurement_keys: set[str] = set()
        for measurement in records:
            if measurement.measurement_key in measurement_keys:
                issue(
                    measurement.source,
                    "measurement_key",
                    "duplicate_measurement",
                    "Measurement key must be unique",
                )
            measurement_keys.add(measurement.measurement_key)
            if measurement.batch_key not in batch_keys:
                issue(
                    measurement.source, "batch_key", "unknown_batch", "Referenced batch is absent"
                )
        return measurement_keys

    def _validate_psds(
        self,
        psds: tuple[PSDImportRecord, ...],
        measurements: tuple[MeasurementImportRecord, ...],
        measurement_keys: set[str],
    ) -> None:
        issue = self.parser.issue
        groups: dict[str, list[PSDImportRecord]] = defaultdict(list)
        for point in psds:
            if point.measurement_key not in measurement_keys:
                issue(
                    point.source,
                    "measurement_key",
                    "unknown_measurement",
                    "Referenced measurement is absent",
                )
            groups[point.measurement_key].append(point)
        for measurement in measurements:
            points = groups[measurement.measurement_key]
            if len(points) < 2:
                issue(
                    measurement.source,
                    "measurement_key",
                    "insufficient_psd_points",
                    "Each measurement requires at least two PSD points",
                )
            seen: set[float] = set()
            previous_point: PSDImportRecord | None = None
            for point in points:
                if point.particle_size_um in seen:
                    issue(
                        point.source,
                        "particle_size_um",
                        "duplicate_particle_size",
                        "A measurement cannot contain duplicate particle sizes",
                    )
                elif previous_point and point.particle_size_um <= previous_point.particle_size_um:
                    issue(
                        point.source,
                        "particle_size_um",
                        "nonascending_particle_size",
                        "Particle sizes must be strictly increasing in input row order",
                    )
                if (
                    previous_point
                    and point.cumulative_passing_pct < previous_point.cumulative_passing_pct
                ):
                    issue(
                        point.source,
                        "cumulative_passing_pct",
                        "nonmonotone_passing",
                        "Cumulative passing must not decrease",
                    )
                seen.add(point.particle_size_um)
                previous_point = point

    def _validate_recipes(
        self, records: tuple[RecipeImportRecord, ...], materials: dict[str, MaterialImportRecord]
    ) -> None:
        issue = self.parser.issue
        recipe_groups: dict[tuple[str, str], list[RecipeImportRecord]] = defaultdict(list)
        for line in records:
            if line.material_code not in materials:
                issue(
                    line.source,
                    "material_code",
                    "unknown_material",
                    "Referenced material is absent",
                )
            recipe_groups[(line.recipe_code, line.recipe_version)].append(line)
        for lines in recipe_groups.values():
            seen_lines: set[str] = set()
            for line in lines:
                if line.line_key in seen_lines:
                    issue(
                        line.source, "line_key", "duplicate_recipe_line", "Line key must be unique"
                    )
                seen_lines.add(line.line_key)
                if line.recipe_name != lines[0].recipe_name:
                    issue(
                        line.source,
                        "recipe_name",
                        "conflicting_recipe_name",
                        "Rows for a recipe version must agree on name",
                    )
            total = fsum(line.mass_fraction_pct / 100 for line in lines)
            if abs(total - 1.0) > FRACTION_TOLERANCE:
                issue(
                    lines[0].source,
                    "mass_fraction_pct",
                    "invalid_recipe_total",
                    f"Recipe total is {total * 100:g}%; expected 100%",
                )

    def map(self, records: ImportRecords, source_hash: str) -> ImportedWorkbook:
        """Validate everything before returning a complete set of domain objects."""
        self.validate(records)
        if self.parser.issues:
            raise ExcelImportError(tuple(self.parser.issues))
        materials, batches = self._map_materials(records.materials)
        measurements = self._map_measurements(records.measurements, records.psds, source_hash)
        recipes = self._map_recipes(records.recipes)
        if self.parser.issues:
            raise ExcelImportError(tuple(self.parser.issues))
        return ImportedWorkbook(materials, batches, measurements, recipes, source_hash)

    def _map_materials(
        self, records: tuple[MaterialImportRecord, ...]
    ) -> tuple[tuple[Material, ...], tuple[MaterialBatch, ...]]:
        materials: dict[str, Material] = {}
        batches: list[MaterialBatch] = []
        for record in records:
            try:
                materials[record.material_code] = Material(
                    record.material_code,
                    record.material_name,
                    record.grade or "",
                    record.notes or "",
                )
                batches.append(
                    MaterialBatch(
                        record.batch_key,
                        record.material_code,
                        record.supplier or "",
                        record.batch_no,
                        record.density,
                        DensityKind(record.density_kind) if record.density_kind else None,
                    )
                )
            except DomainValidationError as exc:
                self.parser.issue(record.source, "material_code", "domain_validation", str(exc))
        return tuple(materials.values()), tuple(batches)

    def _map_measurements(
        self,
        records: tuple[MeasurementImportRecord, ...],
        psds: tuple[PSDImportRecord, ...],
        source_hash: str,
    ) -> tuple[PSDMeasurement, ...]:
        measurements: list[PSDMeasurement] = []
        points: dict[str, list[PSDImportRecord]] = defaultdict(list)
        for point in psds:
            points[point.measurement_key].append(point)
        for measurement in records:
            values = points[measurement.measurement_key]
            try:
                psd = PSD(
                    tuple(p.particle_size_um for p in values),
                    tuple(p.cumulative_passing_pct / 100 for p in values),
                    DistributionBasis(measurement.basis),
                )
                measurements.append(
                    PSDMeasurement(
                        measurement.measurement_key,
                        measurement.batch_key,
                        measurement.version,
                        psd,
                        measurement.method,
                        measurement.protocol,
                        source_hash,
                    )
                )
            except DomainValidationError as exc:
                self.parser.issue(
                    measurement.source, "measurement_key", "domain_validation", str(exc)
                )
        return tuple(measurements)

    def _map_recipes(self, records: tuple[RecipeImportRecord, ...]) -> tuple[RecipeVersion, ...]:
        recipes: list[RecipeVersion] = []
        recipe_groups: dict[tuple[str, str], list[RecipeImportRecord]] = defaultdict(list)
        for line in records:
            recipe_groups[(line.recipe_code, line.recipe_version)].append(line)
        for (code, version), lines in recipe_groups.items():
            try:
                recipes.append(
                    RecipeVersion(
                        code,
                        lines[0].recipe_name,
                        version,
                        tuple(
                            RecipeLine(
                                line.line_key, line.material_code, line.mass_fraction_pct / 100
                            )
                            for line in lines
                        ),
                    )
                )
            except DomainValidationError as exc:
                self.parser.issue(lines[0].source, "recipe_code", "domain_validation", str(exc))
        return tuple(recipes)
