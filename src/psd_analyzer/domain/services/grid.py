"""Fixed evaluation grids; plotting nodes never change fitting weights."""

import numpy as np

from ..models.analysis_profile import AnalysisProfile


def build_grid(profile: AnalysisProfile) -> tuple[float, ...]:
    values = np.geomspace(profile.d_min_um, profile.d_max_um, profile.grid_points)
    values[0], values[-1] = profile.d_min_um, profile.d_max_um
    return tuple(float(v) for v in values)
