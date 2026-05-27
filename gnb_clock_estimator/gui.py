"""
PySide6 widget for the 5G gNB clock bias & drift estimator.

Integrates with the CPC desktop application as the content of the
"5G Correction" tab.  The standalone gui.py described in the spec is
implemented here as a QWidget so it can be embedded directly rather
than launching a separate Tk window.
"""

import os
import tempfile

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from gnb_clock_estimator.config import EstimatorConfig
from gnb_clock_estimator.module_main import run_estimator
from gnb_clock_estimator.output_writer import write_correction_csvs
from gnb_clock_estimator.synth_generator import generate as synth_generate

# ---------------------------------------------------------------------------
# Default synthetic-data configuration
#
# Drift magnitudes are kept within the unwrapper capture range
# (π / K ≈ 6.67 ns/s ≈ 0.0067 ppm at 3.75 GHz / 20 ms).
# Larger drifts are supported by the filter but may exhibit a cycle-slip
# transient until the bias-driven estimate enters the capture window.
# ---------------------------------------------------------------------------
_DEFAULT_PCI_CONFIGS = [
    {
        "pci": 4,
        "initial_offset_ns": 500.0,
        "drift_ppm": 0.004,
        "toa_noise_std_ns": 4.0,
        "phase_noise_std_rad": 0.05,
    },
    {
        "pci": 7,
        "initial_offset_ns": 1200.0,
        "drift_ppm": -0.003,
        "toa_noise_std_ns": 4.0,
        "phase_noise_std_rad": 0.05,
    },
    {
        "pci": 12,
        "initial_offset_ns": 750.0,
        "drift_ppm": 0.005,
        "toa_noise_std_ns": 4.0,
        "phase_noise_std_rad": 0.05,
    },
]

_DEFAULT_GLOBAL_CONFIG = {
    "ssb_period_s": 0.02,
    "carrier_freq_hz": 3.75e9,
    "duration_s": 10.0,
}

_PCI_COLORS = ["#2ecc71", "#3498db", "#e74c3c", "#f39c12", "#9b59b6", "#1abc9c"]


