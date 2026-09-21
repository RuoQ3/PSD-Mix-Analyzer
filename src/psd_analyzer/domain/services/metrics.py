"""Residual metrics stored in fraction units (SSE in squared fractions)."""

from collections.abc import Sequence
from math import fsum, sqrt

from ..exceptions import DomainValidationError
from ..models.analysis_result import ErrorMetrics
from ..validation import vector


def residuals(observed: Sequence[float], predicted: Sequence[float]) -> tuple[float, ...]:
    obs, pred = vector(observed, "observed"), vector(predicted, "predicted")
    if not obs or len(obs) != len(pred):
        raise DomainValidationError("Metric vectors must be nonempty and have equal lengths")
    if any(v < 0 or v > 1 for v in (*obs, *pred)):
        raise DomainValidationError("Metrics require cumulative fractions in [0, 1]")
    return tuple(a - b for a, b in zip(obs, pred, strict=True))


def calculate_metrics(observed: Sequence[float], predicted: Sequence[float]) -> ErrorMetrics:
    errors = residuals(observed, predicted)
    sse = fsum(e * e for e in errors)
    n = len(errors)
    return ErrorMetrics(
        sqrt(sse / n), fsum(abs(e) for e in errors) / n, sse, max(abs(e) for e in errors), n
    )
