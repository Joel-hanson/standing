"""Headless JSON-lines worker for the SwiftUI shell.

Protocol (one JSON object per line):
  Swift → Python (stdin):  {"cmd":"...", "id":1, ...}
  Python → Swift (stdout): {"event":"state"|"notify"|"ready"|"ack"|"error", ...}

Logs always go to stderr / log file — never stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any, TextIO

from dotenv import load_dotenv

from src.core import ROOT, StandingCore, add_common_args
from src.credentials import has_keychain_key, get_api_key
from src.logging_setup import get_logger, setup_logging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Standing AI standing tracker — IPC worker for SwiftUI shell")
    add_common_args(p)
    return p.parse_args(argv)


class WorkerBridge:
    def __init__(self, core: StandingCore, out: TextIO) -> None:
        self.core = core
        self.out = out
        self._write_lock = threading.Lock()
        self.log = get_logger()

    def emit(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        with self._write_lock:
            self.out.write(line + "\n")
            self.out.flush()

    def on_state(self, state: dict[str, Any]) -> None:
        self.emit({"event": "state", "state": state})

    def on_notify(self, title: str, message: str) -> None:
        self.emit({"event": "notify", "title": title, "message": message})

    def handle(self, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        req_id = msg.get("id")
        result: dict[str, Any]

        try:
            if cmd == "ping":
                result = {"ok": True, "pong": True}
            elif cmd == "get_state":
                state = self.core.publish_state()
                result = {"ok": True, "state": state.as_dict()}
            elif cmd == "toggle_tracking":
                result = self.core.toggle_tracking()
            elif cmd == "set_tracking":
                result = self.core.set_tracking(bool(msg.get("enabled")))
            elif cmd == "reset_day":
                result = self.core.reset_day()
            elif cmd == "toggle_suggestions":
                result = self.core.toggle_suggestions()
            elif cmd == "set_suggestions":
                result = self.core.set_suggestions(bool(msg.get("enabled")))
            elif cmd == "apply_thresholds":
                result = self.core.apply_thresholds(
                    float(msg.get("sit_warn_minutes", 30)),
                    float(msg.get("stand_warn_minutes", 45)),
                )
            elif cmd == "save_api_key":
                key = str(msg.get("key") or "")
                result = self.core.save_api_key(key)
            elif cmd == "clear_api_key":
                result = self.core.clear_api_key()
            elif cmd == "calibrate":
                result = self.core.calibrate(str(msg.get("posture") or ""))
            elif cmd == "clear_calibration":
                result = self.core.clear_calibration()
            elif cmd == "open_log":
                result = self.core.open_log()
            elif cmd == "connect_strava":
                result = self.core.connect_strava()
            elif cmd == "disconnect_strava":
                result = self.core.disconnect_strava()
            elif cmd == "shutdown":
                result = {"ok": True}
                self.emit({"event": "ack", "id": req_id, **result})
                return
            else:
                result = {"ok": False, "error": f"unknown_cmd:{cmd}"}
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Command failed: %s", cmd)
            result = {"ok": False, "error": str(exc)}

        ack: dict[str, Any] = {"event": "ack", "id": req_id, **result}
        self.emit(ack)


def run_worker(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args(argv)

    log_path: Path | None = None
    if args.log_file:
        log_path = Path(args.log_file).expanduser()
    # Worker: never log to stdout (IPC channel).
    setup_logging(verbose=args.verbose, log_file=log_path, stream=sys.stderr)

    log = get_logger()
    key = get_api_key()
    key_src = "Keychain" if has_keychain_key() else (".env/env" if key else "missing")
    log.info("Worker starting (API key: %s)", key_src)

    bridge: WorkerBridge | None = None

    def on_state(state: dict[str, Any]) -> None:
        if bridge:
            bridge.on_state(state)

    def on_notify(title: str, message: str) -> None:
        if bridge:
            bridge.on_notify(title, message)

    core = StandingCore(args, log_path, on_state=on_state, on_notify=on_notify)
    bridge = WorkerBridge(core, sys.stdout)
    core.start_pulse(0.5)

    bridge.emit({"event": "ready", "version": 1, "root": str(ROOT)})
    core.publish_state()

    try:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                bridge.emit({"event": "error", "message": f"bad_json:{exc}"})
                continue
            if not isinstance(msg, dict):
                bridge.emit({"event": "error", "message": "expected_object"})
                continue
            bridge.handle(msg)
            if msg.get("cmd") == "shutdown":
                break
    except KeyboardInterrupt:
        log.info("Worker interrupted")
    finally:
        core.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_worker(argv)


if __name__ == "__main__":
    raise SystemExit(main())
