"""Atomic SQLite storage and SQL-filtered history summaries."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, and_, exists, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from ...application.dto.history import (
    AnalysisConflict,
    AnalysisNotFound,
    AnalysisSummary,
    AnalysisType,
    HistoryError,
    HistoryFilter,
    RepositoryError,
    StoredAnalysis,
)
from ...domain.models.analysis_result import ComparisonResult, Diagnostic, FitStatus
from ..persistence import schema as s
from ..persistence.database import DEFAULT_DATABASE_PATH, init_db
from ..persistence.snapshots import (
    read_keys,
    read_metrics,
    read_snapshot,
    rows,
    write_keys,
    write_metrics,
    write_points,
    write_snapshot,
)


def _baseline_clause() -> Any:
    return exists(
        select(s.baselines.c.analysis_id).where(
            s.baselines.c.analysis_id == s.analyses.c.analysis_id
        )
    )


class SqlAlchemyAnalysisRepository:
    """One transaction per command, one short-lived connection per read."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save_analysis(self, analysis: StoredAnalysis) -> StoredAnalysis:
        """Identical UUID/content is a no-op; changed content never overwrites history."""
        try:
            with self.engine.begin() as connection:
                # Serialize competing writers before the idempotency check.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                existing = connection.execute(
                    select(s.analyses.c.analysis_id).where(
                        s.analyses.c.analysis_id == analysis.analysis_id
                    )
                ).first()
                if existing is not None:
                    saved = self._get(connection, analysis.analysis_id)
                    if (
                        saved.result != analysis.result
                        or saved.analysis_type != analysis.analysis_type
                    ):
                        raise AnalysisConflict(
                            "This analysis UUID already belongs to another result"
                        )
                    return saved
                if analysis.is_baseline:
                    raise HistoryError("Save first, then explicitly select a baseline")
                result = analysis.current
                recipe = result.recipe
                assert recipe is not None
                metric = result.target_metrics or result.fit_metrics
                comparison = (
                    analysis.result if isinstance(analysis.result, ComparisonResult) else None
                )
                metadata = (
                    None
                    if comparison is None
                    else {
                        "delta_q": comparison.delta_q,
                        "max_absolute_deviation": comparison.max_absolute_deviation,
                        "diagnostics": [asdict(value) for value in comparison.diagnostics],
                    }
                )
                connection.execute(
                    insert(s.analyses).values(
                        analysis_id=analysis.analysis_id,
                        created_at=analysis.created_at.isoformat(),
                        analysis_type=analysis.analysis_type,
                        recipe_id=recipe.recipe_id,
                        recipe_name=recipe.name,
                        recipe_version=recipe.version,
                        equivalent_q=result.equivalent_q,
                        target_q=result.target_q,
                        d_min=result.profile.d_min_um,
                        d_max=result.profile.d_max_um,
                        interpolation_method=result.profile.interpolation,
                        packing_model=result.profile.model_id,
                        sse=None if metric is None else metric.sse,
                        rmse=None if metric is None else metric.rmse,
                        mae=None if metric is None else metric.mae,
                        max_absolute_deviation=None
                        if metric is None
                        else metric.max_absolute_deviation,
                        fit_status=result.fit.status,
                        comparison_metadata=metadata,
                        convention_key=hashlib.sha256(
                            json.dumps(
                                {
                                    "profile": asdict(result.profile),
                                    "algorithm": result.algorithm_version,
                                    "grid": result.mixed_curve.particle_size_um,
                                    "protocols": [
                                        (
                                            c.line_id,
                                            c.mass_fraction,
                                            c.measurement.method,
                                            c.measurement.protocol_id,
                                        )
                                        for c in result.components
                                    ],
                                },
                                sort_keys=True,
                            ).encode()
                        ).hexdigest(),
                    )
                )
                snapshot_id = write_snapshot(connection, analysis.analysis_id, "current", result)
                if comparison is not None:
                    assert comparison.baseline is not None
                    write_snapshot(
                        connection, analysis.analysis_id, "baseline", comparison.baseline
                    )
                    write_points(
                        connection,
                        snapshot_id,
                        "delta",
                        comparison.particle_size_um,
                        comparison.delta_psd,
                    )
                    write_keys(connection, snapshot_id, comparison.key_delta, "delta")
                    write_metrics(connection, snapshot_id, "comparison", comparison.metrics)
            return analysis
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise RepositoryError(
                "Unable to save analysis; the transaction was rolled back"
            ) from exc

    def _get(self, connection: Connection, analysis_id: str) -> StoredAnalysis:
        row = (
            connection.execute(
                select(s.analyses, _baseline_clause().label("is_baseline")).where(
                    s.analyses.c.analysis_id == analysis_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise AnalysisNotFound("The selected analysis no longer exists")
        current = read_snapshot(connection, f"{analysis_id}:current")
        meta = row["comparison_metadata"]
        result = current
        if meta is not None:
            snapshot_id = f"{analysis_id}:current"
            delta = [p for p in rows(connection, s.points, snapshot_id) if p["curve"] == "delta"]
            comparison = ComparisonResult(
                tuple(p["particle_size"] for p in delta),
                tuple(p["passing"] for p in delta),
                meta["delta_q"],
                read_keys(connection, snapshot_id, "delta"),
                meta["max_absolute_deviation"],
                tuple(Diagnostic(**d) for d in meta["diagnostics"]),
                read_snapshot(connection, f"{analysis_id}:baseline"),
                current,
                read_metrics(connection, snapshot_id, "comparison"),
            )
            return StoredAnalysis(
                analysis_id,
                datetime.fromisoformat(row["created_at"]),
                AnalysisType(row["analysis_type"]),
                comparison,
                row["is_baseline"],
            )
        return StoredAnalysis(
            analysis_id,
            datetime.fromisoformat(row["created_at"]),
            AnalysisType(row["analysis_type"]),
            result,
            row["is_baseline"],
        )

    def get_analysis(self, analysis_id: str) -> StoredAnalysis:
        try:
            with self.engine.connect() as connection:
                return self._get(connection, analysis_id)
        except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise RepositoryError("Unable to restore the saved analysis") from exc

    def list_analyses(self, filters: HistoryFilter) -> tuple[AnalysisSummary, ...]:
        """Only summary columns; PSD points are never loaded by this query."""
        statement = select(s.analyses, _baseline_clause().label("is_baseline"))
        for name in ("recipe_id", "recipe_version", "analysis_type"):
            value = getattr(filters, name)
            if value is not None:
                statement = statement.where(s.analyses.c[name] == value)
        if filters.date_from is not None:
            statement = statement.where(s.analyses.c.created_at >= filters.date_from.isoformat())
        if filters.date_to is not None:
            statement = statement.where(s.analyses.c.created_at <= filters.date_to.isoformat())
        if filters.batch_no is not None:
            statement = statement.where(
                exists(
                    select(s.materials.c.snapshot_id)
                    .join(s.snapshots, s.snapshots.c.snapshot_id == s.materials.c.snapshot_id)
                    .where(
                        s.snapshots.c.analysis_id == s.analyses.c.analysis_id,
                        s.materials.c.batch_no == filters.batch_no,
                    )
                )
            )
        statement = statement.order_by(
            s.analyses.c.created_at.desc(), s.analyses.c.analysis_id
        ).limit(filters.limit)
        try:
            with self.engine.connect() as connection:
                return tuple(
                    AnalysisSummary(
                        row["analysis_id"],
                        datetime.fromisoformat(row["created_at"]),
                        AnalysisType(row["analysis_type"]),
                        row["recipe_id"],
                        row["recipe_name"],
                        row["recipe_version"],
                        row["equivalent_q"],
                        row["target_q"],
                        row["rmse"],
                        row["mae"],
                        row["max_absolute_deviation"],
                        row["is_baseline"],
                        FitStatus(row["fit_status"]),
                        row["convention_key"],
                    )
                    for row in connection.execute(statement).mappings()
                )
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise RepositoryError("Unable to query analysis history") from exc

    def set_baseline(self, analysis_id: str) -> None:
        """The association primary key permits one production baseline per recipe version."""
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        select(s.analyses).where(s.analyses.c.analysis_id == analysis_id)
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    raise AnalysisNotFound("The selected analysis no longer exists")
                if row["analysis_type"] != AnalysisType.PRODUCTION_MONITORING:
                    raise HistoryError("Only production monitoring can be a default baseline")
                statement = (
                    sqlite_insert(s.baselines)
                    .values(
                        recipe_id=row["recipe_id"],
                        recipe_version=row["recipe_version"],
                        analysis_id=analysis_id,
                    )
                    .on_conflict_do_update(
                        index_elements=[s.baselines.c.recipe_id, s.baselines.c.recipe_version],
                        set_={"analysis_id": analysis_id},
                    )
                )
                connection.execute(statement)
        except SQLAlchemyError as exc:
            raise RepositoryError("Unable to change the default baseline") from exc

    def get_baseline(self, recipe_id: str, recipe_version: str) -> StoredAnalysis | None:
        try:
            with self.engine.connect() as connection:
                analysis_id = connection.execute(
                    select(s.baselines.c.analysis_id).where(
                        and_(
                            s.baselines.c.recipe_id == recipe_id,
                            s.baselines.c.recipe_version == recipe_version,
                        )
                    )
                ).scalar_one_or_none()
                return None if analysis_id is None else self._get(connection, analysis_id)
        except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise RepositoryError("Unable to restore the default baseline") from exc


def create_repository(path: str | Path = DEFAULT_DATABASE_PATH) -> SqlAlchemyAnalysisRepository:
    """Build and initialize an explicitly configured SQLite repository."""
    return SqlAlchemyAnalysisRepository(init_db(path))
