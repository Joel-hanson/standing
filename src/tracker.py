"""Stand-up count and standing-time tracker with daily JSON persistence."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

Posture = Literal["standing", "sitting", "away", "unknown"]

# Keep enough history for a useful Settings glance without growing forever.
HISTORY_LIMIT = 60
HISTORY_DISPLAY = 14


def _today() -> str:
    return date.today().isoformat()


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_day_label(day: str) -> str:
    """Human date label; falls back to ISO if parsing fails."""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return day
    today = date.today()
    if d == today:
        return "Today"
    if (today - d).days == 1:
        return "Yesterday"
    return d.strftime("%b %-d") if _supports_dash_d() else d.strftime("%b %d").replace(" 0", " ")


def _supports_dash_d() -> bool:
    # %-d is POSIX; Windows/strftime may not support it.
    try:
        return datetime(2020, 1, 5).strftime("%-d") == "5"
    except ValueError:
        return False


@dataclass
class DayStats:
    day: str = field(default_factory=_today)
    stand_ups: int = 0
    standing_seconds: float = 0.0
    sitting_seconds: float = 0.0
    api_calls: int = 0
    input_tokens: int = 0

    def estimated_cost_usd(self) -> float:
        return self.input_tokens * 0.042 / 1_000_000

    def has_activity(self) -> bool:
        return (
            self.stand_ups > 0
            or self.standing_seconds >= 1.0
            or self.sitting_seconds >= 1.0
        )

    def summary_line(self) -> str:
        return (
            f"{format_day_label(self.day)}  ·  {self.stand_ups} stand-ups · "
            f"Stand {format_duration(self.standing_seconds)} · "
            f"Sit {format_duration(self.sitting_seconds)}"
        )

    def as_history_entry(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "stand_ups": self.stand_ups,
            "standing_seconds": round(self.standing_seconds, 1),
            "sitting_seconds": round(self.sitting_seconds, 1),
            "api_calls": self.api_calls,
            "input_tokens": self.input_tokens,
            "label": format_day_label(self.day),
            "summary": self.summary_line(),
        }


@dataclass
class TrackerSnapshot:
    posture: Posture
    stand_ups: int
    standing_seconds_today: float
    sitting_seconds_today: float
    standing_streak_seconds: float
    sitting_streak_seconds: float
    api_calls: int
    input_tokens: int
    estimated_cost_usd: float
    tracking: bool
    last_error: str | None
    motion_score: float
    last_call_reason: str | None


class StandingTracker:
    def __init__(self, stats_path: Path, history_path: Path | None = None) -> None:
        self.stats_path = stats_path
        self.history_path = history_path or (stats_path.parent / "history.json")
        self.posture: Posture = "unknown"
        self.tracking = False
        self.last_error: str | None = None
        self.motion_score = 0.0
        self.last_call_reason: str | None = None
        self._standing_since: float | None = None
        self._sitting_since: float | None = None
        self._last_tick: float = time.monotonic()
        self.stats = self._load()

    def _day_from_raw(self, raw: dict[str, Any]) -> DayStats:
        return DayStats(
            day=str(raw.get("day", _today())),
            stand_ups=int(raw.get("stand_ups", 0)),
            standing_seconds=float(raw.get("standing_seconds", 0)),
            sitting_seconds=float(raw.get("sitting_seconds", 0)),
            api_calls=int(raw.get("api_calls", 0)),
            input_tokens=int(raw.get("input_tokens", 0)),
        )

    def _load(self) -> DayStats:
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.stats_path.exists():
            return DayStats()
        try:
            raw = json.loads(self.stats_path.read_text())
            stats = self._day_from_raw(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return DayStats()
        if stats.day != _today():
            self._archive_day(stats)
            return DayStats()
        return stats

    def _load_history(self) -> list[DayStats]:
        if not self.history_path.exists():
            return []
        try:
            raw = json.loads(self.history_path.read_text())
            days = raw.get("days", raw if isinstance(raw, list) else [])
            out: list[DayStats] = []
            for item in days:
                if isinstance(item, dict):
                    out.append(self._day_from_raw(item))
            return out
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return []

    def _save_history(self, days: list[DayStats]) -> None:
        # Newest first, unique by day, capped.
        by_day: dict[str, DayStats] = {}
        for d in days:
            by_day[d.day] = d
        ordered = sorted(by_day.values(), key=lambda d: d.day, reverse=True)[:HISTORY_LIMIT]
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "days": [
                {
                    "day": d.day,
                    "stand_ups": d.stand_ups,
                    "standing_seconds": round(d.standing_seconds, 1),
                    "sitting_seconds": round(d.sitting_seconds, 1),
                    "api_calls": d.api_calls,
                    "input_tokens": d.input_tokens,
                }
                for d in ordered
            ]
        }
        self.history_path.write_text(json.dumps(payload, indent=2) + "\n")

    def _archive_day(self, stats: DayStats) -> None:
        if not stats.has_activity():
            return
        days = self._load_history()
        days.append(stats)
        self._save_history(days)

    def save(self) -> None:
        self._roll_day_if_needed()
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats_path.write_text(json.dumps(asdict(self.stats), indent=2) + "\n")

    def _roll_day_if_needed(self) -> None:
        today = _today()
        if self.stats.day == today:
            return
        self._accumulate(time.monotonic())
        self._archive_day(self.stats)
        self.stats = DayStats(day=today)
        now = time.monotonic()
        if self.tracking and self.posture == "standing":
            self._standing_since = now
            self._sitting_since = None
        elif self.tracking and self.posture == "sitting":
            self._sitting_since = now
            self._standing_since = None

    def set_tracking(self, enabled: bool) -> None:
        now = time.monotonic()
        if enabled and not self.tracking:
            self._last_tick = now
            if self.posture == "standing":
                self._standing_since = now
                self._sitting_since = None
            elif self.posture == "sitting":
                self._sitting_since = now
                self._standing_since = None
        elif not enabled and self.tracking:
            self._accumulate(now)
            self._standing_since = None
            self._sitting_since = None
        self.tracking = enabled
        self.save()

    def reset_day(self) -> None:
        """Clear today's counters only — past history is kept."""
        now = time.monotonic()
        self._accumulate(now)
        self.stats = DayStats(day=_today())
        if self.tracking and self.posture == "standing":
            self._standing_since = now
            self._sitting_since = None
        elif self.tracking and self.posture == "sitting":
            self._sitting_since = now
            self._standing_since = None
        else:
            self._standing_since = None
            self._sitting_since = None
        self.last_error = None
        self.save()

    def tick(self) -> None:
        self._roll_day_if_needed()
        if not self.tracking:
            self._last_tick = time.monotonic()
            return
        now = time.monotonic()
        self._accumulate(now)
        self._last_tick = now

    def _accumulate(self, now: float) -> None:
        if not self.tracking:
            return
        delta = max(0.0, now - self._last_tick)
        if self.posture == "standing":
            if self._standing_since is None:
                self._standing_since = now
            self.stats.standing_seconds += delta
        elif self.posture == "sitting":
            if self._sitting_since is None:
                self._sitting_since = now
            self.stats.sitting_seconds += delta

    def set_posture_from_api(
        self,
        new_posture: Posture,
        *,
        input_tokens: int,
        reason: str,
    ) -> None:
        self._roll_day_if_needed()
        now = time.monotonic()
        self._accumulate(now)

        prev = self.posture
        if new_posture == "standing" and prev in ("sitting", "away"):
            self.stats.stand_ups += 1

        if new_posture == "standing":
            if prev != "standing":
                self._standing_since = now
            self._sitting_since = None
        elif new_posture == "sitting":
            if prev != "sitting":
                self._sitting_since = now
            self._standing_since = None
        else:
            self._standing_since = None
            self._sitting_since = None

        self.posture = new_posture
        self.stats.api_calls += 1
        self.stats.input_tokens += input_tokens
        self.last_call_reason = reason
        self.last_error = None
        self._last_tick = now
        self.save()

    def set_error(self, message: str) -> None:
        self.last_error = message

    def set_motion_score(self, score: float) -> None:
        self.motion_score = score

    def standing_streak_seconds(self) -> float:
        if (
            self.posture != "standing"
            or not self.tracking
            or self._standing_since is None
        ):
            return 0.0
        return max(0.0, time.monotonic() - self._standing_since)

    def sitting_streak_seconds(self) -> float:
        if (
            self.posture != "sitting"
            or not self.tracking
            or self._sitting_since is None
        ):
            return 0.0
        return max(0.0, time.monotonic() - self._sitting_since)

    def history_entries(self, *, limit: int = HISTORY_DISPLAY) -> list[dict[str, Any]]:
        """Recent days for UI: today (if any activity) then archived days, newest first."""
        self._roll_day_if_needed()
        entries: list[dict[str, Any]] = []
        if self.stats.has_activity():
            entries.append(self.stats.as_history_entry())
        for day in self._load_history():
            if day.day == self.stats.day or not day.has_activity():
                continue
            entries.append(day.as_history_entry())
            if len(entries) >= limit:
                break
        return entries[:limit]

    def history_label(self, *, limit: int = HISTORY_DISPLAY) -> str:
        entries = self.history_entries(limit=limit)
        if not entries:
            return "No activity recorded yet"
        return "\n".join(str(e["summary"]) for e in entries)

    def snapshot(self) -> TrackerSnapshot:
        self.tick()
        return TrackerSnapshot(
            posture=self.posture,
            stand_ups=self.stats.stand_ups,
            standing_seconds_today=self.stats.standing_seconds,
            sitting_seconds_today=self.stats.sitting_seconds,
            standing_streak_seconds=self.standing_streak_seconds(),
            sitting_streak_seconds=self.sitting_streak_seconds(),
            api_calls=self.stats.api_calls,
            input_tokens=self.stats.input_tokens,
            estimated_cost_usd=self.stats.estimated_cost_usd(),
            tracking=self.tracking,
            last_error=self.last_error,
            motion_score=self.motion_score,
            last_call_reason=self.last_call_reason,
        )
