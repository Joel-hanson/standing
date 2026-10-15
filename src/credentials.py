"""TypeSafe API key: macOS Keychain first, then .env / environment."""

from __future__ import annotations

import os

import keyring

SERVICE = "Standing"
_LEGACY_SERVICE = "standing-or-not"
ACCOUNT = "typesafe_api_key"


def get_api_key() -> str | None:
    """Return the API key from Keychain, then TYPESAFE_API_KEY env."""
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
    keyring.set_password(SERVICE, ACCOUNT, cleaned)
    # Keep process env in sync for the running session.
    os.environ["TYPESAFE_API_KEY"] = cleaned


def clear_api_key() -> None:
    for service in (SERVICE, _LEGACY_SERVICE):
        try:
            keyring.delete_password(service, ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            pass
    os.environ.pop("TYPESAFE_API_KEY", None)


def has_keychain_key() -> bool:
    for service in (SERVICE, _LEGACY_SERVICE):
        try:
            stored = keyring.get_password(service, ACCOUNT)
        except keyring.errors.KeyringError:
            continue
        if stored and stored.strip():
            return True
    return False
