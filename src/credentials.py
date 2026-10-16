"""TypeSafe API key: macOS Keychain first, then .env / environment.

The SwiftUI shell owns Keychain for release builds and sets
STANDING_DISABLE_KEYRING=1 so the helper never opens Keychain (avoids
macOS prompts that blame python3.12). Dev / rumps still use keyring.
"""

from __future__ import annotations

import os

import keyring

SERVICE = "Standing"
_LEGACY_SERVICE = "standing-or-not"
ACCOUNT = "typesafe_api_key"


def _keyring_enabled() -> bool:
    flag = os.environ.get("STANDING_DISABLE_KEYRING", "").strip().lower()
    return flag not in {"1", "true", "yes", "on"}


def get_api_key() -> str | None:
    """Return the API key from Keychain (when enabled), then TYPESAFE_API_KEY env."""
    if _keyring_enabled():
        try:
            stored = keyring.get_password(SERVICE, ACCOUNT)
        except keyring.errors.KeyringError:
            stored = None
        if stored and stored.strip():
            return stored.strip()

        # One-time migrate from the old Keychain service name.
        try:
            legacy = keyring.get_password(_LEGACY_SERVICE, ACCOUNT)
        except keyring.errors.KeyringError:
            legacy = None
        if legacy and legacy.strip():
            cleaned = legacy.strip()
            try:
                keyring.set_password(SERVICE, ACCOUNT, cleaned)
                keyring.delete_password(_LEGACY_SERVICE, ACCOUNT)
            except keyring.errors.KeyringError:
                pass
            os.environ["TYPESAFE_API_KEY"] = cleaned
            return cleaned

    env = os.environ.get("TYPESAFE_API_KEY", "").strip()
    return env or None


def set_api_key(key: str) -> None:
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("API key cannot be empty")
    if _keyring_enabled():
        keyring.set_password(SERVICE, ACCOUNT, cleaned)
    # Keep process env in sync for the running session.
    os.environ["TYPESAFE_API_KEY"] = cleaned


def clear_api_key() -> None:
    if _keyring_enabled():
        for service in (SERVICE, _LEGACY_SERVICE):
            try:
                keyring.delete_password(service, ACCOUNT)
            except keyring.errors.PasswordDeleteError:
                pass
    os.environ.pop("TYPESAFE_API_KEY", None)


def has_keychain_key() -> bool:
    if not _keyring_enabled():
        return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
    for service in (SERVICE, _LEGACY_SERVICE):
        try:
            stored = keyring.get_password(service, ACCOUNT)
        except keyring.errors.KeyringError:
            continue
        if stored and stored.strip():
            return True
    return False
