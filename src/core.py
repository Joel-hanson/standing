"""UI-agnostic Standing brain (AI-based standing tracker) — shared by rumps and the Swift worker."""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.camera import DEFAULT_MAX_SIDE, Camera, CameraUnavailable
from src.credentials import clear_api_key, get_api_key, set_api_key
from src.jev_client import JevPostureClient
from src.logging_setup import get_logger
from src.motion import MotionGate
from src import strava as strava_api
from src.suggestions import SuggestionEngine
from src.tracker import StandingTracker, format_duration

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATS_PATH = DATA / "stats.json"
HISTORY_PATH = DATA / "history.json"
STANDING_CAL = DATA / "calibrate_standing.jpg"
SITTING_CAL = DATA / "calibrate_sitting.jpg"
DEFAULT_LOG = DATA / "standing.log"

NotifyFn = Callable[[str, str], None]
StateFn = Callable[[dict[str, Any]], None]


def calibration_label(*, has_standing: bool, has_sitting: bool) -> str:
    if has_standing and has_sitting:
        return "Calibration: ready"
    if has_standing:
        return "Calibration: add sitting"
    if has_sitting:
        return "Calibration: add standing"
    return "Calibration: not set"


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--idle-seconds", type=float, default=180.0, help="Heartbeat when still")
    p.add_argument("--cooldown-seconds", type=float, default=15.0, help="Min gap after a call")
    p.add_argument("--confirm-seconds", type=float, default=2.0, help="Confirm after posture flip")
    p.add_argument("--motion-threshold", type=float, default=8.0, help="Frame-diff mean to trigger")
    p.add_argument("--poll-ms", type=int, default=500, help="Local loop interval (ms)")
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    p.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE,
        help=f"Longest JPEG side for Jev (default {DEFAULT_MAX_SIDE}, min ~280)",
    )
    p.add_argument("--model", type=str, default="jev-latest", help="TypeSafe model id")
    p.add_argument("--sit-warn-minutes", type=float, default=30.0, help="Notify after sitting this long")
    p.add_argument("--stand-warn-minutes", type=float, default=45.0, help="Notify after standing this long")
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logs (motion scores, skips, cooldowns)",
    )
    p.add_argument(
        "--log-file",
        nargs="?",
        const=str(DEFAULT_LOG),
        default=str(DEFAULT_LOG),
        help=f"Also write logs to a file (default: {DEFAULT_LOG}). Pass empty to disable: --log-file ''",
    )


