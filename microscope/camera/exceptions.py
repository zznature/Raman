"""
Custom exceptions for IDS camera operations.
"""


class CameraError(Exception):
    """Base exception for camera operations."""
    pass


class CameraInitError(CameraError):
    """Raised when camera initialization fails."""
    pass


class CameraMemoryError(CameraError):
    """Raised when image memory allocation or management fails."""
    pass


class CameraCaptureError(CameraError):
    """Raised when image capture fails."""
    pass
