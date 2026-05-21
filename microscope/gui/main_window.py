"""
Main application window for IDS Camera acquisition.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QPushButton,
    QDoubleSpinBox,
    QLabel,
    QStatusBar,
    QMessageBox,
)

from microscope.acquisition.controller import AcquisitionController
from microscope.config import DEFAULT_EXPOSURE_MS
from .preview_widget import PreviewWidget


class MainWindow(QMainWindow):
    """Main window with live preview and camera controls."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IDS Camera - Raman Microscope")
        self.setMinimumSize(900, 600)

        self._controller = AcquisitionController()
        self._init_ui()
        self._connect_signals()
        self._update_button_states()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)

        # Left: preview
        self._preview = PreviewWidget()
        layout.addWidget(self._preview, stretch=3)

        # Right: controls
        controls = QVBoxLayout()
        layout.addLayout(controls, stretch=1)

        # Connection group
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)
        self._btn_connect = QPushButton("Connect Camera")
        self._btn_disconnect = QPushButton("Disconnect")
        conn_layout.addWidget(self._btn_connect)
        conn_layout.addWidget(self._btn_disconnect)
        controls.addWidget(conn_group)

        # Capture group
        cap_group = QGroupBox("Capture")
        cap_layout = QVBoxLayout(cap_group)
        self._btn_start_live = QPushButton("Start Live View")
        self._btn_stop_live = QPushButton("Stop Live View")
        self._btn_snapshot = QPushButton("Snapshot")
        cap_layout.addWidget(self._btn_start_live)
        cap_layout.addWidget(self._btn_stop_live)
        cap_layout.addWidget(self._btn_snapshot)
        controls.addWidget(cap_group)

        # Exposure group
        exp_group = QGroupBox("Exposure (ms)")
        exp_layout = QVBoxLayout(exp_group)
        self._spin_exposure = QDoubleSpinBox()
        self._spin_exposure.setRange(0.01, 5000.0)
        self._spin_exposure.setDecimals(2)
        self._spin_exposure.setValue(DEFAULT_EXPOSURE_MS)
        self._btn_set_exposure = QPushButton("Set Exposure")
        exp_layout.addWidget(self._spin_exposure)
        exp_layout.addWidget(self._btn_set_exposure)
        controls.addWidget(exp_group)

        controls.addStretch()

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Disconnected")

    def _connect_signals(self) -> None:
        self._btn_connect.clicked.connect(self._on_connect)
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        self._btn_start_live.clicked.connect(self._on_start_live)
        self._btn_stop_live.clicked.connect(self._on_stop_live)
        self._btn_snapshot.clicked.connect(self._on_snapshot)
        self._btn_set_exposure.clicked.connect(self._on_set_exposure)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        try:
            w, h = self._controller.connect()
            self._status.showMessage(f"Connected: {w}x{h}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))
        self._update_button_states()

    def _on_disconnect(self) -> None:
        self._controller.disconnect()
        self._preview.clear_preview()
        self._status.showMessage("Disconnected")
        self._update_button_states()

    def _on_start_live(self) -> None:
        try:
            self._controller.start_live(
                on_frame=self._preview.update_frame,
                on_error=self._on_capture_error,
            )
        except Exception as e:
            QMessageBox.critical(self, "Capture Error", str(e))
        self._update_button_states()

    def _on_stop_live(self) -> None:
        self._controller.stop_live()
        self._update_button_states()

    def _on_snapshot(self) -> None:
        path = self._controller.snapshot()
        if path:
            self._status.showMessage(f"Saved: {path}")
        else:
            self._status.showMessage("No frame available for snapshot")

    def _on_set_exposure(self) -> None:
        ms = self._spin_exposure.value()
        try:
            actual = self._controller.set_exposure(ms)
            self._spin_exposure.setValue(actual)
            self._status.showMessage(f"Exposure set: {actual:.2f} ms")
        except Exception as e:
            QMessageBox.critical(self, "Exposure Error", str(e))

    def _on_capture_error(self, msg: str) -> None:
        self._controller.stop_live()
        self._status.showMessage(f"Error: {msg}")
        self._update_button_states()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_button_states(self) -> None:
        connected = self._controller.is_connected
        live = self._controller.is_live

        self._btn_connect.setEnabled(not connected)
        self._btn_disconnect.setEnabled(connected)
        self._btn_start_live.setEnabled(connected and not live)
        self._btn_stop_live.setEnabled(live)
        self._btn_snapshot.setEnabled(connected)
        self._btn_set_exposure.setEnabled(connected)
        self._spin_exposure.setEnabled(connected)

    def closeEvent(self, event) -> None:
        """Ensure camera resources are released on window close."""
        self._controller.disconnect()
        event.accept()