@dataclass
class StandingState:
    posture: str
    tracking: bool
    stand_ups: int
    standing_seconds_today: float
    sitting_seconds_today: float
    standing_streak_seconds: float
    sitting_streak_seconds: float
    api_calls: int
    input_tokens: int
    estimated_cost_usd: float
    last_error: str | None
    has_api_key: bool
    has_standing_cal: bool
    has_sitting_cal: bool
    suggestions_enabled: bool
    sit_warn_minutes: float
    stand_warn_minutes: float
    calibration_label: str
    status_title: str
    bar_title: str
    bar_symbol: str
    usage_label: str
    history: list[dict[str, Any]]
    history_label: str
    strava_connected: bool
    strava_configured: bool
    strava_label: str
    strava_ui_enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StandingCore:
    """Camera + Jev + tracker. Emits state/notify via callbacks (no UI imports)."""

    def __init__(
        self,
        args: argparse.Namespace,
        log_path: Path | None,
        *,
        on_state: StateFn | None = None,
        on_notify: NotifyFn | None = None,
    ) -> None:
        self.args = args
        self.log = get_logger()
        self.log_path = log_path
        self._on_state = on_state
        self._on_notify = on_notify
        DATA.mkdir(parents=True, exist_ok=True)

        api_key = get_api_key()
        self.tracker = StandingTracker(STATS_PATH, HISTORY_PATH)
        self.motion = MotionGate(threshold=args.motion_threshold)
        self.camera = Camera(device_index=args.camera, max_side=args.max_side)
        self.jev = JevPostureClient(
            model=args.model,
            api_key=api_key,
            standing_example=STANDING_CAL if STANDING_CAL.is_file() else None,
            sitting_example=SITTING_CAL if SITTING_CAL.is_file() else None,
        )
        self.suggestions = SuggestionEngine(
            sit_warn_minutes=args.sit_warn_minutes,
            stand_warn_minutes=args.stand_warn_minutes,
        )

        self._stop = threading.Event()
        self._loop_thread: threading.Thread | None = None
        self._pulse_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self._last_api_at = 0.0
        self._pending_confirm_at: float | None = None
        self._pending_strava_seconds: float | None = None
        self._force_next = False
        self._last_skip_log_at = 0.0
        self._camera_down = False
        self._camera_backoff_s = 2.0

        self.log.info(
            "Ready (model=%s, max_side=%s, idle=%ss, sit_warn=%sm, stand_warn=%sm, key=%s)",
            args.model,
            args.max_side,
            args.idle_seconds,
            args.sit_warn_minutes,
            args.stand_warn_minutes,
            "yes" if api_key else "missing",
        )

    def set_callbacks(
        self,
        *,
        on_state: StateFn | None = None,
        on_notify: NotifyFn | None = None,
    ) -> None:
        if on_state is not None:
            self._on_state = on_state
        if on_notify is not None:
            self._on_notify = on_notify

    def notify(self, title: str, message: str) -> None:
        if self._on_notify:
            self._on_notify(title, message)

    def publish_state(self) -> StandingState:
        state = self.snapshot_state()
        if self._on_state:
            self._on_state(state.as_dict())
        return state

    def snapshot_state(self) -> StandingState:
        snap = self.tracker.snapshot()
        has_standing = STANDING_CAL.is_file()
        has_sitting = SITTING_CAL.is_file()
        has_key = bool(get_api_key())
        cal = calibration_label(has_standing=has_standing, has_sitting=has_sitting)

        if snap.last_error:
            status = f"Error: {snap.last_error[:48]}"
            bar_title = ""
            symbol = "exclamationmark.triangle"
        elif not snap.tracking:
            status = "Paused" if has_key else "Needs setup"
            bar_title = ""
            symbol = "pause.circle"
        elif snap.posture == "standing":
            streak = format_duration(snap.standing_streak_seconds)
            status = f"Standing · {streak} streak"
            bar_title = streak
            symbol = "figure.stand"
        elif snap.posture == "sitting":
            streak = format_duration(snap.sitting_streak_seconds)
            status = f"Sitting · {streak} streak"
            bar_title = streak
            symbol = "figure.seated.side.right"
        elif snap.posture == "away":
            status = "Away"
            bar_title = ""
            symbol = "person.slash"
        else:
            status = "Checking posture…"
            bar_title = "…"
            symbol = "ellipsis.circle"

        return StandingState(
            posture=snap.posture,
            tracking=snap.tracking,
            stand_ups=snap.stand_ups,
            standing_seconds_today=snap.standing_seconds_today,
            sitting_seconds_today=snap.sitting_seconds_today,
            standing_streak_seconds=snap.standing_streak_seconds,
            sitting_streak_seconds=snap.sitting_streak_seconds,
            api_calls=snap.api_calls,
            input_tokens=snap.input_tokens,
            estimated_cost_usd=snap.estimated_cost_usd,
            last_error=snap.last_error,
            has_api_key=has_key,
            has_standing_cal=has_standing,
            has_sitting_cal=has_sitting,
            suggestions_enabled=self.suggestions.enabled,
            sit_warn_minutes=self.suggestions.sit_warn_minutes,
            stand_warn_minutes=self.suggestions.stand_warn_minutes,
            calibration_label=cal,
            status_title=status,
            bar_title=bar_title,
            bar_symbol=symbol,
            usage_label=(
                f"{snap.api_calls} calls · ${snap.estimated_cost_usd:.4f} · "
                f"{snap.input_tokens} tokens"
            ),
            history=self.tracker.history_entries(),
            history_label=self.tracker.history_label(),
            strava_connected=strava_api.feature_enabled() and strava_api.is_connected(),
            strava_configured=strava_api.feature_enabled()
            and strava_api.has_app_credentials(),
            strava_label=(
                strava_api.connection_label()
                if strava_api.feature_enabled()
                else "Hidden"
            ),
            strava_ui_enabled=strava_api.feature_enabled(),
        )

    def start_pulse(self, interval: float = 0.5) -> None:
        if self._pulse_thread and self._pulse_thread.is_alive():
            return

        def _pulse() -> None:
            while not self._stop.is_set():
                with self._lock:
                    self.tracker.tick()
                    self.publish_state()
                    self._maybe_suggest()
                time.sleep(interval)

        self._pulse_thread = threading.Thread(target=_pulse, name="standing-pulse", daemon=True)
        self._pulse_thread.start()

    def toggle_tracking(self) -> dict[str, Any]:
        with self._lock:
            enabling = not self.tracker.tracking
        if enabling:
            return self.set_tracking(True)
        return self.set_tracking(False)

    def set_tracking(self, enabled: bool) -> dict[str, Any]:
        need_key = False
        ended_standing: float | None = None
        with self._lock:
            if enabled and not get_api_key():
                self.log.warning("Start blocked — set TypeSafe API key first")
                need_key = True
                self.publish_state()
            else:
                if not enabled and self.tracker.tracking:
                    if self.tracker.posture == "standing":
                        ended_standing = self.tracker.standing_streak_seconds()
                    elif self._pending_strava_seconds is not None:
                        ended_standing = self._pending_strava_seconds
                    self._pending_strava_seconds = None
                self.tracker.set_tracking(enabled)
                if enabled:
                    self.log.info("Tracking started")
                    self._force_next = True
                    self._pending_confirm_at = None
                    self._pending_strava_seconds = None
                    self.motion.reset()
                    self._ensure_loop()
                else:
                    self.log.info("Tracking paused")
                self.publish_state()
        if ended_standing is not None:
            self._maybe_push_strava(ended_standing)
        if need_key:
            self.notify("API key needed", "Open Settings… to add your TypeSafe key.")
            return {"ok": False, "error": "api_key_required"}
        return {"ok": True, "tracking": enabled}

    def connect_strava(self) -> dict[str, Any]:
        """Run browser OAuth (blocks until done or timeout). Prefer calling from a UI thread."""
        if not strava_api.feature_enabled():
            return {"ok": False, "error": "strava_hidden"}
        try:
            tokens = strava_api.authorize_interactive()
            with self._lock:
                self.publish_state()
            name = tokens.athlete_name or "Strava"
            self.log.info("Strava connected (%s)", name)
            self.notify("Strava connected", f"Standing sessions will upload for {name}.")
            return {"ok": True, "athlete": tokens.athlete_name}
        except strava_api.StravaConfigError as exc:
            self.log.warning("Strava config: %s", exc)
            self.notify("Strava setup needed", str(exc)[:160])
            return {"ok": False, "error": str(exc)}
        except strava_api.StravaAuthError as exc:
            self.log.warning("Strava auth failed: %s", exc)
            self.notify("Strava connection failed", str(exc)[:120])
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Strava connect failed")
            self.notify("Strava connection failed", str(exc)[:120])
            return {"ok": False, "error": str(exc)}

    def disconnect_strava(self) -> dict[str, Any]:
        strava_api.clear_tokens()
        with self._lock:
            self.publish_state()
        self.log.info("Strava disconnected")
        self.notify("Strava disconnected", "Tokens removed from Keychain.")
        return {"ok": True}

    def _maybe_push_strava(self, elapsed_seconds: float) -> None:
        if not strava_api.feature_enabled() or not strava_api.is_connected():
            return
        minimum = strava_api.min_standing_seconds()
        if elapsed_seconds < minimum:
            self.log.debug(
                "Skip Strava upload (%.0fs < min %.0fs)",
                elapsed_seconds,
                minimum,
            )
            return
        stand_ups = self.tracker.stats.stand_ups

        def _upload() -> None:
            try:
                strava_api.create_standing_activity(
                    elapsed_seconds=elapsed_seconds,
                    stand_ups_note=stand_ups,
                )
                mins = int(elapsed_seconds // 60)
                self.notify("Logged to Strava", f"Standing desk · {mins}m")
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Strava upload failed")
                self.notify("Strava upload failed", str(exc)[:120])

        threading.Thread(target=_upload, name="strava-upload", daemon=True).start()

    def reset_day(self) -> dict[str, Any]:
        with self._lock:
            self.tracker.reset_day()
            self.publish_state()
        self.log.info("Day stats reset")
        self.notify("Day reset", "Stand-ups and standing time cleared for today.")
        return {"ok": True}

    def toggle_suggestions(self) -> dict[str, Any]:
        return self.set_suggestions(not self.suggestions.enabled)

    def set_suggestions(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self.suggestions.set_enabled(enabled)
            self.publish_state()
        self.log.info("Suggestions %s", "enabled" if enabled else "disabled")
        self.notify(
            "Suggestions",
            "Standing nudges on." if enabled else "Standing nudges off.",
        )
        return {"ok": True, "enabled": enabled}

    def apply_thresholds(self, sit_warn_minutes: float, stand_warn_minutes: float) -> dict[str, Any]:
        sit = max(1.0, float(sit_warn_minutes))
        stand = max(1.0, float(stand_warn_minutes))
        with self._lock:
            self.suggestions.sit_warn_minutes = sit
            self.suggestions.stand_warn_minutes = stand
            self.args.sit_warn_minutes = sit
            self.args.stand_warn_minutes = stand
            self.publish_state()
        self.log.info("Thresholds updated sit=%sm stand=%sm", sit, stand)
        self.notify("Thresholds saved", f"Sit {sit:.0f}m · Stand {stand:.0f}m")
        return {"ok": True}

    def save_api_key(self, text: str) -> dict[str, Any]:
        try:
            set_api_key(text)
            with self._lock:
                self.jev.set_api_key(text)
                self.publish_state()
            self.log.info("API key saved to Keychain")
            self.notify("API key saved", "Stored securely in your macOS Keychain.")
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Failed to save API key")
            self.notify("Could not save key", str(exc)[:120])
            return {"ok": False, "error": str(exc)}

    def clear_api_key(self) -> dict[str, Any]:
        clear_api_key()
        with self._lock:
            if self.tracker.tracking:
                self.tracker.set_tracking(False)
            self.jev.set_api_key(None)
            self.publish_state()
        self.log.info("API key cleared from Keychain")
        self.notify("API key cleared", "Tracking paused. Set a new key to continue.")
        return {"ok": True}

    def calibrate(self, posture: str) -> dict[str, Any]:
        if posture not in ("standing", "sitting"):
            return {"ok": False, "error": "invalid_posture"}
        path = STANDING_CAL if posture == "standing" else SITTING_CAL
        try:
            self.camera.open()
            frame = self.camera.grab()
            path.write_bytes(frame.jpeg_bytes)
            with self._lock:
                self.jev.set_examples(
                    standing_example=STANDING_CAL if STANDING_CAL.is_file() else None,
                    sitting_example=SITTING_CAL if SITTING_CAL.is_file() else None,
                )
                if self.tracker.tracking:
                    self._force_next = True
                self.publish_state()
            self.log.info("Calibrated %s → %s (%d bytes)", posture, path, len(frame.jpeg_bytes))
            self.notify(
                f"{posture.capitalize()} calibrated",
                "Saved a reference photo. Calibrate both postures for best accuracy.",
            )
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Calibration failed (%s)", posture)
            with self._lock:
                self.tracker.set_error(str(exc))
                self.publish_state()
            self.notify("Calibration failed", str(exc)[:120])
            return {"ok": False, "error": str(exc)}

    def clear_calibration(self) -> dict[str, Any]:
        for path in (STANDING_CAL, SITTING_CAL):
            if path.exists():
                path.unlink()
        with self._lock:
            self.jev.set_examples(standing_example=None, sitting_example=None)
            self.publish_state()
        self.log.info("Calibration photos cleared")
        self.notify("Calibration cleared", "Posture examples removed.")
        return {"ok": True}

    def open_log(self) -> dict[str, Any]:
        path = self.log_path or DEFAULT_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        subprocess.run(["open", "-R", str(path)], check=False)
        self.log.info("Revealed log in Finder: %s", path)
        return {"ok": True, "path": str(path)}

    def shutdown(self) -> None:
        if self._stop.is_set():
            return
        self.log.info("Shutting down")
        self._stop.set()
        with self._lock:
            if self.tracker.tracking:
                self.tracker.set_tracking(False)
            self.tracker.save()
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=3.0)
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._pulse_thread.join(timeout=2.0)
        self.camera.close()
        self.jev.close()

    def _ensure_loop(self) -> None:
        if self._loop_thread and self._loop_thread.is_alive():
            return
        self._stop.clear()
        self._loop_thread = threading.Thread(target=self._loop, name="standing-loop", daemon=True)
        self._loop_thread.start()
        self.log.debug("Worker loop thread started")

    def _maybe_suggest(self) -> None:
        snap = self.tracker.snapshot()
        tip = self.suggestions.evaluate(snap)
        if tip is None:
            return
        self.log.info("Suggestion [%s]: %s — %s", tip.id, tip.title, tip.message)
        self.notify(tip.title, tip.message)

    def _loop(self) -> None:
        try:
            self.camera.open()
            self.jev.open()
            self.log.info("Camera + Jev client ready")
        except CameraUnavailable as exc:
            self.log.warning("%s — will keep retrying", exc)
            self._camera_down = True
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Failed to open camera/Jev")
            with self._lock:
                self.tracker.set_error(str(exc))
                self.publish_state()
            return

        while not self._stop.is_set():
            try:
                self._tick_once()
                sleep_s = self.args.poll_ms / 1000.0
            except CameraUnavailable as exc:
                sleep_s = self._on_camera_unavailable(exc)
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Loop error: %s", exc)
                with self._lock:
                    self.tracker.set_error(str(exc))
                    self.publish_state()
                sleep_s = max(2.0, self.args.poll_ms / 1000.0)
            time.sleep(sleep_s)

    def _on_camera_unavailable(self, exc: CameraUnavailable) -> float:
        if not self._camera_down:
            self.log.warning("%s Waiting for camera (common after Mac sleep)…", exc)
            self._camera_down = True
            with self._lock:
                self.tracker.set_error("Camera unavailable — waiting for wake")
                self.publish_state()
            self.motion.reset()
        else:
            self.log.debug("Camera still unavailable; retry in %.1fs", self._camera_backoff_s)

        try:
            self.camera.reopen()
            self.camera.grab(retry=False)
            self.log.info("Camera restored after sleep/disconnect")
            self._camera_down = False
            self._camera_backoff_s = 2.0
            with self._lock:
                if self.tracker.last_error and "Camera unavailable" in self.tracker.last_error:
                    self.tracker.last_error = None
                self.motion.reset()
                self._force_next = True
                self.publish_state()
            return self.args.poll_ms / 1000.0
        except CameraUnavailable:
            self._camera_backoff_s = min(15.0, self._camera_backoff_s * 1.5)
            return self._camera_backoff_s

    def _tick_once(self) -> None:
        with self._lock:
            tracking = self.tracker.tracking
        if not tracking:
            return

        frame = self.camera.grab()
        if self._camera_down:
            self.log.info("Camera restored after sleep/disconnect")
            self._camera_down = False
            self._camera_backoff_s = 2.0
            self.motion.reset()
            with self._lock:
                if self.tracker.last_error and "Camera unavailable" in (
                    self.tracker.last_error or ""
                ):
                    self.tracker.last_error = None
                self._force_next = True

        significant, score = self.motion.is_significant(frame.gray_small)
        now = time.monotonic()

        with self._lock:
            self.tracker.set_motion_score(score)
            self.tracker.tick()

            reason: str | None = None
            skip_why: str | None = None
            since_api = now - self._last_api_at
            in_cooldown = self._last_api_at > 0 and since_api < self.args.cooldown_seconds

            if self._force_next:
                reason = "start"
                self._force_next = False
            elif self._pending_confirm_at is not None and now >= self._pending_confirm_at:
                reason = "confirm"
            elif in_cooldown:
                skip_why = f"cooldown ({since_api:.1f}s/{self.args.cooldown_seconds}s)"
            elif significant:
                reason = "motion"
            elif self._last_api_at > 0 and since_api >= self.args.idle_seconds:
                reason = "heartbeat"
            else:
                skip_why = (
                    f"still (motion={score:.1f}<{self.args.motion_threshold}, "
                    f"next heartbeat in {max(0, self.args.idle_seconds - since_api):.0f}s)"
                )

            if reason is None:
                if skip_why and now - self._last_skip_log_at >= 5.0:
                    self.log.debug("Skip API: %s", skip_why)
                    self._last_skip_log_at = now
                return

            jpeg = frame.jpeg_bytes
            prev_posture = self.tracker.posture
            self.log.info(
                "Calling Jev (%s) motion=%.1f prev=%s jpeg=%dB",
                reason,
                score,
                prev_posture,
                len(jpeg),
            )

        try:
            result = self.jev.classify(jpeg)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Jev call failed")
            with self._lock:
                self._last_api_at = time.monotonic()
                self._pending_confirm_at = None
                self.tracker.set_error(str(exc))
                self.publish_state()
            return

        ended_standing: float | None = None
        with self._lock:
            self._last_api_at = time.monotonic()
            if prev_posture == "standing" and result.posture != "standing":
                self._pending_strava_seconds = self.tracker.standing_streak_seconds()
            elif result.posture == "standing":
                self._pending_strava_seconds = None
            self.tracker.set_posture_from_api(
                result.posture,
                input_tokens=result.input_tokens,
                reason=reason or "api",
            )
            flipped = result.posture != prev_posture
            self.log.info(
                "Jev → %s (was %s)%s tokens=%d cost~$%.4f stand_ups=%d",
                result.posture,
                prev_posture,
                " FLIP" if flipped else "",
                result.input_tokens,
                result.estimated_cost_usd,
                self.tracker.stats.stand_ups,
            )

            if reason == "confirm":
                self._pending_confirm_at = None
                # Only upload after the flip is confirmed — avoids false sit detections.
                if (
                    result.posture != "standing"
                    and self._pending_strava_seconds is not None
                ):
                    ended_standing = self._pending_strava_seconds
                    self._pending_strava_seconds = None
            elif flipped and prev_posture != "unknown":
                self._pending_confirm_at = time.monotonic() + self.args.confirm_seconds
                self.log.debug("Scheduled confirm in %.1fs", self.args.confirm_seconds)
            else:
                self._pending_confirm_at = None
            self.publish_state()
        if ended_standing is not None:
            self._maybe_push_strava(ended_standing)
