"""
Per-PCI Kalman filter for 5G gNB clock bias and drift estimation.

State vector  x = [b, d]ᵀ
  b – clock offset in nanoseconds (ns)
  d – clock drift in nanoseconds per second (ns/s)
      → output in ppm:  d_ppm = d / 1000.0

Measurement 1 (every epoch):  TOA residual  → observes b
Measurement 2 (epoch ≥ 1):    time-differenced carrier phase → observes d
"""

from math import pi

import numpy as np

from gnb_clock_estimator.config import EstimatorConfig
from gnb_clock_estimator.phase_unwrap import unwrap_phase_delta


class GnbClockKF:
    """
    Independent Kalman filter instance for one PCI.

    The bias estimate is NOT absolute – it absorbs an unknown per-PCI constant
    (geometric delay + frame-epoch ambiguity).  Downstream consumers should
    use inter-PCI differences.  The drift estimate IS absolute because the
    receiver's frequency reference pins its fractional frequency error to ~0.

    Note on capture range: prediction-aided phase unwrapping resolves integer
    cycle ambiguities by using the KF's predicted drift.  For the unwrapping to
    succeed the predicted drift must be within π/K ≈ 6.67 ns/s (≈ 0.0067 ppm)
    of the true drift.  Drifts exceeding this bound may produce cycle slips
    during the initial convergence period.
    """

    def __init__(self, config: EstimatorConfig):
        self.cfg = config
        T = config.ssb_period_s
        f_c = config.carrier_freq_hz

        # Phase-to-drift conversion factor  (rad → ns/s  when divided)
        self._K = 2.0 * pi * f_c * T * 1e-9

        # State-transition matrix
        self._F = np.array([[1.0, T],
                            [0.0, 1.0]])

        # Process noise  (Allan-variance-based, converted to [ns, ns/s])
        h0 = config.h0
        h2 = config.h_minus_2
        S_b = h0 / 2.0
        S_d = 2.0 * (pi ** 2) * h2
        Q_si = np.array([
            [S_b * T + S_d * T**3 / 3.0,  S_d * T**2 / 2.0],
            [S_d * T**2 / 2.0,             S_d * T           ],
        ])
        # Scale from SI [s, dimensionless] to [ns, ns/s]: multiply by 1e18
        self._Q = Q_si * 1e18

        # Measurement noise variances
        self._R_toa = config.toa_noise_std_ns ** 2          # (ns)²
        pn = config.phase_noise_std_rad
        self._R_drift = 2.0 * pn**2 / (self._K ** 2)        # (ns/s)²

        # Combined measurement matrices (epoch ≥ 1)
        self._H_full = np.eye(2)
        self._R_full = np.diag([self._R_toa, self._R_drift])

        # TOA-only measurement (epoch 0)
        self._H_toa = np.array([[1.0, 0.0]])
        self._R_toa_mat = np.array([[self._R_toa]])

        # Internal state
        self._x: np.ndarray | None = None
        self._P: np.ndarray | None = None
        self._phi_prev: float | None = None
        self._initialized: bool = False

    # ------------------------------------------------------------------
    def _kf_update(self, x_pred, P_pred, H, R, z):
        """Standard KF measurement update; returns (x_new, P_new)."""
        S = H @ P_pred @ H.T + R
        K_gain = P_pred @ H.T @ np.linalg.inv(S)
        x_new = x_pred + K_gain @ (z - H @ x_pred)
        P_new = (np.eye(len(x_pred)) - K_gain @ H) @ P_pred
        return x_new, P_new

    # ------------------------------------------------------------------
    def update(self, epoch_index: int, measured_toa_ns: float,
               phi_curr: float) -> tuple[float, float, np.ndarray]:
        """
        Process one SSB epoch and return updated state.

        Args:
            epoch_index:     integer epoch counter (0-based)
            measured_toa_ns: measured time-of-arrival in nanoseconds
            phi_curr:        measured carrier phase in radians, wrapped to (−π, π]

        Returns:
            b_ns       – estimated clock offset (ns)
            d_ns_per_s – estimated clock drift (ns/s)  [÷1000 → ppm]
            P          – 2×2 state covariance matrix
        """
        # TOA residual: subtract nominal arrival time to isolate bias
        z_toa = measured_toa_ns - epoch_index * self.cfg.ssb_period_s * 1e9

        # ── Epoch 0: initialise ─────────────────────────────────────
        if not self._initialized:
            self._x = np.array([z_toa, 0.0])
            self._P = np.diag([
                self._R_toa,
                self.cfg.initial_drift_uncertainty_ns_per_s ** 2,
            ])
            self._phi_prev = phi_curr
            self._initialized = True
            return self._x[0], self._x[1], self._P.copy()

        # ── Epoch ≥ 1: predict ──────────────────────────────────────
        x_pred = self._F @ self._x
        P_pred = self._F @ self._P @ self._F.T + self._Q

        # ── Phase unwrapping (prediction-aided) ────────────────────
        d_predicted = x_pred[1]
        predicted_delta_phi = self._K * d_predicted
        delta_phi = unwrap_phase_delta(self._phi_prev, phi_curr,
                                       predicted_delta_phi)
        z_drift = delta_phi / self._K

        # ── Combined measurement update ─────────────────────────────
        z = np.array([z_toa, z_drift])
        self._x, self._P = self._kf_update(
            x_pred, P_pred, self._H_full, self._R_full, z
        )

        self._phi_prev = phi_curr
        return self._x[0], self._x[1], self._P.copy()
