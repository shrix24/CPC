"""
Estimator entry point: orchestrates per-PCI Kalman filters over a
measurements DataFrame and returns time-series estimates for every PCI.
"""

from collections import defaultdict

import pandas as pd

from gnb_clock_estimator.config import EstimatorConfig
from gnb_clock_estimator.kalman_filter import GnbClockKF


def run_estimator(
    meas_df: pd.DataFrame,
    config: EstimatorConfig | None = None,
) -> dict[int, list[tuple[float, float, float]]]:
    """
    Run the clock estimator on a measurements DataFrame.

    Args:
        meas_df: DataFrame with columns
                 [epoch, time_s, pci, toa_ns, carrier_phase_rad]
                 Rows must be sorted by (epoch, pci).
        config:  EstimatorConfig instance; uses defaults when None.

    Returns:
        estimates_by_pci: {pci: [(time_s, b_ns, d_ns_per_s), ...]}
            b_ns       – clock offset estimate (ns)
            d_ns_per_s – clock drift estimate (ns/s); divide by 1000 for ppm
    """
    if config is None:
        config = EstimatorConfig()

    pcis = sorted(meas_df["pci"].unique())
    kf_by_pci: dict[int, GnbClockKF] = {pci: GnbClockKF(config) for pci in pcis}
    estimates: dict[int, list] = defaultdict(list)

    for epoch, group in meas_df.groupby("epoch", sort=True):
        for _, row in group.iterrows():
            pci = int(row["pci"])
            b_ns, d_ns_per_s, _ = kf_by_pci[pci].update(
                epoch_index=int(epoch),
                measured_toa_ns=float(row["toa_ns"]),
                phi_curr=float(row["carrier_phase_rad"]),
            )
            estimates[pci].append((float(row["time_s"]), b_ns, d_ns_per_s))

    return dict(estimates)
