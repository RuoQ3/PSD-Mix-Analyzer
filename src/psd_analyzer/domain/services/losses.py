"""Loss strategies are separate from fitting and reported error metrics."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum

from .metrics import residuals


@dataclass(frozen=True)
class SquaredErrorLoss:
    loss_id: str = "sse"

    def __call__(self, observed: Sequence[float], predicted: Sequence[float]) -> float:
        return fsum(e * e for e in residuals(observed, predicted))
