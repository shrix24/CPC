import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QListWidget, QListWidgetItem, QPlainTextEdit, QMessageBox, QApplication,
    QSplitter, QGroupBox, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal

from ui.widgets.file_selector import FileSelector, DirectorySelector
from ui.widgets.rtk_config_panel import RTKConfigPanel
from ui.widgets.conversion_status import ConversionStatus
from ui.widgets.analysis_view import AnalysisView
from processing.converter import convert_ubx, parse_rinex_header_position, ecef_to_lla
from processing.rtk_processor import run_rtk, build_rtk_command


def _show_msg(parent, icon, title, text):
    msg = QMessageBox(icon, title, text, parent=parent)
    msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    msg.exec()


STEPS = [
    "1. File Selection",
    "2. RINEX Conversion",
    "3. RTK Configuration",
    "4. Processing",
    "5. Analysis",
]


class ConvertWorker(QThread):
    """Runs convbin in a background thread."""

    progress = Signal(str)
    finished = Signal(dict, dict)
    error = Signal(str)

    def __init__(self, vehicle_path, base_path, output_dir):
        super().__init__()
        self.vehicle_path = vehicle_path
        self.base_path = base_path
        self.output_dir = output_dir

    def run(self):
        try:
            self.progress.emit("Converting vehicle .ubx file…")
            vehicle_result = convert_ubx(self.vehicle_path, self.output_dir)

            self.progress.emit("Converting base station .ubx file…")
            base_result = convert_ubx(self.base_path, self.output_dir)

            self.finished.emit(vehicle_result, base_result)
        except Exception as e:
            self.error.emit(str(e))


class RTKWorker(QThread):
    """Runs rnx2rtkp in a background thread."""

    log = Signal(str)
    finished = Signal(int, str, str)

    def __init__(self, rover_obs, base_obs, nav_files, output_path, config):
        super().__init__()
        self.rover_obs = rover_obs
        self.base_obs = base_obs
        self.nav_files = nav_files
        self.output_path = output_path
        self.config = config

    def run(self):
        try:
            cmd = build_rtk_command(
                self.rover_obs, self.base_obs, self.nav_files,
                self.output_path, self.config,
            )
            self.log.emit(f"Command: {' '.join(cmd)}\n")

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            stdout, stderr = proc.communicate(timeout=600)

            if stdout:
                self.log.emit(stdout)
            if stderr:
                self.log.emit(stderr)

            self.finished.emit(proc.returncode, stdout, stderr)
        except Exception as e:
            self.log.emit(f"Error: {e}")
            self.finished.emit(-1, "", str(e))


