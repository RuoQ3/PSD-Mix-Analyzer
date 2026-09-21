"""Single implementation of the Modified Andreasen / Funk-Dinger curve."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, log

import numpy as np

from ..exceptions import DomainValidationError
from ..validation import finite, positive, sizes


@dataclass(frozen=True)
class ModifiedAndreasen:
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
        grid = sizes(particle_size_um)
        lo, hi = positive(d_min_um, "Dmin"), positive(d_max_um, "Dmax")
        exponent = finite(q, "q")
        if lo >= hi:
            raise DomainValidationError("Dmin must be smaller than Dmax")
        width = log(hi) - log(lo)
        z = exponent * width
        if not isfinite(z):
            raise DomainValidationError("q and particle range exceed numerical limits")
        # All exponentials below have nonpositive arguments; no power overflow.
        a = np.log(np.clip(grid, lo, hi)) - log(lo)
        if abs(z) < 1e-8:
            values = a / width
        elif exponent > 0:
            values = np.exp(exponent * (a - width)) * (-np.expm1(-exponent * a))
            values /= -np.expm1(-z)
        else:
            values = np.expm1(exponent * a) / np.expm1(z)
        values = np.clip(values, 0.0, 1.0)
        return tuple(
            0.0 if d <= lo else 1.0 if d >= hi else float(v)
            for d, v in zip(grid, values, strict=True)
        )
