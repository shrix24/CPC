# gnb\_clock\_estimator — 5G gNB Clock Bias & Drift Estimator

Estimates per-PCI clock bias and clock drift for 5G gNBs using passive SSB
(Synchronization Signal Block) measurements from an SDR receiver that is
disciplined to a stable frequency reference.

## Quick start (GUI)

Run the CPC application (`python main.py` from the repository root) and select
the **5G Correction** tab.

1. **Generate Synthetic Data** — creates measurements for three PCIs using a
   built-in configuration and saves them to a temporary directory.
2. **Run Estimator** — executes the Kalman filter on every PCI in a background
   thread and populates the two plots.
3. **Export CSVs** — writes one `correction_pciN.csv` per PCI to a directory
   of your choice.

Alternatively, use **Load Measurements CSV** to supply a real-measurement file
(same column format as the synthetic generator output).

---

## Architecture

```
gnb_clock_estimator/
├── config.py           EstimatorConfig dataclass (all tunable parameters)
├── synth_generator.py  Closed-loop synthetic data generator
├── phase_unwrap.py     Prediction-aided carrier-phase unwrapper
├── kalman_filter.py    Per-PCI two-state Kalman filter [bias, drift]
├── output_writer.py    Correction CSV writer
├── module_main.py      Estimator orchestrator (run_estimator function)
└── gui.py              PySide6 widget embedded in the CPC 5G tab
```

---

## File formats

### Measurements CSV (input)

| column             | type  | units |
|--------------------|-------|-------|
| epoch              | int   | —     |
| time\_s            | float | s     |
| pci                | int   | —     |
| toa\_ns            | float | ns    |
| carrier\_phase\_rad | float | rad, wrapped to (−π, π] |

### Correction CSV (output, one file per PCI)

| column                      | type  | units |
|-----------------------------|-------|-------|
| time\_ms                    | float | ms    |
| PCI                         | int   | —     |
| estimated\_clock\_offset\_ns | float | ns    |
| estimated\_clock\_drift\_ppm | float | ppm   |

---

## State model

```
x = [b, d]ᵀ
```

- **b** — clock offset (ns): the measured arrival-time residual after removing
  the nominal epoch time.  This is **not** absolute; it includes a per-PCI
  constant absorbing geometric delay and frame-epoch ambiguity.  Downstream
  consumers should use **inter-PCI differences**.
- **d** — clock drift (ns/s = ppm × 10³): the fractional frequency offset of
  the gNB clock relative to the receiver's frequency reference.  Because the
  receiver is disciplined to a stable oscillator, the drift estimate **is**
  absolute.

Process model:

```
F = [[1, T],   Q derived from Allan variance (h0, h_minus_2)
     [0, 1]]
```

---

## Measurement model

| Measurement | Sensor | Observable | Noise |
|-------------|--------|------------|-------|
| TOA residual | Time-of-arrival | b | R_toa = σ²_toa |
| Time-differenced phase | Carrier phase | d | R_drift = 2σ²_phase / K² |

Phase conversion factor: `K = 2π · f_c · T · 10⁻⁹` (rad per ns/s).

---

## Prediction-aided phase unwrapping

At 3.75 GHz with a 20 ms SSB period, even 1 ppm of clock drift produces
≈ 471 rad (75 full cycles) of carrier-phase change per epoch.  Naive ±π
unwrapping fails entirely.

The phase unwrapper uses the KF's predicted drift to compute the expected
phase change, then wraps only the small residual:

```
unwrapped_Δφ = predicted_Δφ + wrap(Δφ_raw − predicted_Δφ)
```

**Capture range**: for unwrapping to succeed, the KF's predicted drift must
be within `π/K ≈ 6.67 ns/s (≈ 0.0067 ppm)` of the true drift.  Larger
initial drift errors (e.g. at start-up when d is initialised to 0) may cause
a single cycle slip, biasing the drift estimate by `2π/K ≈ 13.3 ns/s`.  The
filter self-corrects as the bias-driven TOA innovations progressively reduce
the drift error.

To guarantee correct unwrapping from epoch 1, keep the gNB drift within
≈ 0.006 ppm of the receiver reference, or supply an external rough drift
estimate as the seed for `initial_drift_uncertainty_ns_per_s`.

---

## Configuration

All parameters live in `EstimatorConfig` (`config.py`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| ssb\_period\_s | 0.02 | SSB burst periodicity (s) |
| carrier\_freq\_hz | 3.75e9 | Carrier frequency (Hz) |
| h0 | 8e-20 | Allan white FM noise coeff |
| h\_minus\_2 | 4e-23 | Allan random-walk FM coeff |
| toa\_noise\_std\_ns | 4.0 | TOA noise σ (ns) |
| phase\_noise\_std\_rad | 0.05 | Phase noise σ (rad) |
| initial\_drift\_uncertainty\_ns\_per\_s | 1e6 | Initial drift state σ |
