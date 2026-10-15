"""Local scene + coarse pose cache to skip redundant Jev calls.

Stores metadata only (no frames). Caps entries, age, and file size so disk
use stays tiny. Never schedules extra API calls — only replaces ones the
motion/heartbeat gates already decided to make.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

Posture = Literal["standing", "sitting", "away"]

MAX_ENTRIES = 32
MAX_AGE_SECONDS = 7 * 24 * 3600
MAX_FILE_BYTES = 32 * 1024
HEARTBEAT_TRUST_AGE = 24 * 3600
FORCE_REFRESH_EVERY = 8
POSE_BANDS = 5  # 0..4

# Center ROI treated as person; borders form the scene fingerprint.
PERSON_WIDTH_FRAC = 0.50
PERSON_HEIGHT_FRAC = 0.70


@dataclass(frozen=True)
class SceneFeatures:
    scene_id: str
    pose_band: str  # "0".."4", "away", or cal labels sit/stand/mid
    pose_raw: float  # 0..1 vertical signal (higher ≈ more standing-like)

    @property
    def key(self) -> str:
        return f"{self.scene_id}:{self.pose_band}"


@dataclass
class CacheEntry:
    posture: Posture
    updated_at: float
    hits: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "posture": self.posture,
            "updated_at": self.updated_at,
            "hits": self.hits,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CacheEntry | None:
        posture = raw.get("posture")
        if posture not in ("standing", "sitting", "away"):
            return None
        try:
            return cls(
                posture=posture,
                updated_at=float(raw.get("updated_at", 0)),
                hits=int(raw.get("hits", 0)),
            )
        except (TypeError, ValueError):
            return None


def extract_features(
    gray: np.ndarray,
    *,
    sit_anchor: float | None = None,
    stand_anchor: float | None = None,
) -> SceneFeatures:
    """Compute border scene hash + coarse pose band from a grayscale frame."""
    if gray.ndim != 2 or gray.size == 0:
        return SceneFeatures(scene_id="0", pose_band="away", pose_raw=0.0)

    scene_id = _border_ahash(gray)
    pose_raw = _person_pose_raw(gray)
    pose_band = _pose_band(pose_raw, sit_anchor=sit_anchor, stand_anchor=stand_anchor)
    return SceneFeatures(scene_id=scene_id, pose_band=pose_band, pose_raw=pose_raw)


def pose_raw_from_gray(gray: np.ndarray) -> float:
    return _person_pose_raw(gray)


def gray_from_jpeg(jpeg_bytes: bytes) -> np.ndarray | None:
    """Decode JPEG bytes to grayscale for calibration anchors."""
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _person_roi(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    rw = max(8, int(w * PERSON_WIDTH_FRAC))
    rh = max(8, int(h * PERSON_HEIGHT_FRAC))
    x0 = max(0, (w - rw) // 2)
    y0 = max(0, (h - rh) // 2)
    return gray[y0 : y0 + rh, x0 : x0 + rw]


def _border_collage(gray: np.ndarray) -> np.ndarray:
    """Assemble border strips into a small collage (person ROI excluded)."""
    h, w = gray.shape[:2]
    strip_h = max(4, h // 8)
    strip_w = max(4, w // 8)
    top = gray[:strip_h, :]
    bottom = gray[h - strip_h :, :]
    left = gray[strip_h : h - strip_h, :strip_w]
    right = gray[strip_h : h - strip_h, w - strip_w :]
    target_w = 32
    top_r = cv2.resize(top, (target_w, 8), interpolation=cv2.INTER_AREA)
    bot_r = cv2.resize(bottom, (target_w, 8), interpolation=cv2.INTER_AREA)
    left_r = cv2.resize(left, (8, 16), interpolation=cv2.INTER_AREA)
    right_r = cv2.resize(right, (8, 16), interpolation=cv2.INTER_AREA)
    mid = np.hstack([left_r, right_r])
    mid = cv2.resize(mid, (target_w, 16), interpolation=cv2.INTER_AREA)
    return np.vstack([top_r, mid, bot_r])


def _border_ahash(gray: np.ndarray) -> str:
    collage = _border_collage(gray)
    small = cv2.resize(collage, (8, 8), interpolation=cv2.INTER_AREA)
    mean = float(np.mean(small))
    bits = (small.astype(np.float32) >= mean).astype(np.uint8).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def _person_pose_raw(gray: np.ndarray) -> float:
    """Vertical mass signal in person ROI: higher ≈ more standing-like."""
    roi = _person_roi(gray)
    blurred = cv2.GaussianBlur(roi, (5, 5), 0)
    edges = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    energy = np.abs(edges)
    row_sum = energy.sum(axis=1)
    total = float(row_sum.sum())
    if total < 1e-3:
        return 0.0
    ys = np.arange(len(row_sum), dtype=np.float64)
    centroid = float(np.dot(row_sum, ys) / total)
    h = max(1, len(row_sum) - 1)
    top_quarter = float(row_sum[: max(1, len(row_sum) // 4)].sum()) / total
    upper = float(row_sum[: len(row_sum) // 2].sum()) / total
    height_score = 1.0 - (centroid / h)
    raw = 0.55 * upper + 0.25 * top_quarter + 0.20 * height_score
    return float(np.clip(raw, 0.0, 1.0))


def _pose_band(
    pose_raw: float,
    *,
    sit_anchor: float | None,
    stand_anchor: float | None,
) -> str:
    if pose_raw < 0.08:
        return "away"

    if (
        sit_anchor is not None
        and stand_anchor is not None
        and abs(stand_anchor - sit_anchor) > 0.04
    ):
        mid = (sit_anchor + stand_anchor) / 2.0
        margin = abs(stand_anchor - sit_anchor) * 0.15
        stand_is_higher = stand_anchor >= sit_anchor
        if pose_raw < mid - margin:
            return "sit" if stand_is_higher else "stand"
        if pose_raw > mid + margin:
            return "stand" if stand_is_higher else "sit"
        return "mid"

    band = int(np.clip(pose_raw * POSE_BANDS, 0, POSE_BANDS - 1))
    return str(band)


class ScenePoseCache:
    """Persisted map of scene+pose → last Jev posture."""

    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._entries: dict[str, CacheEntry] = {}
        self._sit_anchor: float | None = None
        self._stand_anchor: float | None = None
        self._consecutive_hits = 0
        self._last_hit_key: str | None = None
        if enabled:
            self._load()

    @property
    def sit_anchor(self) -> float | None:
        return self._sit_anchor

    @property
    def stand_anchor(self) -> float | None:
        return self._stand_anchor

    def features(self, gray: np.ndarray) -> SceneFeatures:
        return extract_features(
            gray,
            sit_anchor=self._sit_anchor,
            stand_anchor=self._stand_anchor,
        )

    def set_calibration_anchors(
        self,
        *,
        sitting_gray: np.ndarray | None = None,
        standing_gray: np.ndarray | None = None,
    ) -> None:
        if sitting_gray is not None:
            self._sit_anchor = pose_raw_from_gray(sitting_gray)
        if standing_gray is not None:
            self._stand_anchor = pose_raw_from_gray(standing_gray)
        self._save()

    def clear(self) -> None:
        self._entries.clear()
        self._sit_anchor = None
        self._stand_anchor = None
        self._consecutive_hits = 0
        self._last_hit_key = None
        if self.path.exists():
            self.path.unlink()

    def lookup(
        self,
        features: SceneFeatures,
        *,
        reason: str,
        current_posture: str,
    ) -> Posture | None:
        """Return cached posture if trusted for this reason, else None."""
        if not self.enabled:
            return None
        if reason not in ("motion", "heartbeat"):
            self._consecutive_hits = 0
            self._last_hit_key = None
            return None

        entry = self._entries.get(features.key)
        if entry is None:
            self._consecutive_hits = 0
            self._last_hit_key = None
            return None

        now = time.time()
        age = now - entry.updated_at
        if age > HEARTBEAT_TRUST_AGE:
            self._consecutive_hits = 0
            self._last_hit_key = None
            return None

        if reason == "motion" and entry.posture != current_posture:
            self._consecutive_hits = 0
            self._last_hit_key = None
            return None

        # After N successful hits on this key, force one Jev refresh.
        if (
            self._last_hit_key == features.key
            and self._consecutive_hits >= FORCE_REFRESH_EVERY
        ):
            self._consecutive_hits = 0
            self._last_hit_key = None
            return None

        entry.hits += 1
        entry.updated_at = now
        if self._last_hit_key == features.key:
            self._consecutive_hits += 1
        else:
            self._consecutive_hits = 1
            self._last_hit_key = features.key
        self._save()
        return entry.posture

    def remember(self, features: SceneFeatures, posture: Posture) -> None:
        if not self.enabled:
            return
        if posture not in ("standing", "sitting", "away"):
            return
        now = time.time()
        existing = self._entries.get(features.key)
        hits = existing.hits if existing else 0
        self._entries[features.key] = CacheEntry(
            posture=posture, updated_at=now, hits=hits
        )
        self._consecutive_hits = 0
        self._last_hit_key = None
        self._prune(now)
        self._save()

    def _prune(self, now: float) -> None:
        expired = [
            k
            for k, e in self._entries.items()
            if now - e.updated_at > MAX_AGE_SECONDS
        ]
        for k in expired:
            del self._entries[k]
        if len(self._entries) <= MAX_ENTRIES:
            return
        ordered = sorted(
            self._entries.items(), key=lambda kv: kv[1].updated_at, reverse=True
        )
        self._entries = dict(ordered[:MAX_ENTRIES])

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        anchors = raw.get("anchors") or {}
        if isinstance(anchors, dict):
            sit = anchors.get("sitting")
            stand = anchors.get("standing")
            try:
                self._sit_anchor = float(sit) if sit is not None else None
            except (TypeError, ValueError):
                self._sit_anchor = None
            try:
                self._stand_anchor = float(stand) if stand is not None else None
            except (TypeError, ValueError):
                self._stand_anchor = None
        entries_raw = raw.get("entries") or {}
        if not isinstance(entries_raw, dict):
            return
        now = time.time()
        loaded: dict[str, CacheEntry] = {}
        for key, val in entries_raw.items():
            if not isinstance(key, str) or not isinstance(val, dict):
                continue
            entry = CacheEntry.from_dict(val)
            if entry is None:
                continue
            if now - entry.updated_at > MAX_AGE_SECONDS:
                continue
            loaded[key] = entry
        self._entries = loaded
        self._prune(now)

    def _save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 1,
            "anchors": {
                "sitting": self._sit_anchor,
                "standing": self._stand_anchor,
            },
            "entries": {k: e.as_dict() for k, e in self._entries.items()},
        }
        text = json.dumps(payload, separators=(",", ":"))
        while len(text.encode("utf-8")) > MAX_FILE_BYTES and self._entries:
            oldest = min(self._entries.items(), key=lambda kv: kv[1].updated_at)
            del self._entries[oldest[0]]
            payload["entries"] = {k: e.as_dict() for k, e in self._entries.items()}
            text = json.dumps(payload, separators=(",", ":"))
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.path)
