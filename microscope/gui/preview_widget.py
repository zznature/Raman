"""
Live preview widget — displays numpy frames as scaled QPixmap on a QLabel.
"""

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QSizePolicy

from microscope.config import PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT


class PreviewWidget(QLabel):
    """QLabel-based widget that renders grayscale numpy frames with aspect-ratio scaling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMaximumSize(PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: black;")
        self.setText("No Preview")
        self.setStyleSheet("background-color: black; color: #666; font-size: 14px;")

    def update_frame(self, frame: np.ndarray) -> None:
        """Convert numpy array to QPixmap and display with aspect-ratio scaling."""
        h, w = frame.shape[:2]
        bytes_per_line = w

        qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimg)

        # Scale to widget size keeping aspect ratio
        scaled = pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def clear_preview(self) -> None:
        """Reset to blank state."""
        self.clear()
        self.setText("No Preview")
