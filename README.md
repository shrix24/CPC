# CPC — GNSS Post-Processing Correction

Desktop application for post-processing GNSS data using RTKLIB.

## Features

- **RTK Post-Processing:** Convert raw `.ubx` receiver logs to RINEX, configure RTK parameters, and compute corrected positions using RTKLIB's `convbin` and `rnx2rtkp`.
- **Analysis:** Trajectory plots, position uncertainty, jitter, satellite count, fix quality — with optional ground-truth comparison (CEP50/95, CDF, error time series).
- **5G Correction:** Placeholder for future 5G gNB clock bias/drift correction module.

## Prerequisites

- Python 3.10+
- RTKLIB CLI tools (`convbin`, `rnx2rtkp`) on PATH
  - Ubuntu/Debian: `sudo apt install rtklib`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. Select vehicle and base station `.ubx` files
2. Convert to RINEX format
3. Configure RTK processing parameters (constellations, frequencies, base position, etc.)
4. Run RTK processing
5. View analysis and optionally compare against a ground truth file
