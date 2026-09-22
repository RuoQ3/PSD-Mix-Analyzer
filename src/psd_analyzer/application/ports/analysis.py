"""Small structural ports for independently testable application orchestration."""

from collections.abc import Sequence
from typing import Protocol

from ...domain.models.analysis_profile import AnalysisProfile, TailPolicy
from ...domain.models.analysis_result import EvaluatedCurve, FitResult
from ...domain.models.psd import PSD
from ...domain.protocols import LossFunction, PSDGridBuilder, PSDInterpolator, QFittableModel


class PSDMixer(Protocol):
    def mix(
        self, psds: Sequence[PSD], mass_fractions: Sequence[float], interpolator: PSDInterpolator
    ) -> PSD: ...


class MixingFactory(Protocol):
    def __call__(self, grid_builder: PSDGridBuilder, tail_policy: TailPolicy) -> PSDMixer: ...


class QFitter(Protocol):
    def __call__(
        self,
        particle_size_um: Sequence[float],
        cumulative_passing: Sequence[float | None],
        *,
        profile: AnalysisProfile,
        model: QFittableModel,
        loss: LossFunction,
    ) -> FitResult: ...


class KeySizeEvaluator(Protocol):
    def __call__(
        self,
        psd: PSD,
        sizes: Sequence[float],
        interpolator: PSDInterpolator,
        *,
        tail_policy: TailPolicy,
    ) -> EvaluatedCurve: ...
