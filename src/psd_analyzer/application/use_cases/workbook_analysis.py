"""Select imported snapshots and delegate all calculation to established use cases."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import fsum
from uuid import uuid4

from ...domain.exceptions import DomainValidationError, IncompatibleComparisonError
from ...domain.models.analysis_profile import (
    DEFAULT_Q_BOUNDS,
    AnalysisProfile,
    InterpolationMethod,
    TailPolicy,
)
from ...domain.models.analysis_result import AnalysisResult, ComparisonResult
from ...domain.models.recipe import MixtureComponent, RecipeVersion
from ...domain.policies.recipe_policy import create_simulation_recipe
from ...domain.services.comparison import compare_results
from ...domain.services.interpolation import LinearInterpolator, LogLinearInterpolator
from ...domain.validation import finite, fractions
from ..dto.workbook import ImportedWorkbook
from ..exceptions import InvalidAnalysisConfiguration, MissingMaterialPSD
from .analyze_recipe import AnalyzeRecipePSD
from .compare_batches import ComparePSDAnalysis
from .compare_substitution import CompareMaterialSubstitution
from .simulate_recipe import SimulateRecipe


@dataclass(frozen=True)
class WorkbookAnalysis:
    """Stateless application facade; no file IO, UI, or database knowledge."""

    @staticmethod
    def profile(
        d_min_um: float,
        d_max_um: float,
        interpolation: str = "log-linear",
        q_min: float = DEFAULT_Q_BOUNDS[0],
        q_max: float = DEFAULT_Q_BOUNDS[1],
        target_q: float | None = None,
        key_sizes: str = "10,45,75,100,500,1000",
    ) -> AnalysisProfile:
        """Parse user configuration into the existing immutable numerical contract."""
        try:
            nodes = tuple(float(value.strip()) for value in key_sizes.split(","))
            method = InterpolationMethod(interpolation)
        except (ValueError, TypeError) as exc:
            raise InvalidAnalysisConfiguration(
                "请选择支持的插值方式；关键粒径应为逗号分隔的数值"
            ) from exc
        return AnalysisProfile(
            "interactive",
            "1",
            d_min_um,
            d_max_um,
            interpolation=method,
            tail_policy=TailPolicy.CLAMP,
            q_bounds=(q_min, q_max),
            target_q=target_q,
            key_sizes_um=nodes,
        )

    @staticmethod
    def validate_simulation_fractions(fractions_pct: Sequence[float]) -> None:
        """Validate percentages with the shared domain tolerance; never repair input."""
        try:
            values = tuple(finite(value, "mass_fraction_pct") / 100 for value in fractions_pct)
            fractions(values)
        except DomainValidationError as exc:
            detail = ""
            try:
                total = fsum(finite(value, "mass_fraction_pct") / 100 for value in fractions_pct)
                detail = (
                    f"当前合计 {total * 100:g}%，与 100% 相差 {(total - 1) * 100:+g} 个百分点。"
                )
            except (DomainValidationError, OverflowError):
                pass
            raise InvalidAnalysisConfiguration(
                detail + "模拟比例必须为非负有限数，合计 100%（质量分数容差 1e-8）"
            ) from exc

    @staticmethod
    def _analyzer(profile: AnalysisProfile) -> AnalyzeRecipePSD:
        return AnalyzeRecipePSD(
            interpolator=(
                LinearInterpolator()
                if profile.interpolation == InterpolationMethod.LINEAR
                else LogLinearInterpolator()
            )
        )

    @staticmethod
    def _component(
        workbook: ImportedWorkbook,
        line_id: str,
        measurement_id: str,
        fraction: float,
    ) -> MixtureComponent:
        measurement = next((m for m in workbook.measurements if m.psd_id == measurement_id), None)
        if measurement is None:
            raise MissingMaterialPSD(f"找不到选择的 PSD：{measurement_id}")
        batch = next((b for b in workbook.batches if b.batch_id == measurement.batch_id), None)
        if batch is None:
            raise MissingMaterialPSD(f"找不到 PSD 所属批次：{measurement.batch_id}")
        return MixtureComponent(line_id, batch, measurement, fraction)

    def _components(
        self,
        workbook: ImportedWorkbook,
        recipe: RecipeVersion,
        selections: Mapping[str, str],
    ) -> tuple[MixtureComponent, ...]:
        lines = {line.line_id: line for line in recipe.lines}
        if set(selections) - lines.keys():
            raise MissingMaterialPSD("选择中包含不存在的配方行")
        missing = [
            line.line_id
            for line in recipe.lines
            if line.mass_fraction > 0 and line.line_id not in selections
        ]
        if missing:
            raise MissingMaterialPSD(f"请选择配方行的 PSD：{', '.join(missing)}")
        return tuple(
            self._component(workbook, line.line_id, selections[line.line_id], line.mass_fraction)
            for line in recipe.lines
            if line.line_id in selections
        )

    def production(
        self,
        workbook: ImportedWorkbook,
        recipe: RecipeVersion,
        selections: Mapping[str, str],
        profile: AnalysisProfile,
    ) -> AnalysisResult:
        return self._analyzer(profile).execute(
            recipe, self._components(workbook, recipe, selections), profile
        )

    def substitute(
        self,
        workbook: ImportedWorkbook,
        recipe: RecipeVersion,
        selections: Mapping[str, str],
        replacements: Mapping[str, str],
        profile: AnalysisProfile,
    ) -> ComparisonResult:
        by_line = {line.line_id: line for line in recipe.lines}
        if not replacements or set(replacements) - by_line.keys():
            raise InvalidAnalysisConfiguration("请明确选择要替代的配方行")
        components = {
            line_id: self._component(workbook, line_id, psd_id, by_line[line_id].mass_fraction)
            for line_id, psd_id in replacements.items()
        }
        use_case = CompareMaterialSubstitution(ComparePSDAnalysis(self._analyzer(profile)))
        return use_case.execute(
            recipe, self._components(workbook, recipe, selections), components, profile
        )

    def simulation(
        self,
        workbook: ImportedWorkbook,
        recipe: RecipeVersion,
        selections: Mapping[str, str],
        fractions_pct: Mapping[str, float],
        profile: AnalysisProfile,
    ) -> AnalysisResult:
        if set(fractions_pct) != {line.line_id for line in recipe.lines}:
            raise InvalidAnalysisConfiguration("模拟比例必须对应所有配方行")
        self.validate_simulation_fractions(tuple(fractions_pct.values()))
        simulated = create_simulation_recipe(
            recipe,
            scenario_id=f"{recipe.recipe_id}:simulation:{uuid4()}",
            lines=tuple(
                replace(line, mass_fraction=fractions_pct[line.line_id] / 100)
                for line in recipe.lines
            ),
        )
        return SimulateRecipe(self._analyzer(profile)).execute(
            simulated, self._components(workbook, simulated, selections), profile
        )

    @staticmethod
    def compare_baseline(baseline: AnalysisResult, current: AnalysisResult) -> ComparisonResult:
        """Compare stored conventions as-is; incompatible histories are never silently refitted."""
        if (
            baseline.recipe is None
            or current.recipe is None
            or (baseline.recipe.recipe_id, baseline.recipe.version)
            != (current.recipe.recipe_id, current.recipe.version)
            or baseline.is_simulation
            or current.is_simulation
        ):
            raise IncompatibleComparisonError("基准与当前记录必须属于同一正式配方版本")
        return compare_results(current, baseline)
