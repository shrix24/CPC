"""
Writes per-PCI correction CSVs consumed by the downstream positioning engine.

Output format per file:
    time_ms,PCI,estimated_clock_offset_ns,estimated_clock_drift_ppm
    0.0,4,502.14,0.00412
    ...
"""

import os

import pandas as pd


def write_correction_csvs(
    estimates_by_pci: dict[int, list[tuple[float, float, float]]],
    output_dir: str,
) -> list[str]:
    """
    Write one correction CSV per PCI.

    Args:
        estimates_by_pci: {pci: [(time_s, b_ns, d_ns_per_s), ...]}
        output_dir:       directory to write files into (created if absent)

    Returns:
        List of written file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths: list[str] = []

    for pci, records in sorted(estimates_by_pci.items()):
        rows = [
            {
                "time_ms": time_s * 1000.0,
                "PCI": pci,
                "estimated_clock_offset_ns": b_ns,
                "estimated_clock_drift_ppm": d_ns_per_s / 1000.0,
            }
            for time_s, b_ns, d_ns_per_s in records
        ]
        df = pd.DataFrame(rows)
        path = os.path.join(output_dir, f"correction_pci{pci}.csv")
        df.to_csv(path, index=False)
        paths.append(path)

    return paths
