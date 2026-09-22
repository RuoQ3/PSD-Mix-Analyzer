"""Single implementation of the Modified Andreasen / Funk-Dinger curve."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, log, log1p

import numpy as np

from ..exceptions import DomainValidationError
from ..validation import CUMULATIVE_ROUNDOFF_TOLERANCE, positive, sizes

_LOG_LIMIT_THRESHOLD = 1e-8


@dataclass(frozen=True)
class ModifiedAndreasen:
    """Positive-q target curve, with exact 0/1 extension at its configured bounds.

    Natural logarithms and nonpositive exponentials avoid overflowing D**q.
    Very small positive q uses its continuous logarithmic limit.
    """

    model_id: str = "modified-andreasen"

    def cumulative_passing(
        self,
        particle_size_um: Sequence[float],
        *,
        q: float | None,
        d_min_um: float,
        d_max_um: float,
    ) -> tuple[float, ...]:
        if q is None:
            raise DomainValidationError("Modified Andreasen requires q")
        return self.evaluate_q(particle_size_um, q=q, d_min_um=d_min_um, d_max_um=d_max_um)

    def evaluate_q(
        self, particle_size_um: Sequence[float], *, q: float, d_min_um: float, d_max_um: float
    ) -> tuple[float, ...]:
        """Evaluate strictly increasing positive sizes in μm; return cumulative fractions."""
        grid = sizes(particle_size_um)
        lo, hi = positive(d_min_um, "Dmin"), positive(d_max_um, "Dmax")
        exponent = positive(q, "q")
        if lo >= hi:
            raise DomainValidationError("Dmin must be smaller than Dmax")
        relative_span = (hi - lo) / lo
        width = log1p(relative_span) if isfinite(relative_span) else log(hi) - log(lo)
        z = exponent * width
        if not isfinite(z):
            raise DomainValidationError("q and particle range exceed numerical limits")
        bounded_grid = np.clip(grid, lo, hi)  # Model's declared support boundary, not data repair.
        try:
            with np.errstate(divide="raise", invalid="raise", over="raise"):
                a = (
                    np.log1p((bounded_grid - lo) / lo)
                    if isfinite(relative_span)
                    else np.log(bounded_grid) - log(lo)
                )
                if z < _LOG_LIMIT_THRESHOLD:
                    values = a / width
                else:
                    values = np.exp(exponent * (a - width)) * (-np.expm1(-exponent * a))
                    values /= -np.expm1(-z)
        except (ValueError, FloatingPointError) as exc:
            raise DomainValidationError("Modified Andreasen numerical evaluation failed") from exc
        if not np.all(np.isfinite(values)) or np.any(
            (values < -CUMULATIVE_ROUNDOFF_TOLERANCE) | (values > 1 + CUMULATIVE_ROUNDOFF_TOLERANCE)
        ):
            raise DomainValidationError("Modified Andreasen produced invalid cumulative values")
        # Only already-validated sub-tolerance floating errors can be corrected.
        values = np.clip(values, 0.0, 1.0)
        result = tuple(
            0.0 if d <= lo else 1.0 if d >= hi else float(v)
            for d, v in zip(grid, values, strict=True)
        )
        if any(a > b for a, b in zip(result, result[1:], strict=False)):
            raise DomainValidationError("Modified Andreasen produced a nonmonotonic curve")
        return result
