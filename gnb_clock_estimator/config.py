from dataclasses import dataclass


@dataclass
class EstimatorConfig:
    """All tunable parameters for the gNB clock estimator."""

    # Signal parameters
    ssb_period_s: float = 0.02          # SSB periodicity (20 ms)
    carrier_freq_hz: float = 3.75e9     # carrier frequency

    # Clock noise model (Allan variance coefficients, OCXO grade)
    h0: float = 8e-20                   # white FM noise coefficient
    h_minus_2: float = 4e-23            # random-walk FM noise coefficient

    # Measurement noise standard deviations
    toa_noise_std_ns: float = 4.0       # TOA noise σ (nanoseconds)
    phase_noise_std_rad: float = 0.05   # carrier phase noise σ (radians)

    # Initialisation
    initial_drift_uncertainty_ns_per_s: float = 1e6  # initial drift state σ
