"""Lossless relational mapping of existing domain results, without executing algorithms."""

from dataclasses import asdict
from typing import Any

from sqlalchemy import Connection, Table, insert, select

from ...domain.models.analysis_profile import AnalysisProfile, InterpolationMethod, TailPolicy
from ...domain.models.analysis_result import (
    AnalysisResult,
    Diagnostic,
    ErrorMetrics,
    EvaluatedCurve,
    FitResult,
    FitStatus,
    KeyPassing,
)
from ...domain.models.material import DensityKind, MaterialBatch
from ...domain.models.psd import PSD, DistributionBasis, PSDMeasurement
from ...domain.models.recipe import MixtureComponent, RecipeLine, RecipeStatus, RecipeVersion
from . import schema as s


def _insert_many(connection: Connection, table: Table, rows: list[dict[str, Any]]) -> None:
    if rows:
        connection.execute(insert(table), rows)


def write_points(
    connection: Connection,
    snapshot_id: str,
    curve: str,
    sizes: tuple[float, ...],
    passing: tuple[float | None, ...],
) -> None:
    _insert_many(
        connection,
        s.points,
        [
            dict(snapshot_id=snapshot_id, curve=curve, position=i, particle_size=d, passing=p)
            for i, (d, p) in enumerate(zip(sizes, passing, strict=True))
        ],
    )


def write_keys(
    connection: Connection, snapshot_id: str, values: tuple[KeyPassing, ...], role: str = "current"
) -> None:
    _insert_many(
        connection,
        s.keys,
        [
            dict(
                snapshot_id=snapshot_id,
                role=role,
                position=i,
                particle_size=k.particle_size_um,
                passing=k.cumulative_passing,
                reason=k.reason,
            )
            for i, k in enumerate(values)
        ],
    )


def write_metrics(
    connection: Connection, snapshot_id: str, role: str, value: ErrorMetrics | None
) -> None:
    if value is not None:
        connection.execute(
            insert(s.metrics).values(snapshot_id=snapshot_id, role=role, **asdict(value))
        )


def write_snapshot(
    connection: Connection, analysis_id: str, role: str, result: AnalysisResult
) -> str:
    snapshot_id = f"{analysis_id}:{role}"
    fit = asdict(result.fit)
    fit.pop("metrics")
    recipe = result.recipe
    curve_bases = {
        name: curve.basis
        for name, curve in (
            ("mixed", result.mixed_curve),
            ("fitted", result.fitted_curve),
            ("target", result.target_curve),
        )
        if curve is not None
    }
    connection.execute(
        insert(s.snapshots).values(
            snapshot_id=snapshot_id,
            analysis_id=analysis_id,
            role=role,
            profile=asdict(result.profile),
            fit=fit,
            curve_bases=curve_bases,
            input_fraction_sum=result.input_fraction_sum,
            algorithm_version=result.algorithm_version,
            is_simulation=result.is_simulation,
            recipe_id=None if recipe is None else recipe.recipe_id,
            recipe_name=None if recipe is None else recipe.name,
            recipe_version=None if recipe is None else recipe.version,
            recipe_status=None if recipe is None else recipe.status,
            approval_reference=None if recipe is None else recipe.approval_reference,
        )
    )
    for name, curve in (
        ("mixed", result.mixed_curve),
        ("fitted", result.fitted_curve),
        ("target", result.target_curve),
    ):
        if curve is not None:
            write_points(
                connection, snapshot_id, name, curve.particle_size_um, curve.cumulative_passing
            )
    write_keys(connection, snapshot_id, result.key_passing)
    for name, value in (
        ("fit", result.fit_metrics),
        ("target", result.target_metrics),
        ("optimizer", result.fit.metrics),
    ):
        write_metrics(connection, snapshot_id, name, value)
    _insert_many(
        connection,
        s.diagnostics,
        [
            dict(snapshot_id=snapshot_id, position=i, **asdict(value))
            for i, value in enumerate(result.diagnostics)
        ],
    )
    if recipe is not None:
        _insert_many(
            connection,
            s.recipe_lines,
            [
                dict(snapshot_id=snapshot_id, position=i, **asdict(line))
                for i, line in enumerate(recipe.lines)
            ],
        )
    if len(result.actual_weights) != len(result.components):
        raise ValueError("Actual weight count must match component count")
    for i, component in enumerate(result.components):
        batch, measurement = component.batch, component.measurement
        psd = measurement.psd
        connection.execute(
            insert(s.materials).values(
                snapshot_id=snapshot_id,
                position=i,
                line_id=component.line_id,
                **asdict(batch),
                mass_fraction=component.mass_fraction,
                actual_weight=result.actual_weights[i],
                uniform_density_confirmed=component.uniform_density_confirmed,
                psd_id=measurement.psd_id,
                measurement_version=measurement.version,
                method=measurement.method,
                protocol_id=measurement.protocol_id,
                source_hash=measurement.source_hash,
                basis=psd.basis,
                lower_tail_confirmed=psd.lower_tail_confirmed,
                upper_tail_confirmed=psd.upper_tail_confirmed,
            )
        )
        write_points(
            connection, snapshot_id, f"source:{i}", psd.particle_size_um, psd.cumulative_passing
        )
    return snapshot_id


