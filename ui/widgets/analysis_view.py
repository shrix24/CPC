import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QSplitter, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread

from processing.analysis import (
    parse_pos_file, compute_statistics, compute_jitter,
    parse_ground_truth, compare_to_ground_truth, is_rinex_observation,
)
from processing.rtk_processor import run_single_point


Q_COLORS = {1: "#2ecc71", 2: "#f39c12", 3: "#3498db", 4: "#9b59b6", 5: "#e74c3c", 6: "#1abc9c"}
Q_LABELS = {1: "Fix", 2: "Float", 3: "SBAS", 4: "DGPS", 5: "Single", 6: "PPP"}


class SPPWorker(QThread):
    """Runs single-point positioning in background."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, rover_obs, nav_files, output_path):
        super().__init__()
        self.rover_obs = rover_obs
        self.nav_files = nav_files
        self.output_path = output_path

    def run(self):
        try:
            rc, stdout, stderr = run_single_point(self.rover_obs, self.nav_files, self.output_path)
            if rc != 0:
                self.error.emit(f"SPP failed (rc={rc}): {stderr}")
            else:
                self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))


class AnalysisView(QWidget):
    """Full analysis panel: ground truth upload, metrics table, and matplotlib plots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rtk_pos_path = None
        self._spp_pos_path = None
        self._rover_obs = None
        self._nav_files = []
        self._ground_truth_path = None
        self._spp_worker = None

        layout = QVBoxLayout(self)

        # --- Ground truth upload ---
        gt_layout = QHBoxLayout()
        gt_layout.addWidget(QLabel("Ground Truth (optional):"))
        self._gt_path_label = QLabel("No file selected")
        self._gt_path_label.setStyleSheet("color: gray;")
        gt_layout.addWidget(self._gt_path_label, 1)
        self._gt_browse_btn = QPushButton("Browse…")
        self._gt_browse_btn.clicked.connect(self._browse_ground_truth)
        gt_layout.addWidget(self._gt_browse_btn)
        self._gt_clear_btn = QPushButton("Clear")
        self._gt_clear_btn.clicked.connect(self._clear_ground_truth)
        self._gt_clear_btn.setVisible(False)
        gt_layout.addWidget(self._gt_clear_btn)
        layout.addLayout(gt_layout)

        # --- Run analysis button ---
        self._run_btn = QPushButton("Run Analysis")
        self._run_btn.setStyleSheet("font-size: 14px; padding: 8px; font-weight: bold;")
        self._run_btn.clicked.connect(self._run_analysis)
        layout.addWidget(self._run_btn)

        self._status_label = QLabel()
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # --- Scrollable results area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._results_widget = QWidget()
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._results_widget)
        layout.addWidget(scroll, 1)

    def set_data(self, rtk_pos_path: str, rover_obs: str, nav_files: list[str], output_dir: str):
        """Set paths needed for analysis."""
        self._rtk_pos_path = rtk_pos_path
        self._rover_obs = rover_obs
        self._nav_files = nav_files
        self._output_dir = output_dir

    def _browse_ground_truth(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Ground Truth File", "",
            "Position files (*.pos *.csv *.txt);;All Files (*)"
        )
        if not path:
            return

        if is_rinex_observation(path):
            QMessageBox.warning(
                self, "Invalid File",
                "This appears to be a RINEX observation file, not a position solution.\n"
                "Please provide a position solution file (.pos) or CSV with lat/lon/height columns."
            )
            return

        self._ground_truth_path = path
        self._gt_path_label.setText(path)
        self._gt_path_label.setStyleSheet("")
        self._gt_clear_btn.setVisible(True)

    def _clear_ground_truth(self):
        self._ground_truth_path = None
        self._gt_path_label.setText("No file selected")
        self._gt_path_label.setStyleSheet("color: gray;")
        self._gt_clear_btn.setVisible(False)

    def _run_analysis(self):
        if not self._rtk_pos_path:
            QMessageBox.warning(self, "No Data", "No RTK solution file available. Run processing first.")
            return

        self._run_btn.setEnabled(False)
        self._status_label.setText("Computing single-point solution for comparison…")
        self._status_label.setVisible(True)

        import os
        spp_path = os.path.join(self._output_dir, "spp_solution.pos")
        self._spp_worker = SPPWorker(self._rover_obs, self._nav_files, spp_path)
        self._spp_worker.finished.connect(self._on_spp_done)
        self._spp_worker.error.connect(self._on_spp_error)
        self._spp_worker.start()

    def _on_spp_done(self, spp_path: str):
        self._spp_pos_path = spp_path
        self._status_label.setText("Generating analysis…")
        self._generate_plots()
        self._status_label.setVisible(False)
        self._run_btn.setEnabled(True)

    def _on_spp_error(self, msg: str):
        self._status_label.setText(f"SPP computation failed: {msg}\nShowing RTK analysis only.")
        self._spp_pos_path = None
        self._generate_plots()
        self._status_label.setVisible(False)
        self._run_btn.setEnabled(True)

    def _clear_results(self):
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _generate_plots(self):
        self._clear_results()

        rtk_df = parse_pos_file(self._rtk_pos_path)
        if rtk_df.empty:
            self._results_layout.addWidget(QLabel("RTK solution file is empty or could not be parsed."))
            return

        spp_df = None
        if self._spp_pos_path:
            spp_df = parse_pos_file(self._spp_pos_path)
            if spp_df.empty:
                spp_df = None

        truth_df = None
        if self._ground_truth_path:
            truth_df = parse_ground_truth(self._ground_truth_path)
            if truth_df is None:
                QMessageBox.warning(self, "Invalid File",
                    "Ground truth file appears to be a RINEX observation file.")
                truth_df = None
            elif truth_df.empty:
                QMessageBox.warning(self, "Parse Error",
                    "Could not parse ground truth file.")
                truth_df = None

        # --- Summary statistics ---
        rtk_stats = compute_statistics(rtk_df)
        self._add_stats_table("RTK Solution Statistics", rtk_stats)

        if spp_df is not None:
            spp_stats = compute_statistics(spp_df)
            self._add_stats_table("Single-Point (Raw) Solution Statistics", spp_stats)

        # --- Trajectory plot ---
        self._add_trajectory_plot(rtk_df, spp_df, truth_df)

        # --- Position time series ---
        self._add_position_timeseries(rtk_df, spp_df)

        # --- Uncertainty time series ---
        self._add_uncertainty_plot(rtk_df)

        # --- Jitter plot ---
        self._add_jitter_plot(rtk_df, spp_df)

        # --- Satellite count ---
        self._add_satellite_plot(rtk_df)

        # --- Fix quality ---
        self._add_quality_plot(rtk_df)

        # --- Ground truth comparison ---
        if truth_df is not None and not truth_df.empty:
            rtk_cmp = compare_to_ground_truth(rtk_df, truth_df)
            self._add_error_timeseries("RTK vs Ground Truth — Error", rtk_cmp)

            if spp_df is not None:
                spp_cmp = compare_to_ground_truth(spp_df, truth_df)
                self._add_error_timeseries("Raw SPP vs Ground Truth — Error", spp_cmp)
                self._add_cdf_plot(rtk_cmp, spp_cmp)
                self._add_error_comparison_table(rtk_cmp, spp_cmp)
            else:
                self._add_cdf_plot(rtk_cmp, None)

    def _make_canvas(self, fig: Figure) -> FigureCanvasQTAgg:
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumHeight(350)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return canvas

    def _add_stats_table(self, title: str, stats: dict):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        table = QTableWidget()
        rows = [
            ("Total Epochs", f"{stats.get('total_epochs', 0)}"),
            ("Fix Rate", f"{stats.get('fix_rate', 0):.1f}%"),
            ("Float Rate", f"{stats.get('float_rate', 0):.1f}%"),
            ("Single Rate", f"{stats.get('single_rate', 0):.1f}%"),
            ("SDN RMS", f"{stats.get('sdn_rms', 0):.4f} m"),
            ("SDE RMS", f"{stats.get('sde_rms', 0):.4f} m"),
            ("SDU RMS", f"{stats.get('sdu_rms', 0):.4f} m"),
            ("SDN 95th pct", f"{stats.get('sdn_95', 0):.4f} m"),
            ("SDE 95th pct", f"{stats.get('sde_95', 0):.4f} m"),
            ("SDU 95th pct", f"{stats.get('sdu_95', 0):.4f} m"),
            ("Satellites (mean)", f"{stats.get('ns_mean', 0):.1f}"),
            ("Satellites (min/max)", f"{stats.get('ns_min', 0)} / {stats.get('ns_max', 0)}"),
            ("Horiz Jitter RMS", f"{stats.get('jitter_horiz_rms', 0):.4f} m"),
            ("Vert Jitter RMS", f"{stats.get('jitter_vert_rms', 0):.4f} m"),
        ]
        table.setRowCount(len(rows))
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, (name, val) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem(val))
        table.setMaximumHeight(table.rowCount() * 30 + 30)
        layout.addWidget(table)
        self._results_layout.addWidget(group)

    def _add_trajectory_plot(self, rtk_df, spp_df, truth_df):
        fig = Figure(figsize=(10, 6))
        ax = fig.add_subplot(111)

        if spp_df is not None:
            ax.scatter(spp_df["lon"], spp_df["lat"], c="red", s=3, alpha=0.5, label="Raw SPP", zorder=1)

        for q_val in sorted(rtk_df["Q"].unique()):
            mask = rtk_df["Q"] == q_val
            color = Q_COLORS.get(q_val, "gray")
            label = Q_LABELS.get(q_val, f"Q={q_val}")
            ax.scatter(rtk_df.loc[mask, "lon"], rtk_df.loc[mask, "lat"],
                       c=color, s=4, label=f"RTK {label}", zorder=2)

        if truth_df is not None and not truth_df.empty:
            ax.plot(truth_df["lon"], truth_df["lat"], "k-", linewidth=1.5, label="Ground Truth", zorder=3)

        ax.set_xlabel("Longitude (°)")
        ax.set_ylabel("Latitude (°)")
        ax.set_title("Trajectory")
        ax.legend(fontsize=8, loc="best")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_position_timeseries(self, rtk_df, spp_df):
        fig = Figure(figsize=(10, 8))
        axes = fig.subplots(3, 1, sharex=True)

        for ax, col, label in zip(axes, ["lat", "lon", "height"],
                                  ["Latitude (°)", "Longitude (°)", "Height (m)"]):
            if spp_df is not None:
                ax.plot(spp_df["time"], spp_df[col], "r.", markersize=1, alpha=0.4, label="Raw SPP")
            ax.plot(rtk_df["time"], rtk_df[col], "b.", markersize=1, alpha=0.6, label="RTK")
            ax.set_ylabel(label)
            ax.legend(fontsize=7, loc="upper right")
            ax.grid(True, alpha=0.3)

        axes[2].set_xlabel("Time")
        axes[0].set_title("Position Time Series")
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_uncertainty_plot(self, rtk_df):
        fig = Figure(figsize=(10, 5))
        ax = fig.add_subplot(111)

        ax.plot(rtk_df["time"], rtk_df["sdn"], label="SDN (North)", linewidth=0.8)
        ax.plot(rtk_df["time"], rtk_df["sde"], label="SDE (East)", linewidth=0.8)
        ax.plot(rtk_df["time"], rtk_df["sdu"], label="SDU (Up)", linewidth=0.8)
        ax.set_xlabel("Time")
        ax.set_ylabel("Standard Deviation (m)")
        ax.set_title("Position Uncertainty")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_yscale("log")
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_jitter_plot(self, rtk_df, spp_df):
        from processing.analysis import compute_jitter

        fig = Figure(figsize=(10, 6))
        axes = fig.subplots(3, 1, sharex=True)

        rtk_jitter = compute_jitter(rtk_df)
        if not rtk_jitter.empty:
            for ax, col, label in zip(axes, ["east", "north", "up"],
                                      ["East (m)", "North (m)", "Up (m)"]):
                ax.plot(rtk_jitter["time"], rtk_jitter[col], "b-", linewidth=0.5, alpha=0.7, label="RTK")
                if spp_df is not None:
                    spp_jitter = compute_jitter(spp_df)
                    if not spp_jitter.empty:
                        ax.plot(spp_jitter["time"], spp_jitter[col], "r-", linewidth=0.5, alpha=0.4, label="Raw SPP")
                ax.set_ylabel(label)
                ax.legend(fontsize=7, loc="upper right")
                ax.grid(True, alpha=0.3)

        axes[0].set_title("Epoch-to-Epoch Position Jitter")
        axes[2].set_xlabel("Time")
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_satellite_plot(self, rtk_df):
        fig = Figure(figsize=(10, 3))
        ax = fig.add_subplot(111)
        ax.plot(rtk_df["time"], rtk_df["ns"], "g-", linewidth=0.8)
        ax.fill_between(rtk_df["time"], 0, rtk_df["ns"], alpha=0.2, color="green")
        ax.set_xlabel("Time")
        ax.set_ylabel("Number of Satellites")
        ax.set_title("Satellite Count")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(bottom=0)
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_quality_plot(self, rtk_df):
        fig = Figure(figsize=(10, 3))
        ax = fig.add_subplot(111)

        for q_val in sorted(rtk_df["Q"].unique()):
            mask = rtk_df["Q"] == q_val
            color = Q_COLORS.get(q_val, "gray")
            label = Q_LABELS.get(q_val, f"Q={q_val}")
            ax.scatter(rtk_df.loc[mask, "time"], rtk_df.loc[mask, "Q"],
                       c=color, s=8, label=label, alpha=0.7)

        ax.set_xlabel("Time")
        ax.set_ylabel("Quality Flag")
        ax.set_title("Solution Quality")
        ax.set_yticks(sorted(rtk_df["Q"].unique()))
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.3, axis="x")
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_error_timeseries(self, title: str, cmp: dict):
        if not cmp:
            return

        fig = Figure(figsize=(10, 6))
        axes = fig.subplots(3, 1, sharex=True)
        times = cmp["times"]

        for ax, key, label in zip(axes, ["east_err", "north_err", "up_err"],
                                  ["East Error (m)", "North Error (m)", "Up Error (m)"]):
            ax.plot(times, cmp[key], linewidth=0.7)
            ax.set_ylabel(label)
            ax.grid(True, alpha=0.3)
            ax.axhline(y=0, color="k", linewidth=0.5)

        axes[0].set_title(title)
        axes[2].set_xlabel("Time")
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_cdf_plot(self, rtk_cmp: dict, spp_cmp: dict | None):
        fig = Figure(figsize=(8, 5))
        ax = fig.add_subplot(111)

        rtk_sorted = np.sort(rtk_cmp["horiz_err"])
        rtk_cdf = np.arange(1, len(rtk_sorted) + 1) / len(rtk_sorted)
        ax.plot(rtk_sorted, rtk_cdf, "b-", linewidth=1.5, label="RTK")

        ax.axhline(y=0.50, color="gray", linestyle="--", linewidth=0.5)
        ax.axhline(y=0.95, color="gray", linestyle="--", linewidth=0.5)
        ax.axvline(x=rtk_cmp["horiz_cep50"], color="blue", linestyle=":", linewidth=0.8,
                   label=f"RTK CEP50={rtk_cmp['horiz_cep50']:.3f}m")
        ax.axvline(x=rtk_cmp["horiz_cep95"], color="blue", linestyle="--", linewidth=0.8,
                   label=f"RTK CEP95={rtk_cmp['horiz_cep95']:.3f}m")

        if spp_cmp:
            spp_sorted = np.sort(spp_cmp["horiz_err"])
            spp_cdf = np.arange(1, len(spp_sorted) + 1) / len(spp_sorted)
            ax.plot(spp_sorted, spp_cdf, "r-", linewidth=1.5, label="Raw SPP")
            ax.axvline(x=spp_cmp["horiz_cep50"], color="red", linestyle=":", linewidth=0.8,
                       label=f"SPP CEP50={spp_cmp['horiz_cep50']:.3f}m")
            ax.axvline(x=spp_cmp["horiz_cep95"], color="red", linestyle="--", linewidth=0.8,
                       label=f"SPP CEP95={spp_cmp['horiz_cep95']:.3f}m")

        ax.set_xlabel("Horizontal Error (m)")
        ax.set_ylabel("CDF")
        ax.set_title("Cumulative Distribution of Horizontal Error")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        self._results_layout.addWidget(self._make_canvas(fig))

    def _add_error_comparison_table(self, rtk_cmp: dict, spp_cmp: dict):
        group = QGroupBox("Error Comparison: RTK vs Raw SPP (relative to Ground Truth)")
        layout = QVBoxLayout(group)

        table = QTableWidget()
        rows = [
            ("Horiz RMS", f"{rtk_cmp['horiz_rms']:.4f} m", f"{spp_cmp['horiz_rms']:.4f} m"),
            ("Horiz Mean", f"{rtk_cmp['horiz_mean']:.4f} m", f"{spp_cmp['horiz_mean']:.4f} m"),
            ("Horiz Max", f"{rtk_cmp['horiz_max']:.4f} m", f"{spp_cmp['horiz_max']:.4f} m"),
            ("Horiz CEP50", f"{rtk_cmp['horiz_cep50']:.4f} m", f"{spp_cmp['horiz_cep50']:.4f} m"),
            ("Horiz CEP95", f"{rtk_cmp['horiz_cep95']:.4f} m", f"{spp_cmp['horiz_cep95']:.4f} m"),
            ("Vert RMS", f"{rtk_cmp['vert_rms']:.4f} m", f"{spp_cmp['vert_rms']:.4f} m"),
            ("Vert Mean", f"{rtk_cmp['vert_mean']:.4f} m", f"{spp_cmp['vert_mean']:.4f} m"),
            ("Vert Max", f"{rtk_cmp['vert_max']:.4f} m", f"{spp_cmp['vert_max']:.4f} m"),
        ]

        table.setRowCount(len(rows))
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Metric", "RTK", "Raw SPP"])
        for i in range(3):
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, (name, rtk_val, spp_val) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem(rtk_val))
            table.setItem(i, 2, QTableWidgetItem(spp_val))
        table.setMaximumHeight(table.rowCount() * 30 + 30)
        layout.addWidget(table)
        self._results_layout.addWidget(group)
