"""Task 3 only: python examples/psd_mixing_demo.py (no q, batches, UI, or I/O)."""

from psd_analyzer.domain.models.psd import PSD
from psd_analyzer.domain.services.interpolation import LinearInterpolator, LogSizeLinearInterpolator
from psd_analyzer.domain.services.psd_mixing import PSDMixingService


def main() -> None:
    a = PSD((10.0, 100.0, 1000.0), (0.2, 0.6, 1.0))
    b = PSD((10.0, 100.0, 1000.0), (0.0, 0.4, 1.0))
    service = PSDMixingService()  # sorted source-node union; clamp boundary
    mixture = service.mix((a, b), (0.4, 0.6), LinearInterpolator())
    print(f"P(100 μm) = {mixture.cumulative_passing[1]:.2f} (expected 0.48)")

    other_grid = PSD((20.0, 200.0, 2000.0), (0.1, 0.5, 0.9))
    for strategy in (LinearInterpolator(), LogSizeLinearInterpolator()):
        result = service.mix((a, other_grid), (0.4, 0.6), strategy)
        print(f"{strategy.method_id}: grid = {result.particle_size_um}")
        print(f"  passing = {tuple(round(p, 6) for p in result.cumulative_passing)}")


if __name__ == "__main__":
    main()