class RTKTab(QWidget):
    """RTK post-processing workflow tab with step-by-step wizard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vehicle_result = None
        self._base_result = None
        self._rtk_output_path = None
        self._convert_worker = None
        self._rtk_worker = None

        main_layout = QHBoxLayout(self)

        # --- Step sidebar ---
        self._step_list = QListWidget()
        self._step_list.setFixedWidth(180)
        self._step_list.setStyleSheet("""
            QListWidget { font-size: 13px; }
            QListWidget::item { padding: 8px; }
            QListWidget::item:selected { background: #3498db; color: white; }
        """)
        for step_name in STEPS:
            item = QListWidgetItem(step_name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._step_list.addItem(item)

        self._step_list.item(0).setFlags(self._step_list.item(0).flags() | Qt.ItemFlag.ItemIsEnabled)
        self._step_list.setCurrentRow(0)
        self._step_list.currentRowChanged.connect(self._on_step_clicked)
        main_layout.addWidget(self._step_list)

        # --- Stacked pages ---
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack, 1)

        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()
        self._build_step5()

    def _enable_step(self, index: int):
        item = self._step_list.item(index)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)

    def _go_to_step(self, index: int):
        self._enable_step(index)
        self._step_list.setCurrentRow(index)
        self._stack.setCurrentIndex(index)

    def _on_step_clicked(self, row: int):
        self._stack.setCurrentIndex(row)

    # ─── Step 1: File Selection ───

    def _build_step1(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        header = QLabel("Step 1: Select Input Files")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        desc = QLabel("Select the vehicle and base station .ubx files, and an output directory.")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(10)

        self._vehicle_selector = FileSelector("Vehicle .ubx file:", "UBX files (*.ubx);;All Files (*)")
        layout.addWidget(self._vehicle_selector)

        self._base_selector = FileSelector("Base station .ubx file:", "UBX files (*.ubx);;All Files (*)")
        layout.addWidget(self._base_selector)

        self._output_dir_selector = DirectorySelector("Output directory:")
        layout.addWidget(self._output_dir_selector)

        self._vehicle_selector.file_selected.connect(self._on_vehicle_selected)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._step1_next = QPushButton("Next: Convert to RINEX →")
        self._step1_next.setStyleSheet("font-size: 14px; padding: 8px 20px;")
        self._step1_next.clicked.connect(self._start_conversion)
        btn_layout.addWidget(self._step1_next)
        layout.addLayout(btn_layout)

        self._stack.addWidget(page)

    def _on_vehicle_selected(self, path: str):
        if not self._output_dir_selector.path():
            self._output_dir_selector.set_path(str(Path(path).parent / "rtk_output"))

    # ─── Step 2: RINEX Conversion ───

    def _build_step2(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        header = QLabel("Step 2: RINEX Conversion")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        self._conv_progress_label = QLabel("Converting…")
        layout.addWidget(self._conv_progress_label)

        self._conv_progress_bar = QProgressBar()
        self._conv_progress_bar.setRange(0, 0)
        layout.addWidget(self._conv_progress_bar)

        self._vehicle_status = ConversionStatus()
        layout.addWidget(self._vehicle_status)

        self._base_status = ConversionStatus()
        layout.addWidget(self._base_status)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        self._step2_back = QPushButton("← Back")
        self._step2_back.clicked.connect(lambda: self._go_to_step(0))
        btn_layout.addWidget(self._step2_back)
        btn_layout.addStretch()
        self._step2_next = QPushButton("Next: Configure Processing →")
        self._step2_next.setStyleSheet("font-size: 14px; padding: 8px 20px;")
        self._step2_next.setEnabled(False)
        self._step2_next.clicked.connect(self._prepare_config_step)
        btn_layout.addWidget(self._step2_next)
        layout.addLayout(btn_layout)

        self._stack.addWidget(page)

    def _start_conversion(self):
        vehicle_path = self._vehicle_selector.path()
        base_path = self._base_selector.path()

        if not vehicle_path or not base_path:
            _show_msg(self, QMessageBox.Icon.Warning, "Missing Files", "Please select both vehicle and base station .ubx files.")
            return

        if not os.path.isfile(vehicle_path):
            _show_msg(self, QMessageBox.Icon.Warning, "File Not Found", f"Vehicle file not found:\n{vehicle_path}")
            return
        if not os.path.isfile(base_path):
            _show_msg(self, QMessageBox.Icon.Warning, "File Not Found", f"Base station file not found:\n{base_path}")
            return

        output_dir = self._output_dir_selector.path()
        if not output_dir:
            output_dir = str(Path(vehicle_path).parent / "rtk_output")
            self._output_dir_selector.set_path(output_dir)

        self._go_to_step(1)
        self._conv_progress_label.setText("Converting…")
        self._conv_progress_bar.setVisible(True)
        self._step2_next.setEnabled(False)

        self._convert_worker = ConvertWorker(vehicle_path, base_path, output_dir)
        self._convert_worker.progress.connect(lambda msg: self._conv_progress_label.setText(msg))
        self._convert_worker.finished.connect(self._on_conversion_done)
        self._convert_worker.error.connect(self._on_conversion_error)
        self._convert_worker.start()

    def _on_conversion_done(self, vehicle_result: dict, base_result: dict):
        self._vehicle_result = vehicle_result
        self._base_result = base_result

        self._conv_progress_bar.setVisible(False)
        self._conv_progress_label.setText("Conversion complete.")

        self._vehicle_status.set_results("Vehicle Files", vehicle_result)
        self._base_status.set_results("Base Station Files", base_result)

        if "obs" not in vehicle_result:
            _show_msg(self, QMessageBox.Icon.Critical, "Conversion Failed",
                "Vehicle .obs file was not generated. Check that the .ubx file contains valid observation data.")
            return
        if "obs" not in base_result:
            _show_msg(self, QMessageBox.Icon.Critical, "Conversion Failed",
                "Base station .obs file was not generated. Check that the .ubx file contains valid observation data.")
            return

        self._step2_next.setEnabled(True)

    def _on_conversion_error(self, msg: str):
        self._conv_progress_bar.setVisible(False)
        self._conv_progress_label.setText("Conversion failed.")
        _show_msg(self, QMessageBox.Icon.Critical, "Conversion Error", msg)

    # ─── Step 3: RTK Configuration ───

    def _build_step3(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        header = QLabel("Step 3: RTK Processing Configuration")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._config_panel = RTKConfigPanel()
        scroll.setWidget(self._config_panel)
        layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        self._step3_back = QPushButton("← Back")
        self._step3_back.clicked.connect(lambda: self._go_to_step(1))
        btn_layout.addWidget(self._step3_back)
        btn_layout.addStretch()
        self._step3_next = QPushButton("Next: Run Processing →")
        self._step3_next.setStyleSheet("font-size: 14px; padding: 8px 20px;")
        self._step3_next.clicked.connect(lambda: self._go_to_step(3))
        btn_layout.addWidget(self._step3_next)
        layout.addLayout(btn_layout)

        self._stack.addWidget(page)

    def _prepare_config_step(self):
        if self._base_result and "obs" in self._base_result:
            pos = parse_rinex_header_position(self._base_result["obs"])
            if pos:
                lat, lon, hgt = ecef_to_lla(*pos)
                self._config_panel.set_rinex_header_position(lat, lon, hgt)

        self._go_to_step(2)

    # ─── Step 4: Processing ───

    def _build_step4(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        header = QLabel("Step 4: RTK Post-Processing")
        header.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        self._run_btn = QPushButton("Run RTK Processing")
        self._run_btn.setStyleSheet(
            "font-size: 16px; padding: 12px 30px; font-weight: bold; "
            "background-color: #27ae60; color: white; border-radius: 4px;"
        )
        self._run_btn.clicked.connect(self._run_processing)
        layout.addWidget(self._run_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._proc_progress = QProgressBar()
        self._proc_progress.setRange(0, 0)
        self._proc_progress.setVisible(False)
        layout.addWidget(self._proc_progress)

        log_label = QLabel("Processing Log:")
        log_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(log_label)

        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self._log_area, 1)

        # --- Output info ---
        self._output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(self._output_group)
        self._output_path_label = QLabel()
        self._output_path_label.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._output_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        output_layout.addWidget(self._output_path_label)

        out_btn_layout = QHBoxLayout()
        self._copy_path_btn = QPushButton("Copy Path")
        self._copy_path_btn.clicked.connect(self._copy_output_path)
        out_btn_layout.addWidget(self._copy_path_btn)
        self._open_folder_btn = QPushButton("Open Containing Folder")
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        out_btn_layout.addWidget(self._open_folder_btn)
        out_btn_layout.addStretch()
        output_layout.addLayout(out_btn_layout)
        self._output_group.setVisible(False)
        layout.addWidget(self._output_group)

        btn_layout = QHBoxLayout()
        self._step4_back = QPushButton("← Back")
        self._step4_back.clicked.connect(lambda: self._go_to_step(2))
        btn_layout.addWidget(self._step4_back)
        btn_layout.addStretch()
        self._step4_next = QPushButton("View Analysis →")
        self._step4_next.setStyleSheet("font-size: 14px; padding: 8px 20px;")
        self._step4_next.setEnabled(False)
        self._step4_next.clicked.connect(self._go_to_analysis)
        btn_layout.addWidget(self._step4_next)
        layout.addLayout(btn_layout)

        self._stack.addWidget(page)

    def _run_processing(self):
        if not self._vehicle_result or "obs" not in self._vehicle_result:
            _show_msg(self, QMessageBox.Icon.Warning, "Missing Data", "No vehicle .obs file. Run conversion first.")
            return
        if not self._base_result or "obs" not in self._base_result:
            _show_msg(self, QMessageBox.Icon.Warning, "Missing Data", "No base station .obs file. Run conversion first.")
            return

        rover_obs = self._vehicle_result["obs"]
        base_obs = self._base_result["obs"]

        nav_files = []
        for result in (self._vehicle_result, self._base_result):
            for key in ("nav", "gnav", "hnav", "qnav", "lnav", "cnav", "inav"):
                if key in result and result[key] not in nav_files:
                    nav_files.append(result[key])

        output_dir = self._output_dir_selector.path()
        output_path = os.path.join(output_dir, "rtk_solution.pos")

        config = self._config_panel.get_config()

        self._log_area.clear()
        self._run_btn.setEnabled(False)
        self._proc_progress.setVisible(True)
        self._output_group.setVisible(False)
        self._step4_next.setEnabled(False)

        self._rtk_worker = RTKWorker(rover_obs, base_obs, nav_files, output_path, config)
        self._rtk_worker.log.connect(lambda msg: self._log_area.appendPlainText(msg))
        self._rtk_worker.finished.connect(self._on_processing_done)
        self._rtk_worker.start()

    def _on_processing_done(self, returncode: int, stdout: str, stderr: str):
        self._proc_progress.setVisible(False)
        self._run_btn.setEnabled(True)

        output_dir = self._output_dir_selector.path()
        output_path = os.path.join(output_dir, "rtk_solution.pos")

        if returncode != 0:
            self._log_area.appendPlainText(f"\nProcess exited with code {returncode}")
            if not os.path.isfile(output_path):
                _show_msg(self, QMessageBox.Icon.Critical, "Processing Failed",
                    f"rnx2rtkp exited with code {returncode}.\nCheck the log for details.")
                return

        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            self._rtk_output_path = output_path
            self._output_path_label.setText(output_path)
            self._output_group.setVisible(True)
            self._step4_next.setEnabled(True)
            self._log_area.appendPlainText(f"\nOutput written to: {output_path}")
        else:
            _show_msg(self, QMessageBox.Icon.Warning, "No Output",
                "Processing completed but no output file was generated.\n"
                "This may indicate no valid solutions were computed.")

    def _copy_output_path(self):
        if self._rtk_output_path:
            QApplication.clipboard().setText(self._rtk_output_path)

    def _open_output_folder(self):
        if self._rtk_output_path:
            folder = os.path.dirname(self._rtk_output_path)
            import sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

    # ─── Step 5: Analysis ───

    def _build_step5(self):
        self._analysis_view = AnalysisView()
        self._stack.addWidget(self._analysis_view)

    def _go_to_analysis(self):
        if not self._rtk_output_path:
            _show_msg(self, QMessageBox.Icon.Warning, "No Data", "Run RTK processing first.")
            return

        rover_obs = self._vehicle_result["obs"]
        nav_files = []
        for result in (self._vehicle_result, self._base_result):
            for key in ("nav", "gnav", "hnav", "qnav", "lnav", "cnav", "inav"):
                if key in result and result[key] not in nav_files:
                    nav_files.append(result[key])

        output_dir = self._output_dir_selector.path()
        self._analysis_view.set_data(self._rtk_output_path, rover_obs, nav_files, output_dir)
        self._go_to_step(4)
