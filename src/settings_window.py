"""Native AppKit Settings panel for Standing (AI-based standing tracker)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from AppKit import (
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSButtonTypeMomentaryPushIn,
    NSButtonTypeSwitch,
    NSColor,
    NSFont,
    NSMakeRect,
    NSSecureTextField,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
import objc
import webbrowser

from src.support import open_support, support_menu_title

TYPESAFE_CONSOLE_URL = "https://console.typesafe.ai"


@dataclass
class SettingsSnapshot:
    has_api_key: bool
    suggestions_enabled: bool
    calibration_label: str
    usage_label: str
    history_label: str
    sit_warn_minutes: float
    stand_warn_minutes: float


def _label(text: str, *, bold: bool = False, secondary: bool = False) -> NSTextField:
    field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 17))
    field.setStringValue_(text)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setFont_(
        NSFont.boldSystemFontOfSize_(13.0) if bold else NSFont.systemFontOfSize_(13.0)
    )
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
        field.setFont_(NSFont.systemFontOfSize_(12.0))
    return field


def _group_box(frame) -> NSView:
    """Rounded inset group, similar to System Settings rows."""
    box = NSView.alloc().initWithFrame_(frame)
    box.setWantsLayer_(True)
    layer = box.layer()
    layer.setCornerRadius_(10.0)
    layer.setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
    return box


class _SettingsController(NSObject):
    """Owns the Settings window and routes button actions."""

    def initWithCallbacks_(self, callbacks: dict) -> _SettingsController | None:  # noqa: N802
        self = objc.super(_SettingsController, self).init()
        if self is None:
            return None
        self._callbacks = callbacks
        self._window: NSWindow | None = None
        self._key_field: NSSecureTextField | None = None
        self._status_key: NSTextField | None = None
        self._status_cal: NSTextField | None = None
        self._status_usage: NSTextField | None = None
        self._status_history: NSTextField | None = None
        self._suggestions_btn: NSButton | None = None
        self._sit_field: NSTextField | None = None
        self._stand_field: NSTextField | None = None
        self._save_btn: NSButton | None = None
        return self

    def show_(self, snap: SettingsSnapshot) -> None:  # noqa: N802
        if self._window is None:
            self._build()
        self.refresh_(snap)
        assert self._window is not None
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()

    def refresh_(self, snap: SettingsSnapshot) -> None:  # noqa: N802
        if self._status_key is not None:
            self._status_key.setStringValue_(
                "Saved in Keychain" if snap.has_api_key else "Not set — paste a key below"
            )
        if self._key_field is not None:
            self._key_field.setPlaceholderString_(
                "Paste new key to replace" if snap.has_api_key else "Paste TypeSafe AI API key"
            )
        if self._status_cal is not None:
            cal = snap.calibration_label
            if cal.startswith("Calibration: "):
                cal = cal.removeprefix("Calibration: ")
            self._status_cal.setStringValue_(cal)
        if self._status_usage is not None:
            self._status_usage.setStringValue_(snap.usage_label)
        if self._status_history is not None:
            self._status_history.setStringValue_(snap.history_label)
        if self._suggestions_btn is not None:
            self._suggestions_btn.setState_(1 if snap.suggestions_enabled else 0)
        if self._sit_field is not None:
            self._sit_field.setStringValue_(str(int(snap.sit_warn_minutes)))
        if self._stand_field is not None:
            self._stand_field.setStringValue_(str(int(snap.stand_warn_minutes)))
        self._sync_save_enabled()

    def _sync_save_enabled(self) -> None:
        if self._save_btn is None or self._key_field is None:
            return
        has_text = bool((self._key_field.stringValue() or "").strip())
        self._save_btn.setEnabled_(has_text)

    def controlTextDidChange_(self, _notification) -> None:  # noqa: N802
        self._sync_save_enabled()

    def _build(self) -> None:
        # Compact preference pane — fixed width so rows don’t stretch.
        # Base layout + Support section (~90px with title).
        width, height = 400, 646 + 90
        margin = 18
        inner = width - margin * 2
        pad = 12
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, height),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("Standing · AI standing tracker")
        window.center()
        window.setReleasedWhenClosed_(False)
        window.setBackgroundColor_(NSColor.windowBackgroundColor())

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        y = height - 16

        def section_title(title: str) -> None:
            nonlocal y
            field = _label(title, bold=True, secondary=True)
            field.setFrame_(NSMakeRect(margin + 4, y - 14, inner, 14))
            field.setFont_(NSFont.boldSystemFontOfSize_(11.0))
            content.addSubview_(field)
            y -= 18

        def push_button(title: str, action: str, *, x: float, w: float, parent: NSView, by: float) -> NSButton:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, by, w, 24))
            btn.setTitle_(title)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setButtonType_(NSButtonTypeMomentaryPushIn)
            btn.setTarget_(self)
            btn.setAction_(action)
            parent.addSubview_(btn)
            return btn

        # ── Support (one-time; nothing is locked) ─────────────────
        section_title("Support")
        support_h = 72
        y -= support_h
        support = _group_box(NSMakeRect(margin, y, inner, support_h))
        content.addSubview_(support)

        support_blurb = _label(
            "Standing is free. One-time support helps keep it going.",
            secondary=True,
        )
        support_blurb.setFrame_(NSMakeRect(pad, support_h - 28, inner - pad * 2, 17))
        support.addSubview_(support_blurb)
        push_button(
            support_menu_title(),
            "openSupport:",
            x=pad,
            w=200,
            parent=support,
            by=12,
        )
        y -= 12

        # ── Account ──────────────────────────────────────────────
        section_title("Account")
        account_h = 126
        y -= account_h
        account = _group_box(NSMakeRect(margin, y, inner, account_h))
        content.addSubview_(account)

        api_lab = _label("AI API key")
        api_lab.setFrame_(NSMakeRect(pad, account_h - 28, 96, 17))
        account.addSubview_(api_lab)

        self._status_key = _label("…", secondary=True)
        self._status_key.setAlignment_(NSTextAlignmentRight)
        self._status_key.setFrame_(NSMakeRect(pad + 96, account_h - 28, inner - pad * 2 - 96, 17))
        account.addSubview_(self._status_key)

        self._key_field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(pad, account_h - 54, inner - pad * 2, 24)
        )
        self._key_field.setPlaceholderString_("Paste TypeSafe AI API key")
        self._key_field.setDelegate_(self)
        account.addSubview_(self._key_field)

        self._save_btn = push_button(
            "Save AI key", "saveKey:", x=pad, w=110, parent=account, by=36
        )
        self._save_btn.setEnabled_(False)
        push_button("Clear key", "clearKey:", x=pad + 126, w=88, parent=account, by=36)
        push_button(
            "Get a TypeSafe API key…",
            "openTypeSafeConsole:",
            x=pad,
            w=188,
            parent=account,
            by=8,
        )

        y -= 12

        # ── Standing nudges ──────────────────────────────────────
        section_title("Standing nudges")
        coach_h = 96
        y -= coach_h
        coach = _group_box(NSMakeRect(margin, y, inner, coach_h))
        content.addSubview_(coach)

        tip_lab = _label("Suggestions & posture tips")
        tip_lab.setFrame_(NSMakeRect(pad, coach_h - 28, inner - pad * 2 - 56, 17))
        coach.addSubview_(tip_lab)

        self._suggestions_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(inner - pad - 42, coach_h - 32, 42, 24)
        )
        self._suggestions_btn.setButtonType_(NSButtonTypeSwitch)
        self._suggestions_btn.setTitle_("")
        self._suggestions_btn.setTarget_(self)
        self._suggestions_btn.setAction_("toggleSuggestions:")
        coach.addSubview_(self._suggestions_btn)

        def minute_row(parent: NSView, label: str, top: float) -> NSTextField:
            lab = _label(label)
            lab.setFrame_(NSMakeRect(pad, top, 200, 17))
            parent.addSubview_(lab)

            field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(inner - pad - 78, top - 3, 44, 22)
            )
            field.setAlignment_(NSTextAlignmentRight)
            field.setTarget_(self)
            field.setAction_("applyThresholds:")
            parent.addSubview_(field)

            unit = _label("min", secondary=True)
            unit.setFrame_(NSMakeRect(inner - pad - 30, top, 30, 17))
            parent.addSubview_(unit)
            return field

        self._sit_field = minute_row(coach, "Remind after sitting", coach_h - 56)
        self._stand_field = minute_row(coach, "Remind after standing", coach_h - 84)

        y -= 12

        # ── Calibration ──────────────────────────────────────────
        section_title("Calibration")
        cal_h = 88
        y -= cal_h
        cal = _group_box(NSMakeRect(margin, y, inner, cal_h))
        content.addSubview_(cal)

        self._status_cal = _label("…", secondary=True)
        self._status_cal.setFrame_(NSMakeRect(pad, cal_h - 26, inner - pad * 2, 15))
        cal.addSubview_(self._status_cal)

        push_button("Calibrate sitting", "calSit:", x=pad, w=132, parent=cal, by=42)
        push_button("Calibrate standing", "calStand:", x=pad + 140, w=146, parent=cal, by=42)
        push_button("Clear calibration", "clearCal:", x=pad, w=140, parent=cal, by=10)

        # ── Activity history ─────────────────────────────────────
        y -= 12
        section_title("Activity history")
        hist_h = 118
        y -= hist_h
        hist = _group_box(NSMakeRect(margin, y, inner, hist_h))
        content.addSubview_(hist)

        self._status_history = _label("…", secondary=True)
        self._status_history.setFrame_(NSMakeRect(pad, 8, inner - pad * 2, hist_h - 16))
        # Multi-line, top-aligned.
        self._status_history.cell().setWraps_(True)
        self._status_history.setMaximumNumberOfLines_(7)
        hist.addSubview_(self._status_history)

        # ── Usage / Done ─────────────────────────────────────────
        y -= 12
        section_title("Usage today")
        usage_h = 56
        y -= usage_h
        usage = _group_box(NSMakeRect(margin, y, inner, usage_h))
        content.addSubview_(usage)

        self._status_usage = _label("…", secondary=True)
        self._status_usage.setFrame_(NSMakeRect(pad, usage_h - 24, inner - pad * 2, 15))
        usage.addSubview_(self._status_usage)
        push_button("Open log", "openLog:", x=pad, w=80, parent=usage, by=10)
        done = push_button("Done", "close:", x=inner - pad - 72, w=72, parent=usage, by=10)
        done.setKeyEquivalent_("\r")

        window.setContentView_(content)
        self._window = window

    def saveKey_(self, _sender) -> None:  # noqa: N802
        text = ""
        if self._key_field is not None:
            text = (self._key_field.stringValue() or "").strip()
        cb = self._callbacks.get("save_api_key")
        if cb and text:
            cb(text)
            self._key_field.setStringValue_("")
            self._sync_save_enabled()

    def clearKey_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("clear_api_key")
        if cb:
            cb()

    def openTypeSafeConsole_(self, _sender) -> None:  # noqa: N802
        webbrowser.open(TYPESAFE_CONSOLE_URL)

    def openSupport_(self, _sender) -> None:  # noqa: N802
        open_support()

    def toggleSuggestions_(self, sender) -> None:  # noqa: N802
        cb = self._callbacks.get("toggle_suggestions")
        if cb:
            cb(bool(sender.state()))

    def applyThresholds_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("apply_thresholds")
        if not cb:
            return
        try:
            sit = float(self._sit_field.stringValue()) if self._sit_field else 30.0
            stand = float(self._stand_field.stringValue()) if self._stand_field else 45.0
        except ValueError:
            return
        cb(max(1.0, sit), max(1.0, stand))

    def calSit_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("calibrate_sitting")
        if cb:
            cb()

    def calStand_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("calibrate_standing")
        if cb:
            cb()

    def clearCal_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("clear_calibration")
        if cb:
            cb()

    def openLog_(self, _sender) -> None:  # noqa: N802
        cb = self._callbacks.get("open_log")
        if cb:
            cb()

    def close_(self, _sender) -> None:  # noqa: N802
        self.applyThresholds_(None)
        if self._window is not None:
            self._window.orderOut_(None)


class SettingsWindow:
    """Python-facing wrapper around the AppKit Settings panel."""

    def __init__(
        self,
        *,
        on_save_api_key: Callable[[str], None],
        on_clear_api_key: Callable[[], None],
        on_toggle_suggestions: Callable[[bool], None],
        on_apply_thresholds: Callable[[float, float], None],
        on_calibrate_sitting: Callable[[], None],
        on_calibrate_standing: Callable[[], None],
        on_clear_calibration: Callable[[], None],
        on_open_log: Callable[[], None],
    ) -> None:
        self._controller = _SettingsController.alloc().initWithCallbacks_(
            {
                "save_api_key": on_save_api_key,
                "clear_api_key": on_clear_api_key,
                "toggle_suggestions": on_toggle_suggestions,
                "apply_thresholds": on_apply_thresholds,
                "calibrate_sitting": on_calibrate_sitting,
                "calibrate_standing": on_calibrate_standing,
                "clear_calibration": on_clear_calibration,
                "open_log": on_open_log,
            }
        )

    def show(self, snap: SettingsSnapshot) -> None:
        self._controller.show_(snap)

    def refresh(self, snap: SettingsSnapshot) -> None:
        if self._controller._window is not None:  # noqa: SLF001
            self._controller.refresh_(snap)
