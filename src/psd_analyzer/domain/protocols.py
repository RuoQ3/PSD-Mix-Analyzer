"""Replaceable numerical capabilities, independent of GUI and persistence."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .models.analysis_profile import TailPolicy
from .models.analysis_result import EvaluatedCurve
from .models.psd import PSD


class PSDInterpolator(Protocol):
    @property
    def method_id(self) -> str: ...

    def interpolate(
        self, psd: PSD, particle_size_um: Sequence[float], tail_policy: TailPolicy
    ) -> EvaluatedCurve: ...


class PackingModel(Protocol):
    @property
    def model_id(self) -> str: ...

    def cumulative_passing(
        self,
        particle_size_um: Sequence[float],
        *,
        q: float | None,
        d_min_um: float,
        d_max_um: float,
    ) -> tuple[float, ...]: ...


@runtime_checkable
class QFittableModel(PackingModel, Protocol):
    def evaluate_q(
        self, particle_size_um: Sequence[float], *, q: float, d_min_um: float, d_max_um: float
    ) -> tuple[float, ...]: ...


class LossFunction(Protocol):
    @property
    def loss_id(self) -> str: ...

    def __call__(self, observed: Sequence[float], predicted: Sequence[float]) -> float: ...