# ---------------------------------------------------------------------------
class _EstimatorWorker(QThread):
    """Runs run_estimator() off the GUI thread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, meas_df: pd.DataFrame, config: EstimatorConfig):
        super().__init__()
        self._meas_df = meas_df
        self._config = config

    def run(self):
        try:
            self.finished.emit(run_estimator(self._meas_df, self._config))
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
class FiveGEstimatorWidget(QWidget):
    """
    Self-contained widget providing the full 5G estimator workflow:

      Generate Synthetic Data → Run Estimator → view plots → Export CSVs

    or

      Load Measurements CSV  → Run Estimator → view plots → Export CSVs
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._meas_df: pd.DataFrame | None = None
        self._estimates: dict | None = None
        self._truth: dict | None = None
        self._config = EstimatorConfig()
        self._worker: _EstimatorWorker | None = None
        self._temp_dir: str | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Button bar ──────────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._btn_synth = QPushButton("Generate Synthetic Data")
        self._btn_load = QPushButton("Load Measurements CSV")
        self._btn_run = QPushButton("Run Estimator")
        self._btn_export = QPushButton("Export CSVs")

        self._btn_run.setEnabled(False)
        self._btn_export.setEnabled(False)

        for btn in (self._btn_synth, self._btn_load, self._btn_run,
                    self._btn_export):
            bar.addWidget(btn)

        bar.addStretch()

        self._status_lbl = QLabel("Ready.")
        self._status_lbl.setStyleSheet("color: #666; font-style: italic;")
        bar.addWidget(self._status_lbl)

        root.addLayout(bar)

        # ── Matplotlib canvas ────────────────────────────────────────────────
        self._fig = Figure(figsize=(10, 6))
        self._ax_offset = self._fig.add_subplot(2, 1, 1)
        self._ax_drift = self._fig.add_subplot(2, 1, 2)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._canvas)

        self._draw_empty_axes()

        # ── Signals ──────────────────────────────────────────────────────────
        self._btn_synth.clicked.connect(self._on_generate_synth)
        self._btn_load.clicked.connect(self._on_load_measurements)
        self._btn_run.clicked.connect(self._on_run_estimator)
        self._btn_export.clicked.connect(self._on_export)

    def _draw_empty_axes(self):
        for ax, title, ylabel in (
            (self._ax_offset, "Clock Offset Estimate", "Offset (ns)"),
            (self._ax_drift,  "Clock Drift Estimate",  "Drift (ppm)"),
        ):
            ax.set_title(title)
            ax.set_xlabel("Time (ms)")
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
        self._fig.tight_layout()
        self._canvas.draw()

    # --------------------------------------------------------- Button slots --
    def _on_generate_synth(self):
        self._temp_dir = tempfile.mkdtemp(prefix="cpc_5g_")
        try:
            meas_df, truth_by_pci = synth_generate(
                _DEFAULT_PCI_CONFIGS, _DEFAULT_GLOBAL_CONFIG
            )
        except Exception as exc:
            QMessageBox.critical(self, "Generation Error", str(exc))
            return

        meas_df.to_csv(os.path.join(self._temp_dir, "measurements.csv"),
                       index=False)
        for pci, df in truth_by_pci.items():
            df.to_csv(os.path.join(self._temp_dir, f"truth_pci{pci}.csv"),
                      index=False)

        self._meas_df = meas_df
        self._truth = truth_by_pci
        self._estimates = None
        self._btn_run.setEnabled(True)
        self._btn_export.setEnabled(False)
        n_pci = meas_df["pci"].nunique()
        self._set_status(
            f"Synthetic data generated — {len(meas_df)} measurements, "
            f"{n_pci} PCIs."
        )
        self._clear_plots()

    def _on_load_measurements(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Measurements CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            df = pd.read_csv(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        required = {"epoch", "time_s", "pci", "toa_ns", "carrier_phase_rad"}
        missing = required - set(df.columns)
        if missing:
            QMessageBox.critical(
                self, "Invalid File",
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )
            return

        self._meas_df = df
        self._truth = None
        self._estimates = None
        self._btn_run.setEnabled(True)
        self._btn_export.setEnabled(False)
        self._set_status(
            f"Loaded {len(df)} measurements from '{os.path.basename(path)}'."
        )
        self._clear_plots()

    def _on_run_estimator(self):
        if self._meas_df is None:
            return
        self._set_buttons_enabled(False)
        self._set_status("Running estimator…")

        self._worker = _EstimatorWorker(self._meas_df, self._config)
        self._worker.finished.connect(self._on_estimator_done)
        self._worker.error.connect(self._on_estimator_error)
        self._worker.start()

    def _on_estimator_done(self, estimates: dict):
        self._estimates = estimates
        self._set_buttons_enabled(True)
        self._btn_export.setEnabled(True)
        self._set_status("Estimation complete.")
        self._update_plots()

    def _on_estimator_error(self, msg: str):
        self._set_buttons_enabled(True)
        self._set_status("Estimator error — see dialog.")
        QMessageBox.critical(self, "Estimator Error", msg)

    def _on_export(self):
        if not self._estimates:
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory"
        )
        if not out_dir:
            return
        try:
            paths = write_correction_csvs(self._estimates, out_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return
        self._set_status(f"Exported {len(paths)} CSV(s) to {out_dir}.")
        QMessageBox.information(
            self, "Export Complete",
            f"Written {len(paths)} correction CSV(s) to:\n{out_dir}"
        )

    # ------------------------------------------------------------ Plotting --
    def _clear_plots(self):
        self._ax_offset.cla()
        self._ax_drift.cla()
        self._draw_empty_axes()

    def _update_plots(self):
        self._ax_offset.cla()
        self._ax_drift.cla()

        sorted_pcis = sorted(self._estimates.keys())

        for i, pci in enumerate(sorted_pcis):
            color = _PCI_COLORS[i % len(_PCI_COLORS)]
            records = self._estimates[pci]
            times_ms = [r[0] * 1000.0 for r in records]
            offsets_ns = [r[1] for r in records]
            drifts_ppm = [r[2] / 1000.0 for r in records]

            self._ax_offset.plot(
                times_ms, offsets_ns, color=color, label=f"PCI {pci}"
            )
            self._ax_drift.plot(
                times_ms, drifts_ppm, color=color, label=f"PCI {pci}"
            )

            # Truth overlay (dashed) when synthetic data is loaded
            if self._truth and pci in self._truth:
                t_df = self._truth[pci]
                self._ax_offset.plot(
                    t_df["time_ms"], t_df["true_clock_offset_ns"],
                    color=color, linestyle="--", alpha=0.55,
                    label=f"PCI {pci} truth",
                )
                self._ax_drift.plot(
                    t_df["time_ms"], t_df["true_clock_drift_ppm"],
                    color=color, linestyle="--", alpha=0.55,
                    label=f"PCI {pci} truth",
                )

        for ax, title, ylabel in (
            (self._ax_offset, "Clock Offset Estimate", "Offset (ns)"),
            (self._ax_drift,  "Clock Drift Estimate",  "Drift (ppm)"),
        ):
            ax.set_title(title)
            ax.set_xlabel("Time (ms)")
            ax.set_ylabel(ylabel)
            ax.legend(fontsize=8, loc="best")
            ax.grid(True, alpha=0.3)

        self._fig.tight_layout()
        self._canvas.draw()

    # ---------------------------------------------------------------- Util --
    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self._btn_synth, self._btn_load, self._btn_run):
            btn.setEnabled(enabled)
