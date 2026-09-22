"""Snapshot persistence, transaction boundaries, typed filters and history use cases."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from psd_analyzer.application.dto.history import (
    AnalysisConflict,
    AnalysisNotFound,
    AnalysisType,
    HistoryError,
    HistoryFilter,
    RepositoryError,
    StoredAnalysis,
)
from psd_analyzer.application.use_cases import AnalyzeRecipePSD, CompareMaterialSubstitution
from psd_analyzer.application.use_cases.history import (
    CompareHistoricalAnalyses,
    GetAnalysisDetail,
    GetBaselineAnalysis,
    ListAnalysisHistory,
    SaveAnalysis,
    SetBaselineAnalysis,
)
from psd_analyzer.domain.exceptions import IncompatibleComparisonError
from psd_analyzer.domain.models.analysis_result import Diagnostic, FitResult, FitStatus
from psd_analyzer.domain.models.recipe import RecipeLine, RecipeStatus, RecipeVersion
from psd_analyzer.infrastructure.persistence import create_repository, init_db, schema


@pytest.fixture
def repository(tmp_path):
    repo = create_repository(tmp_path / "history.sqlite")
    yield repo
    repo.engine.dispose()


@pytest.fixture
def result(component, profile):
    c = component()
    recipe = RecipeVersion(
        "R", "Recipe", "v1", (RecipeLine("A", "m1", 1),), RecipeStatus.RELEASED, "approval-1"
    )
    return AnalyzeRecipePSD().execute(recipe, [c], profile)


def save(
    repository, result, *, kind=AnalysisType.PRODUCTION_MONITORING, when=None, identifier=None
):
    return SaveAnalysis(repository).execute(
        result, kind, analysis_id=identifier or str(uuid4()), created_at=when
    )


def test_complete_round_trip_preserves_source_psd_recipe_metrics_and_metadata(repository, result):
    result = replace(result, diagnostics=(Diagnostic("test", "Reason"),))
    stored = save(repository, result)
    restored = GetAnalysisDetail(repository).execute(stored.analysis_id)
    assert restored == stored
    assert restored.current.mixed_curve == result.mixed_curve
    assert restored.current.key_passing == result.key_passing
    assert restored.current.components == result.components
    assert restored.current.fit == result.fit
    assert restored.current.recipe == result.recipe
    assert restored.created_at.tzinfo == UTC


def test_optional_target_and_failed_fit_round_trip(repository, result):
    result = replace(
        result,
        profile=replace(result.profile, target_q=None),
        target_curve=None,
        target_metrics=None,
        fit=FitResult(FitStatus.FAILED, message="No convergence"),
        fitted_curve=None,
        fit_metrics=None,
    )
    stored = save(repository, result)
    assert repository.get_analysis(stored.analysis_id) == stored
    assert repository.list_analyses(HistoryFilter())[0].rmse is None


def test_substitution_round_trip_includes_both_snapshots_and_signed_delta(
    repository, result, component
):
    alternative = component(material="candidate", batch_id="replacement", passing=(0, 0.3, 1))
    comparison = CompareMaterialSubstitution().execute(
        result.recipe, result.components, {"A": alternative}, result.profile
    )
    stored = save(repository, comparison, kind=AnalysisType.MATERIAL_SUBSTITUTION)
    assert repository.get_analysis(stored.analysis_id) == stored
    assert stored.current.components[0].batch.material_id == "candidate"


def test_summary_query_does_not_read_psd_or_load_full_snapshots(repository, result):
    stored = save(repository, result)
    sql = []

    def record(connection, cursor, statement, parameters, context, executemany):
        sql.append(statement)

    event.listen(repository.engine, "before_cursor_execute", record)
    summaries = ListAnalysisHistory(repository).execute()
    event.remove(repository.engine, "before_cursor_execute", record)
    assert len(summaries) == 1
    assert summaries[0].analysis_id == stored.analysis_id
    assert len(summaries[0].convention_key) == 64
    assert len(sql) == 1
    assert "analysis_psd_points" not in sql[0]
    assert "analysis_snapshots" not in sql[0]


def test_sql_filters_recipe_version_date_type_and_batch(repository, result):
    when = datetime(2026, 1, 1, tzinfo=UTC)
    first = save(repository, result, when=when)
    other = replace(result, recipe=replace(result.recipe, recipe_id="OTHER", version="v2"))
    second = save(repository, other, when=when + timedelta(days=2))
    assert (
        repository.list_analyses(HistoryFilter(recipe_id="R"))[0].analysis_id == first.analysis_id
    )
    assert (
        repository.list_analyses(HistoryFilter(recipe_version="v2"))[0].analysis_id
        == second.analysis_id
    )
    assert len(repository.list_analyses(HistoryFilter(date_from=when, date_to=when))) == 1
    assert len(repository.list_analyses(HistoryFilter(batch_no="lot-1"))) == 2
    assert not repository.list_analyses(HistoryFilter(batch_no="unknown"))
    assert not repository.list_analyses(HistoryFilter(analysis_type=AnalysisType.RECIPE_SIMULATION))
    assert len(repository.list_analyses(HistoryFilter(limit=1))) == 1


def test_baseline_switch_is_explicit_unique_and_version_scoped(repository, result):
    first, second = save(repository, result), save(repository, result)
    assert GetBaselineAnalysis(repository).execute("R", "v1") is None
    SetBaselineAnalysis(repository).execute(first.analysis_id)
    assert repository.get_analysis(first.analysis_id).is_baseline
    repository.set_baseline(second.analysis_id)
    assert not repository.get_analysis(first.analysis_id).is_baseline
    assert repository.get_baseline("R", "v1").analysis_id == second.analysis_id
    assert repository.get_baseline("R", "v2") is None
    assert sum(s.is_baseline for s in repository.list_analyses(HistoryFilter())) == 1


def test_simulation_type_is_preserved_and_cannot_be_baseline(repository, result):
    simulation = replace(
        result, is_simulation=True, recipe=replace(result.recipe, status=RecipeStatus.DRAFT)
    )
    stored = save(repository, simulation, kind=AnalysisType.RECIPE_SIMULATION)
    assert repository.get_analysis(stored.analysis_id).current.is_simulation
    assert (
        len(repository.list_analyses(HistoryFilter(analysis_type=AnalysisType.RECIPE_SIMULATION)))
        == 1
    )
    with pytest.raises(HistoryError, match="production"):
        repository.set_baseline(stored.analysis_id)
    with pytest.raises(HistoryError, match="disagree"):
        save(repository, replace(result, is_simulation=True))
    with pytest.raises(HistoryError, match="draft"):
        save(repository, replace(result, is_simulation=True), kind=AnalysisType.RECIPE_SIMULATION)
    with pytest.raises(HistoryError, match="released"):
        save(repository, replace(result, recipe=replace(result.recipe, status=RecipeStatus.DRAFT)))


def test_uuid_idempotence_and_conflict_do_not_overwrite_snapshot(repository, result):
    identifier = str(uuid4())
    first = save(repository, result, identifier=identifier)
    second = save(
        repository, result, identifier=identifier, when=first.created_at + timedelta(days=1)
    )
    assert second == first
    assert len(repository.list_analyses(HistoryFilter())) == 1
    with pytest.raises(AnalysisConflict):
        save(repository, replace(result, algorithm_version="different"), identifier=identifier)
    assert repository.get_analysis(identifier) == first


def test_partial_insert_failure_rolls_back_all_tables(repository, result, monkeypatch):
    import psd_analyzer.infrastructure.repositories.analysis as module

    original = module.write_snapshot

    def fail(connection, analysis_id, role, result):
        original(connection, analysis_id, role, result)
        raise OperationalError("insert", {}, RuntimeError("disk failure"))

    monkeypatch.setattr(module, "write_snapshot", fail)
    with pytest.raises(RepositoryError, match="rolled back"):
        save(repository, result)
    with repository.engine.connect() as connection:
        for table in schema.metadata.sorted_tables:
            assert connection.execute(select(func.count()).select_from(table)).scalar_one() == 0


def test_missing_ids_and_database_failures_are_application_errors(repository):
    identifier = str(uuid4())
    with pytest.raises(AnalysisNotFound):
        repository.get_analysis(identifier)
    with pytest.raises(AnalysisNotFound):
        repository.set_baseline(identifier)
    schema.analyses.drop(repository.engine)
    with pytest.raises(RepositoryError):
        repository.list_analyses(HistoryFilter())
    with pytest.raises(RepositoryError):
        repository.get_analysis(identifier)


def test_history_comparison_uses_existing_service_and_rejects_incompatible_profiles(
    repository, result
):
    first, second = save(repository, result), save(repository, result)
    comparison = CompareHistoricalAnalyses(repository).execute(
        first.analysis_id, second.analysis_id
    )
    assert comparison.max_absolute_deviation == 0
    changed = save(repository, replace(result, profile=replace(result.profile, target_q=0.4)))
    with pytest.raises(IncompatibleComparisonError):
        CompareHistoricalAnalyses(repository).execute(first.analysis_id, changed.analysis_id)
    keys = {s.convention_key for s in repository.list_analyses(HistoryFilter())}
    assert len(keys) == 2


def test_utc_normalization_and_request_validation(repository, result):
    local = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    stored = save(repository, result, when=local)
    assert stored.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert repository.get_analysis(stored.analysis_id).created_at.tzinfo == UTC
    with pytest.raises(HistoryError, match="timezone"):
        save(repository, result, when=datetime(2026, 1, 1))
    with pytest.raises(HistoryError, match="UUID"):
        save(repository, result, identifier="invalid")
    with pytest.raises(HistoryError):
        HistoryFilter(date_from=local, date_to=local - timedelta(days=1))
    with pytest.raises(HistoryError):
        HistoryFilter(limit=0)
    with pytest.raises(HistoryError):
        StoredAnalysis(str(uuid4()), local, "prod", result)


def test_database_initialization_is_explicit_and_temporary(tmp_path):
    path = tmp_path / "nested" / "new.db"
    engine = init_db(path)
    assert path.exists()
    engine.dispose()
    repository = create_repository(":memory:")
    assert repository.list_analyses(HistoryFilter()) == ()
    repository.engine.dispose()


def test_missing_curve_points_and_key_reasons_are_preserved(repository, result):
    mixed = replace(result.mixed_curve, cumulative_passing=(None, 0.5, 1.0))
    result = replace(result, mixed_curve=mixed)
    saved = save(repository, result)
    assert repository.get_analysis(saved.analysis_id) == saved
    assert saved.current.key_passing[-1].cumulative_passing is None
    assert saved.current.key_passing[-1].reason


def test_concurrent_duplicate_saves_keep_one_atomic_record(repository, result):
    from concurrent.futures import ThreadPoolExecutor

    identifier = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save, repository, result, identifier=identifier) for _ in range(2)]
        first, second = [future.result() for future in futures]
    assert first == second
    assert len(repository.list_analyses(HistoryFilter())) == 1


def test_failing_baseline_switch_preserves_existing_association(repository, result):
    first = save(repository, result)
    repository.set_baseline(first.analysis_id)
    with pytest.raises(AnalysisNotFound):
        repository.set_baseline(str(uuid4()))
    assert repository.get_baseline("R", "v1").analysis_id == first.analysis_id


def test_initialization_failure_is_a_repository_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("occupied")
    with pytest.raises(RepositoryError, match="initialize"):
        init_db(blocker / "db.sqlite")
