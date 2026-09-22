"""Loss strategies are separate from fitting and reported error metrics."""

from collections.abc import Sequence
from dataclasses import dataclass

from .metrics import calculate_metrics


@dataclass(frozen=True)
class SquaredErrorLoss:
    loss_id: str = "sse"

    def __call__(self, observed: Sequence[float], predicted: Sequence[float]) -> float:
        return calculate_metrics(observed, predicted).sse