def rows(connection: Connection, table: Table, snapshot_id: str) -> list[dict[str, Any]]:
    statement = select(table).where(table.c.snapshot_id == snapshot_id)
    if "position" in table.c:
        statement = statement.order_by(table.c.position)
    return [dict(row) for row in connection.execute(statement).mappings()]


def read_metrics(connection: Connection, snapshot_id: str, role: str) -> ErrorMetrics | None:
    row = (
        connection.execute(
            select(s.metrics).where(
                s.metrics.c.snapshot_id == snapshot_id, s.metrics.c.role == role
            )
        )
        .mappings()
        .first()
    )
    return (
        None
        if row is None
        else ErrorMetrics(
            rmse=row["rmse"],
            mae=row["mae"],
            sse=row["sse"],
            max_absolute_deviation=row["max_absolute_deviation"],
            n=row["n"],
        )
    )


def read_keys(
    connection: Connection, snapshot_id: str, role: str = "current"
) -> tuple[KeyPassing, ...]:
    return tuple(
        KeyPassing(row["particle_size"], row["passing"], row["reason"])
        for row in rows(connection, s.keys, snapshot_id)
        if row["role"] == role
    )


def read_snapshot(connection: Connection, snapshot_id: str) -> AnalysisResult:
    row = (
        connection.execute(select(s.snapshots).where(s.snapshots.c.snapshot_id == snapshot_id))
        .mappings()
        .one()
    )
    config = dict(row["profile"])
    config["mix_basis"] = DistributionBasis(config["mix_basis"])
    config["interpolation"] = InterpolationMethod(config["interpolation"])
    config["tail_policy"] = TailPolicy(config["tail_policy"])
    profile = AnalysisProfile(**config)
    curve_rows = rows(connection, s.points, snapshot_id)

    def curve(name: str, basis: str) -> EvaluatedCurve:
        selected = [point for point in curve_rows if point["curve"] == name]
        return EvaluatedCurve(
            tuple(p["particle_size"] for p in selected),
            tuple(p["passing"] for p in selected),
            DistributionBasis(basis),
        )

    components: list[MixtureComponent] = []
    weights: list[float] = []
    for item in rows(connection, s.materials, snapshot_id):
        batch = MaterialBatch(
            item["batch_id"],
            item["material_id"],
            item["supplier"],
            item["batch_no"],
            item["density_kg_m3"],
            None if item["density_kind"] is None else DensityKind(item["density_kind"]),
        )
        source = curve(f"source:{item['position']}", item["basis"])
        psd = PSD(
            source.particle_size_um,
            tuple(v for v in source.cumulative_passing if v is not None),
            source.basis,
            item["lower_tail_confirmed"],
            item["upper_tail_confirmed"],
        )
        measurement = PSDMeasurement(
            item["psd_id"],
            item["batch_id"],
            item["measurement_version"],
            psd,
            item["method"],
            item["protocol_id"],
            item["source_hash"],
        )
        components.append(
            MixtureComponent(
                item["line_id"],
                batch,
                measurement,
                item["mass_fraction"],
                item["uniform_density_confirmed"],
            )
        )
        weights.append(item["actual_weight"])
    recipe = None
    if row["recipe_id"] is not None:
        lines = tuple(
            RecipeLine(
                item["line_id"],
                item["material_id"],
                item["mass_fraction"],
                tuple(item["allowed_material_ids"]),
            )
            for item in rows(connection, s.recipe_lines, snapshot_id)
        )
        recipe = RecipeVersion(
            row["recipe_id"],
            row["recipe_name"],
            row["recipe_version"],
            lines,
            RecipeStatus(row["recipe_status"]),
            row["approval_reference"],
        )
    fit_data = dict(row["fit"])
    fit_data["status"] = FitStatus(fit_data["status"])
    fit = FitResult(**fit_data, metrics=read_metrics(connection, snapshot_id, "optimizer"))
    bases = row["curve_bases"]
    return AnalysisResult(
        profile,
        tuple(components),
        curve("mixed", bases["mixed"]),
        fit,
        curve("fitted", bases["fitted"]) if "fitted" in bases else None,
        curve("target", bases["target"]) if "target" in bases else None,
        read_metrics(connection, snapshot_id, "fit"),
        read_metrics(connection, snapshot_id, "target"),
        read_keys(connection, snapshot_id),
        tuple(
            Diagnostic(item["code"], item["message"])
            for item in rows(connection, s.diagnostics, snapshot_id)
        ),
        tuple(weights),
        row["input_fraction_sum"],
        row["algorithm_version"],
        recipe,
        row["is_simulation"],
    )
