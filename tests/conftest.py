import pytest

from psd_analyzer.domain.models.analysis_profile import AnalysisProfile
from psd_analyzer.domain.models.material import MaterialBatch
from psd_analyzer.domain.models.psd import PSD, PSDMeasurement
from psd_analyzer.domain.models.recipe import MixtureComponent


@pytest.fixture
def profile():
    return AnalysisProfile(
        "monitor", "1", 1, 100, grid_points=41, key_sizes_um=(1, 10, 45, 100, 500), target_q=0.3
    )


@pytest.fixture
def component():
    def make(
        passing=(0.0, 0.5, 1.0),
        grid=(1.0, 10.0, 100.0),
        *,
        line="A",
        weight=1.0,
        material="m1",
        batch_id=None,
        basis=None,
        density=None,
        density_kind=None,
        uniform=False,
        tails=(False, False),
        protocol="laser-v1",
    ):
        kwargs = {} if basis is None else {"basis": basis}
        batch_id = batch_id or f"batch-{line}"
        batch = MaterialBatch(batch_id, material, "supplier", "lot-1", density, density_kind)
        psd = PSD(
            grid, passing, lower_tail_confirmed=tails[0], upper_tail_confirmed=tails[1], **kwargs
        )
        measurement = PSDMeasurement(f"psd-{batch_id}", batch_id, "1", psd, "laser", protocol)
        return MixtureComponent(line, batch, measurement, weight, uniform)

    return make
