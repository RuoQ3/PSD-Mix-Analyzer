"""Use cases hand their completed results directly to all figure builders."""

from dataclasses import replace

import plotly.graph_objects as go
import pytest

from psd_analyzer.application.use_cases import (
    AnalyzeRecipePSD,
    ComparePSDAnalysis,
    SimulateRecipe,
)
from psd_analyzer.domain.models.analysis_profile import AnalysisProfile, TailPolicy
from psd_analyzer.domain.models.material import MaterialBatch
from psd_analyzer.domain.models.psd import PSD, PSDMeasurement
from psd_analyzer.domain.models.recipe import (
    MixtureComponent,
    RecipeLine,
    RecipeStatus,
    RecipeVersion,
)
from psd_analyzer.infrastructure.excel import generate_excel_template, import_excel_workbook
from psd_analyzer.visualization import (
    build_key_size_comparison_figure,
    build_psd_difference_figure,
    build_psd_figure,
    build_q_comparison_figure,
)


def inputs():
    """Fourth roots 1..5 give q=.25 exactly on these measured nodes."""
    psd = PSD((1, 16, 81, 256, 625), (0, 0.25, 0.5, 0.75, 1))
    batch = MaterialBatch("batch-A", "A", "", "example-1")
    measurement = PSDMeasurement("PSD-A", batch.batch_id, "1", psd, "example", "example-v1")
    component = MixtureComponent("line-A", batch, measurement, 1)
    recipe = RecipeVersion(
        "R",
        "Example",
        "1",
        (RecipeLine("line-A", "A", 1),),
        RecipeStatus.RELEASED,
        "test-only-approval",
    )
    profile = AnalysisProfile(
        "example", "1", 1, 625, target_q=0.4, key_sizes_um=(16, 81), tail_policy=TailPolicy.CLAMP
    )
    return recipe, (component,), profile


def test_analyze_result_directly_builds_main_figure():
    recipe, components, profile = inputs()
    result = AnalyzeRecipePSD().execute(recipe, components, profile)
    figure = build_psd_figure(result)
    assert isinstance(figure, go.Figure)
    assert figure.layout.xaxis.type == "log"
    assert result.equivalent_q == pytest.approx(0.25, abs=1e-6)
    assert result.target_q == 0.4
    assert result.target_metrics.rmse > 0
    assert result.mixed_psd.cumulative_passing == (0, 0.25, 0.5, 0.75, 1)
    assert result.recipe == recipe
    assert not result.is_simulation
    assert len(figure.data) >= 2
    assert any(tuple(trace.y) == (0, 25, 50, 75, 100) for trace in figure.data)
    assert result.components == components


def test_batch_result_directly_builds_comparison_figures():
    recipe, components, profile = inputs()
    comparison = ComparePSDAnalysis().execute(recipe, components, components, profile)
    assert comparison.delta_q == 0
    assert comparison.metrics.rmse == comparison.metrics.mae == 0
    figures = (
        build_psd_figure(comparison),
        build_psd_difference_figure(comparison),
        build_key_size_comparison_figure(comparison),
        build_q_comparison_figure(comparison),
    )
    assert all(isinstance(figure, go.Figure) for figure in figures)
    assert len(figures[0].data) == 2
    assert all(value == 0 for value in figures[1].data[0].y)
    assert len(figures[2].data) == 2
    assert comparison.baseline.recipe == comparison.current.recipe == recipe


def test_excel_draft_uses_simulation_and_returns_plot_ready_data(tmp_path):
    imported = import_excel_workbook(generate_excel_template(tmp_path / "example.xlsx"))
    recipe = imported.recipes[0]
    batches = {batch.material_id: batch for batch in imported.batches}
    measurements = {item.batch_id: item for item in imported.measurements}
    components = tuple(
        MixtureComponent(
            line.line_id,
            batches[line.material_id],
            measurements[batches[line.material_id].batch_id],
            line.mass_fraction,
        )
        for line in recipe.lines
    )
    _, _, profile = inputs()
    result = SimulateRecipe().execute(recipe, components, replace(profile, target_q=None))
    assert result.is_simulation
    assert result.recipe.status == RecipeStatus.DRAFT
    assert result.target_psd is result.target_metrics is None
    assert result.equivalent_q == pytest.approx(0.25, abs=1e-6)
    assert isinstance(build_psd_figure(result), go.Figure)
