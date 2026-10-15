"""Strava OAuth + manual activity upload for standing bouts."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import keyring

from src.logging_setup import get_logger

SERVICE = "standing-or-not"
ACCOUNT = "strava_tokens"

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/activities"

# Standing desk sessions map to an indoor Workout.
DEFAULT_SPORT_TYPE = "Workout"
DEFAULT_MIN_SECONDS = 600  # 10 minutes — avoid spamming short posture flips
OAUTH_TIMEOUT_S = 180
CALLBACK_PATH = "/strava/callback"


def feature_enabled() -> bool:
    """Strava UI + uploads are hidden unless STRAVA_UI=1 (shipping not ready)."""
    return os.environ.get("STRAVA_UI", "").strip().lower() in ("1", "true", "yes")


@dataclass
class StravaTokens:
    access_token: str
    refresh_token: str
    expires_at: int  # unix seconds
    athlete_name: str = ""

    def expired(self, *, skew_s: int = 60) -> bool:
        return time.time() >= (self.expires_at - skew_s)

    def as_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "athlete_name": self.athlete_name,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StravaTokens:
        return cls(
            access_token=str(raw["access_token"]),
            refresh_token=str(raw["refresh_token"]),
            expires_at=int(raw["expires_at"]),
            athlete_name=str(raw.get("athlete_name") or ""),
        )


class StravaConfigError(RuntimeError):
    """Missing client id/secret or incomplete OAuth setup."""


class StravaAuthError(RuntimeError):
    """User cancelled OAuth or Strava rejected the request."""


def client_id() -> str | None:
    value = os.environ.get("STRAVA_CLIENT_ID", "").strip()
    return value or None


def client_secret() -> str | None:
    value = os.environ.get("STRAVA_CLIENT_SECRET", "").strip()
    return value or None


def min_standing_seconds() -> float:
    raw = os.environ.get("STRAVA_MIN_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_MIN_SECONDS)
    try:
        return max(60.0, float(raw))
    except ValueError:
        return float(DEFAULT_MIN_SECONDS)


def has_app_credentials() -> bool:
    return bool(client_id() and client_secret())


def load_tokens() -> StravaTokens | None:
    try:
        stored = keyring.get_password(SERVICE, ACCOUNT)
    except keyring.errors.KeyringError:
        return None
    if not stored:
        return None
    try:
        return StravaTokens.from_dict(json.loads(stored))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_tokens(tokens: StravaTokens) -> None:
    keyring.set_password(SERVICE, ACCOUNT, json.dumps(tokens.as_dict()))


def clear_tokens() -> None:
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass


def is_connected() -> bool:
    return load_tokens() is not None


def connection_label() -> str:
    if not has_app_credentials():
        return "Add STRAVA_CLIENT_ID / SECRET to .env"
    tokens = load_tokens()
    if tokens is None:
        return "Not connected"
    if tokens.athlete_name:
        return f"Connected as {tokens.athlete_name}"
    return "Connected"


def _form_post(url: str, fields: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = urllib.parse.urlencode({k: v for k, v in fields.items() if v is not None}).encode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise StravaAuthError(f"Strava HTTP {exc.code}: {detail}") from exc


def _athlete_display(athlete: dict[str, Any] | None) -> str:
    if not athlete:
        return ""
    first = str(athlete.get("firstname") or "").strip()
    last = str(athlete.get("lastname") or "").strip()
    name = f"{first} {last}".strip()
    return name or str(athlete.get("username") or "").strip()


def _tokens_from_response(payload: dict[str, Any], *, fallback_name: str = "") -> StravaTokens:
    return StravaTokens(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=int(payload["expires_at"]),
        athlete_name=_athlete_display(payload.get("athlete")) or fallback_name,
    )


def refresh_access_token(tokens: StravaTokens | None = None) -> StravaTokens:
    secret = client_secret()
    cid = client_id()
    if not secret or not cid:
        raise StravaConfigError("STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET are required")
    current = tokens or load_tokens()
    if current is None:
        raise StravaAuthError("Not connected to Strava")
    if not current.expired():
        return current
    payload = _form_post(
        TOKEN_URL,
        {
            "client_id": cid,
            "client_secret": secret,
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token,
        },
    )
    refreshed = _tokens_from_response(payload, fallback_name=current.athlete_name)
    save_tokens(refreshed)
    return refreshed


def authorize_interactive(*, timeout_s: float = OAUTH_TIMEOUT_S) -> StravaTokens:
    """Open the browser for Strava OAuth and wait for the localhost callback."""
    cid = client_id()
    secret = client_secret()
    if not cid or not secret:
        raise StravaConfigError(
            "Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env "
            "(create an app at https://www.strava.com/settings/api — callback domain: localhost)"
        )

    result: dict[str, Any] = {"code": None, "error": None, "done": threading.Event()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("error"):
                result["error"] = qs["error"][0]
            elif qs.get("code"):
                result["code"] = qs["code"][0]
            else:
                result["error"] = "missing_code"
            body = (
                b"<html><body><h2>Standing connected</h2>"
                b"<p>You can close this tab and return to the app.</p></body></html>"
                if result["code"]
                else b"<html><body><h2>Authorization failed</h2>"
                b"<p>You can close this tab.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            result["done"].set()

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}{CALLBACK_PATH}"
    params = urllib.parse.urlencode(
        {
            "client_id": cid,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "approval_prompt": "auto",
            "scope": "activity:write,read",
        }
    )
    auth_url = f"{AUTHORIZE_URL}?{params}"

    thread = threading.Thread(target=server.handle_request, name="strava-oauth", daemon=True)
    thread.start()
    webbrowser.open(auth_url)

    if not result["done"].wait(timeout=timeout_s):
        try:
            server.server_close()
        except OSError:
            pass
        raise StravaAuthError("Timed out waiting for Strava authorization")

    thread.join(timeout=2.0)
    try:
        server.server_close()
    except OSError:
        pass

    if result["error"]:
        raise StravaAuthError(f"Strava authorization denied: {result['error']}")
    code = result["code"]
    if not code:
        raise StravaAuthError("No authorization code returned")

    payload = _form_post(
        TOKEN_URL,
        {
            "client_id": cid,
            "client_secret": secret,
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    tokens = _tokens_from_response(payload)
    save_tokens(tokens)
    return tokens


def create_standing_activity(
    *,
    elapsed_seconds: float,
    ended_at: datetime | None = None,
    stand_ups_note: int | None = None,
) -> dict[str, Any]:
    """Upload a manual indoor Workout for a completed standing bout."""
    elapsed = int(round(elapsed_seconds))
    if elapsed < 60:
        raise ValueError("Standing bout too short to upload")

    tokens = refresh_access_token()
    end = ended_at or datetime.now().astimezone()
    start = end - timedelta(seconds=elapsed)
    # Strava wants local wall time without timezone offset for start_date_local.
    start_local = start.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")

    minutes = elapsed // 60
    description_parts = [
        "Logged by Standing (AI-based standing tracker).",
        f"Stood for {minutes} minute{'s' if minutes != 1 else ''}.",
    ]
    if stand_ups_note is not None:
        description_parts.append(f"Stand-ups today: {stand_ups_note}.")

    payload = _form_post(
        ACTIVITIES_URL,
        {
            "name": f"Standing desk · {minutes}m",
            "sport_type": DEFAULT_SPORT_TYPE,
            "start_date_local": start_local,
            "elapsed_time": elapsed,
            "description": " ".join(description_parts),
            "trainer": 1,
        },
        token=tokens.access_token,
    )
    get_logger().info(
        "Strava activity created id=%s elapsed=%ss",
        payload.get("id"),
        elapsed,
    )
    return payload
