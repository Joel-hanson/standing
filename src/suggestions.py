"""Local suggestion engine — no API cost; drives macOS notifications."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tracker import TrackerSnapshot


@dataclass(frozen=True)
class Suggestion:
    id: str
    title: str
    message: str


# Rotating posture education (not tied to a single streak).
_POSTURE_TIPS = (
    Suggestion(
        "posture_screen",
        "Posture tip",
        "Raise the screen so the top is near eye level — less neck bend.",
    ),
    Suggestion(
        "posture_elbows",
        "Posture tip",
        "Keep elbows near 90° and shoulders relaxed while typing.",
    ),
    Suggestion(
        "posture_feet",
        "Posture tip",
        "If standing: soft knees, weight even on both feet. If sitting: feet flat.",
    ),
    Suggestion(
        "posture_break",
        "Posture tip",
        "Every break, roll shoulders and look 20 feet away for 20 seconds.",
    ),
)


@dataclass
class SuggestionEngine:
    """Rule-based standing nudges from sit/stand patterns."""

    sit_warn_minutes: float = 30.0
    stand_warn_minutes: float = 45.0
    tip_cooldown_minutes: float = 25.0
    posture_tip_every_minutes: float = 120.0
    low_movement_stand_ups: int = 2
    low_movement_after_minutes: float = 180.0  # ~3h into a tracked day
    enabled: bool = True

    _last_sent: dict[str, float] = field(default_factory=dict)
    _last_any_at: float = 0.0
    _posture_tip_index: int = 0
    _tracking_started_at: float | None = None
    _was_tracking: bool = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def evaluate(self, snap: TrackerSnapshot) -> Suggestion | None:
        if not self.enabled or not snap.tracking:
            if not snap.tracking:
                self._was_tracking = False
                self._tracking_started_at = None
            return None

        now = time.monotonic()
        if not self._was_tracking:
            self._tracking_started_at = now
            self._was_tracking = True
            # Don't fire a posture tip the instant tracking starts.
            self._last_sent["posture_rotate"] = now

        # Global gap so we don't stack banners.
        if now - self._last_any_at < 8.0:
            return None

        candidates: list[Suggestion] = []

        if snap.posture == "sitting" and snap.sitting_streak_seconds >= self.sit_warn_minutes * 60:
            mins = max(1, int(snap.sitting_streak_seconds // 60))
            candidates.append(
                Suggestion(
                    "sit_too_long",
                    "Time to stand",
                    f"You've been sitting about {mins} minutes. "
                    "Stand up, walk, or stretch for 2 minutes.",
                )
            )

        if snap.posture == "standing" and snap.standing_streak_seconds >= self.stand_warn_minutes * 60:
            mins = max(1, int(snap.standing_streak_seconds // 60))
            candidates.append(
                Suggestion(
                    "stand_too_long",
                    "Time to sit or move",
                    f"You've been standing about {mins} minutes. "
                    "Sit briefly or walk to reset legs and back.",
                )
            )

        started = self._tracking_started_at or now
        if (
            now - started >= self.low_movement_after_minutes * 60
            and snap.stand_ups < self.low_movement_stand_ups
            and snap.posture == "sitting"
        ):
            candidates.append(
                Suggestion(
                    "low_standups",
                    "Move a little",
                    f"Only {snap.stand_ups} stand-up(s) so far. "
                    "Try one short stand break — it adds up.",
                )
            )

        # Occasional general posture education.
        if now - self._last_sent.get("posture_rotate", now) >= self.posture_tip_every_minutes * 60:
            tip = _POSTURE_TIPS[self._posture_tip_index % len(_POSTURE_TIPS)]
            self._posture_tip_index += 1
            candidates.append(
                Suggestion("posture_rotate", tip.title, tip.message)
            )

        for tip in candidates:
            if self._can_send(tip.id, now):
                self._mark_sent(tip.id, now)
                return tip
        return None

    def _can_send(self, tip_id: str, now: float) -> bool:
        last = self._last_sent.get(tip_id, 0.0)
        return now - last >= self.tip_cooldown_minutes * 60

    def _mark_sent(self, tip_id: str, now: float) -> None:
        self._last_sent[tip_id] = now
        self._last_any_at = now
