from math import pi


def wrap_to_minus_pi_plus_pi(x: float) -> float:
    """Wrap angle x (radians) into the interval (-π, π]."""
    return ((x + pi) % (2.0 * pi)) - pi


def unwrap_phase_delta(phi_prev: float, phi_curr: float,
                       predicted_delta_phi: float) -> float:
    """
    Prediction-aided phase unwrapping.

    At GHz carrier frequencies a 20 ms epoch produces hundreds of radians of
    phase change, so naive (±π) unwrapping fails.  This function uses the KF's
    current drift prediction to disambiguate the integer-cycle count.

    Args:
        phi_prev:            wrapped carrier phase at previous epoch (rad)
        phi_curr:            wrapped carrier phase at current epoch (rad)
        predicted_delta_phi: expected phase change from KF drift prediction (rad)

    Returns:
        unwrapped phase difference (rad) suitable for converting to drift.
    """
    raw_delta = phi_curr - phi_prev
    residual = raw_delta - predicted_delta_phi
    residual_wrapped = wrap_to_minus_pi_plus_pi(residual)
    return predicted_delta_phi + residual_wrapped
