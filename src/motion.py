"""Local frame-diff motion gate to avoid unnecessary Jev calls."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MotionGate:
    """Scores motion between consecutive grayscale frames."""

    threshold: float = 8.0
    _prev: np.ndarray | None = None

    def score(self, gray: np.ndarray) -> float:
        """Return mean absolute pixel difference vs previous frame (0 if first)."""
        if self._prev is None or self._prev.shape != gray.shape:
            self._prev = gray.copy()
            return 0.0
        diff = cv2_absdiff(self._prev, gray)
        self._prev = gray.copy()
        return float(np.mean(diff))

    def is_significant(self, gray: np.ndarray) -> tuple[bool, float]:
        value = self.score(gray)
        return value >= self.threshold, value

    def reset(self) -> None:
        self._prev = None


def cv2_absdiff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # Avoid importing cv2 here for the math; uint8 wrap-safe absdiff.
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
