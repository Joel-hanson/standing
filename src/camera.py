"""Webcam capture and JPEG prep within TypeSafe image limits."""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image as PILImage
from PIL import ImageOps


# TypeSafe: each side 256–1568; total pixels ≥ 78_400 (≈280×280).
# Smaller images → fewer input tokens (stay safely above the minimum).
MIN_SIDE = 280
DEFAULT_MAX_SIDE = 360


class CameraUnavailable(RuntimeError):
    """Camera temporarily unavailable (common after Mac sleep)."""


@dataclass(frozen=True)
class PreparedFrame:
    """A camera frame ready for motion scoring and/or API upload."""

    bgr: np.ndarray
    jpeg_bytes: bytes
    gray_small: np.ndarray


class Camera:
    def __init__(self, device_index: int = 0, max_side: int = DEFAULT_MAX_SIDE) -> None:
        self.device_index = device_index
        self.max_side = max(MIN_SIDE, min(max_side, 1568))
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._cap is not None and self._cap.isOpened():
            return
        self.close()
        cap = cv2.VideoCapture(self.device_index)
        if not cap.isOpened():
            raise CameraUnavailable(
                f"Could not open camera {self.device_index}. "
                "Check macOS Camera permissions for Terminal/Python."
            )
        # Prefer a modest capture size; we resize again for the API.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._cap = cap

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def reopen(self) -> None:
        """Release and reopen — needed after sleep/wake on macOS."""
        self.close()
        self.open()

    def __enter__(self) -> Camera:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def grab(self, *, retry: bool = True) -> PreparedFrame:
        if self._cap is None or not self._cap.isOpened():
            self.open()
        assert self._cap is not None

        ok, frame = self._cap.read()
        if (not ok or frame is None) and retry:
            # Sleep/wake often leaves the capture handle dead; reopen once.
            self.reopen()
            assert self._cap is not None
            ok, frame = self._cap.read()

        if not ok or frame is None:
            # Keep the handle closed so the next attempt does a clean open.
            self.close()
            raise CameraUnavailable(
                "Camera unavailable (Mac sleep/wake or another app using it)."
            )

        prepared_bgr = _fit_for_api(frame, self.max_side)
        jpeg_bytes = _encode_jpeg(prepared_bgr)
        gray_small = cv2.cvtColor(prepared_bgr, cv2.COLOR_BGR2GRAY)
        gray_small = cv2.GaussianBlur(gray_small, (5, 5), 0)
        return PreparedFrame(bgr=prepared_bgr, jpeg_bytes=jpeg_bytes, gray_small=gray_small)


def _fit_for_api(bgr: np.ndarray, max_side: int) -> np.ndarray:
    """Resize so longest side ≤ max_side and both sides ≥ MIN_SIDE when possible."""
    h, w = bgr.shape[:2]
    scale = min(max_side / max(h, w), 1.0)
    if scale < 1.0:
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = new_h, new_w

    # Upscale if under the TypeSafe minimum side / pixel area.
    if min(h, w) < MIN_SIDE or h * w < 78_400:
        scale_up = max(MIN_SIDE / min(h, w), (78_400 / (h * w)) ** 0.5)
        # Keep longest side ≤ 1568.
        scale_up = min(scale_up, 1568 / max(h, w))
        new_w = max(MIN_SIDE, int(round(w * scale_up)))
        new_h = max(MIN_SIDE, int(round(h * scale_up)))
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    return bgr


def _encode_jpeg(bgr: np.ndarray, quality: int = 65) -> bytes:
    """Encode as baseline JPEG; apply EXIF-style upright via Pillow path."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    img = PILImage.fromarray(rgb)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
