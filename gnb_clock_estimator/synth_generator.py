"""
Synthetic measurement generator for closed-loop estimator testing.

Produces:
  - A single measurements CSV (all PCIs interleaved, sorted by epoch then PCI)
    columns: epoch, time_s, pci, toa_ns, carrier_phase_rad

  - One truth CSV per PCI (same column format as the correction-message output)
    columns: time_ms, PCI, true_clock_offset_ns, true_clock_drift_ppm
"""

from math import pi

import numpy as np
import pandas as pd


def _wrap(x: float) -> float:
    """Wrap a scalar angle to (-π, π]."""
    return ((x + pi) % (2.0 * pi)) - pi


def _wrap_array(x):
    """Wrap a numpy array of angles to (-π, π]."""
    return ((x + pi) % (2.0 * pi)) - pi


def generate(pci_configs: list[dict], global_config: dict,
             rng=None) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """
    Generate synthetic SSB measurements and per-PCI truth data.

    Args:
        pci_configs: list of per-PCI parameter dicts, each containing:
            pci                 – Physical Cell ID (int)
            initial_offset_ns   – constant unknown bias absorbed into geometry (ns)
            drift_ppm           – true constant clock drift (ppm)
            toa_noise_std_ns    – TOA measurement noise σ (ns)
            phase_noise_std_rad – carrier phase measurement noise σ (rad)

        global_config: dict with keys:
            ssb_period_s    – SSB burst period (s), default 0.02
            carrier_freq_hz – carrier frequency (Hz), default 3.75e9
            duration_s      – total simulation duration (s), default 10.0

        rng: optional numpy Generator (for reproducibility).

    Returns:
        meas_df      – DataFrame[epoch, time_s, pci, toa_ns, carrier_phase_rad]
        truth_by_pci – {pci: DataFrame[time_ms, PCI, true_clock_offset_ns,
                                       true_clock_drift_ppm]}
    """
    if rng is None:
        rng = np.random.default_rng()

    ssb_period_s = float(global_config.get("ssb_period_s", 0.02))
    carrier_freq_hz = float(global_config.get("carrier_freq_hz", 3.75e9))
    duration_s = float(global_config.get("duration_s", 10.0))

    n_epochs = int(duration_s / ssb_period_s)
    t_epochs = np.arange(n_epochs, dtype=float) * ssb_period_s  # shape (N,)

    meas_rows: list[dict] = []
    truth_by_pci: dict[int, pd.DataFrame] = {}

    for cfg in pci_configs:
        pci = int(cfg["pci"])
        initial_offset_ns = float(cfg["initial_offset_ns"])
        drift_ppm = float(cfg["drift_ppm"])
        toa_noise_std_ns = float(cfg.get("toa_noise_std_ns", 4.0))
        phase_noise_std_rad = float(cfg.get("phase_noise_std_rad", 0.05))

        # --- True clock bias (ns) at each epoch ---
        # bias = constant_offset + drift_ppm * 1e-6 * t_k * 1e9
        #      = constant_offset + drift_ns_per_s * t_k
        drift_ns_per_s = drift_ppm * 1e-6 * 1e9          # ns/s
        true_bias_ns = initial_offset_ns + drift_ns_per_s * t_epochs  # (N,)

        # --- Measured TOA (ns) ---
        nominal_toa_ns = t_epochs * 1e9                   # (N,) – nominal arrivals
        true_toa_ns = nominal_toa_ns + true_bias_ns
        toa_noise = rng.normal(0.0, toa_noise_std_ns, size=n_epochs)
        measured_toa_ns = true_toa_ns + toa_noise

        # --- Measured carrier phase (rad, wrapped to (-π, π]) ---
        true_phase_rad = 2.0 * pi * carrier_freq_hz * true_bias_ns * 1e-9
        true_phase_wrapped = _wrap_array(true_phase_rad)
        phase_noise = rng.normal(0.0, phase_noise_std_rad, size=n_epochs)
        measured_phase_rad = _wrap_array(true_phase_wrapped + phase_noise)

        # --- Accumulate measurement rows ---
        for k in range(n_epochs):
            meas_rows.append({
                "epoch": k,
                "time_s": t_epochs[k],
                "pci": pci,
                "toa_ns": measured_toa_ns[k],
                "carrier_phase_rad": measured_phase_rad[k],
            })

        # --- Truth CSV (same format as correction-message output) ---
        truth_by_pci[pci] = pd.DataFrame({
            "time_ms": t_epochs * 1000.0,
            "PCI": pci,
            "true_clock_offset_ns": true_bias_ns,
            "true_clock_drift_ppm": drift_ppm,   # constant model → flat line
        })

    meas_df = (
        pd.DataFrame(meas_rows)
        .sort_values(["epoch", "pci"])
        .reset_index(drop=True)
    )

    return meas_df, truth_by_pci
