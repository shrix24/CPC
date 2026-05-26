from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QRadioButton,
    QLabel, QLineEdit, QButtonGroup,
)
from PySide6.QtCore import Qt


PROCESSING_MODES = [
    ("Kinematic", 2),
    ("Static", 3),
    ("Single", 0),
    ("DGPS", 1),
    ("Moving-Base", 4),
    ("Fixed", 5),
    ("PPP-Kinematic", 6),
    ("PPP-Static", 7),
]

CONSTELLATIONS = [
    ("GPS", "G"),
    ("GLONASS", "R"),
    ("Galileo", "E"),
    ("BeiDou", "C"),
    ("QZSS", "J"),
    ("IRNSS", "I"),
]

FREQUENCIES = [
    ("L1 only", 1),
    ("L1 + L2", 2),
    ("L1 + L2 + L5", 3),
]


class RTKConfigPanel(QWidget):
    """Configuration form for RTK processing parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # --- Processing Mode ---
        mode_group = QGroupBox("Processing Mode")
        mode_layout = QFormLayout(mode_group)
        self._mode_combo = QComboBox()
        for name, _ in PROCESSING_MODES:
            self._mode_combo.addItem(name)
        self._mode_combo.setCurrentIndex(0)
        mode_layout.addRow("Mode:", self._mode_combo)
        layout.addWidget(mode_group)

        # --- Satellite Constellations ---
        const_group = QGroupBox("Satellite Constellations")
        const_layout = QHBoxLayout(const_group)
        self._constellation_checks = {}
        for name, code in CONSTELLATIONS:
            cb = QCheckBox(name)
            cb.setChecked(code in ("G", "R"))
            self._constellation_checks[code] = cb
            const_layout.addWidget(cb)
        const_layout.addStretch()
        layout.addWidget(const_group)

        # --- Frequencies ---
        freq_group = QGroupBox("Frequencies")
        freq_layout = QFormLayout(freq_group)
        self._freq_combo = QComboBox()
        for name, _ in FREQUENCIES:
            self._freq_combo.addItem(name)
        self._freq_combo.setCurrentIndex(1)
        freq_layout.addRow("Frequency:", self._freq_combo)
        layout.addWidget(freq_group)

        # --- Elevation Mask ---
        elev_group = QGroupBox("Elevation Mask")
        elev_layout = QFormLayout(elev_group)
        self._elev_spin = QSpinBox()
        self._elev_spin.setRange(5, 45)
        self._elev_spin.setValue(15)
        self._elev_spin.setSuffix("°")
        elev_layout.addRow("Mask angle:", self._elev_spin)
        layout.addWidget(elev_group)

        # --- Base Station Position ---
        base_group = QGroupBox("Base Station Position")
        base_layout = QVBoxLayout(base_group)

        self._base_btn_group = QButtonGroup(self)
        self._base_avg = QRadioButton("Average of single-point positions (default)")
        self._base_avg.setChecked(True)
        self._base_rinex = QRadioButton("From RINEX header")
        self._base_manual = QRadioButton("Manual entry")
        self._base_btn_group.addButton(self._base_avg, 0)
        self._base_btn_group.addButton(self._base_rinex, 1)
        self._base_btn_group.addButton(self._base_manual, 2)

        base_layout.addWidget(self._base_avg)
        base_layout.addWidget(self._base_rinex)
        base_layout.addWidget(self._base_manual)

        self._manual_widget = QWidget()
        manual_layout = QFormLayout(self._manual_widget)
        manual_layout.setContentsMargins(20, 5, 0, 0)
        self._lat_edit = QDoubleSpinBox()
        self._lat_edit.setRange(-90.0, 90.0)
        self._lat_edit.setDecimals(8)
        self._lat_edit.setSuffix("°")
        self._lon_edit = QDoubleSpinBox()
        self._lon_edit.setRange(-180.0, 180.0)
        self._lon_edit.setDecimals(8)
        self._lon_edit.setSuffix("°")
        self._hgt_edit = QDoubleSpinBox()
        self._hgt_edit.setRange(-1000.0, 100000.0)
        self._hgt_edit.setDecimals(4)
        self._hgt_edit.setSuffix(" m")
        manual_layout.addRow("Latitude:", self._lat_edit)
        manual_layout.addRow("Longitude:", self._lon_edit)
        manual_layout.addRow("Height:", self._hgt_edit)
        self._manual_widget.setVisible(False)
        base_layout.addWidget(self._manual_widget)

        self._base_btn_group.idToggled.connect(self._on_base_source_changed)

        layout.addWidget(base_group)

        # --- Ambiguity Resolution ---
        ar_group = QGroupBox("Ambiguity Resolution")
        ar_layout = QFormLayout(ar_group)

        self._ar_threshold = QDoubleSpinBox()
        self._ar_threshold.setRange(0.0, 100.0)
        self._ar_threshold.setValue(3.0)
        self._ar_threshold.setDecimals(1)
        self._ar_threshold.setToolTip("0 = no ambiguity resolution")
        ar_layout.addRow("Validation threshold:", self._ar_threshold)

        self._fix_hold = QCheckBox("Fix and hold")
        ar_layout.addRow(self._fix_hold)

        self._instantaneous = QCheckBox("Instantaneous AR")
        ar_layout.addRow(self._instantaneous)

        layout.addWidget(ar_group)

        # --- Solution & Output ---
        out_group = QGroupBox("Solution & Output")
        out_layout = QFormLayout(out_group)

        self._combined = QCheckBox("Combined (forward/backward)")
        out_layout.addRow(self._combined)

        self._time_combo = QComboBox()
        self._time_combo.addItems(["GPST", "UTC"])
        out_layout.addRow("Time system:", self._time_combo)

        layout.addWidget(out_group)
        layout.addStretch()

    def _on_base_source_changed(self, button_id: int, checked: bool):
        if checked:
            self._manual_widget.setVisible(button_id == 2)

    def set_rinex_header_position(self, lat: float, lon: float, hgt: float):
        """Pre-fill coordinates from RINEX header for the 'From RINEX header' option."""
        self._rinex_lat = lat
        self._rinex_lon = lon
        self._rinex_hgt = hgt

    def get_config(self) -> dict:
        """Return the current configuration as a dict for rtk_processor."""
        mode_idx = self._mode_combo.currentIndex()
        _, mode_val = PROCESSING_MODES[mode_idx]

        constellations = [code for code, cb in self._constellation_checks.items() if cb.isChecked()]

        freq_idx = self._freq_combo.currentIndex()
        _, freq_val = FREQUENCIES[freq_idx]

        base_id = self._base_btn_group.checkedId()
        if base_id == 0:
            base_pos = {"source": "average"}
        elif base_id == 1:
            base_pos = {
                "source": "rinex_header",
                "lat": getattr(self, "_rinex_lat", 0.0),
                "lon": getattr(self, "_rinex_lon", 0.0),
                "hgt": getattr(self, "_rinex_hgt", 0.0),
            }
        else:
            base_pos = {
                "source": "manual",
                "lat": self._lat_edit.value(),
                "lon": self._lon_edit.value(),
                "hgt": self._hgt_edit.value(),
            }

        return {
            "mode": mode_val,
            "elevation_mask": self._elev_spin.value(),
            "constellations": constellations,
            "frequencies": freq_val,
            "ar_threshold": self._ar_threshold.value(),
            "fix_and_hold": self._fix_hold.isChecked(),
            "instantaneous_ar": self._instantaneous.isChecked(),
            "combined_solution": self._combined.isChecked(),
            "time_utc": self._time_combo.currentIndex() == 1,
            "base_position": base_pos,
        }
