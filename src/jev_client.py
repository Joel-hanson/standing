"""Thin TypeSafe / Jev wrapper for posture classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from typesafe_sdk import Choice, Image, TypeSafeClient

Posture = Literal["standing", "sitting", "away"]

# $0.042 per million input tokens (output is free).
PRICE_PER_MTOK = 0.042

# Webcam + standing desk: upper body often looks similar when sitting or standing.
# Criteria lean on relative cues, and optional user calibration photos.
INSTRUCTIONS = (
    "Look at `camera`. This is a laptop/monitor webcam at a height-adjustable "
    "standing desk. Head-and-shoulders framing is common for BOTH sitting and "
    "standing — do NOT default to sitting just because the legs are out of frame. "
    "If calibration example photos are provided in the criteria, match `camera` "
    "to the closest example. Which option fits best right now?"
)

STANDING_DESCRIPTION = (
    "Person is standing upright on their feet (including at a raised standing desk). "
    "Typical webcam cues vs sitting: hips/torso sit higher relative to the desk edge; "
    "forearms angle more steeply down to the keyboard; empty chair or chair pushed "
    "back if visible; face/torso often larger or closer in frame if the camera is "
    "fixed to the monitor."
)

SITTING_DESCRIPTION = (
    "Person is seated in a chair at the desk. Typical webcam cues: shoulders and "
    "head sit lower relative to the monitor/desk; forearms more level with the "
    "desktop; chair back or seat may be visible; more headroom above the person."
)

AWAY_DESCRIPTION = (
    "No person is clearly visible, or posture cannot be determined from the frame."
)


@dataclass
class PostureResult:
    posture: Posture
    input_tokens: int
    estimated_cost_usd: float


@dataclass
class UsageTotals:
    api_calls: int = 0
    input_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return self.input_tokens * PRICE_PER_MTOK / 1_000_000


class JevPostureClient:
    def __init__(
        self,
        model: str = "jev-latest",
        *,
        api_key: str | None = None,
        standing_example: Path | None = None,
        sitting_example: Path | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.standing_example = standing_example
        self.sitting_example = sitting_example
        self.usage = UsageTotals()
        self._client: TypeSafeClient | None = None

    def set_api_key(self, api_key: str | None) -> None:
        self.api_key = api_key
        # Force reconnect with the new key on next classify.
        self.close()

    def open(self) -> None:
        if self._client is None:
            kwargs: dict = {
                "model": self.model,
                "headers": {"TypeSafe-Danger-Zone-Images": "true"},
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = TypeSafeClient(**kwargs)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> JevPostureClient:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def set_examples(
        self,
        *,
        standing_example: Path | None,
        sitting_example: Path | None,
    ) -> None:
        self.standing_example = standing_example
        self.sitting_example = sitting_example

    def classify(self, jpeg_bytes: bytes) -> PostureResult:
        if self._client is None:
            self.open()
        assert self._client is not None

        photo = Image(jpeg_bytes)
        result = self._client.system_one(
            state={"camera": photo},
            questions={
                "posture": Choice(
                    instructions=INSTRUCTIONS,
                    criteria=self._criteria(),
                ),
            },
            extra_headers={"TypeSafe-Danger-Zone-Images": "true"},
        )

        choice = result.choices["posture"].choice
        if choice not in ("standing", "sitting", "away"):
            choice = "away"

        input_tokens = _extract_input_tokens(result)
        self.usage.api_calls += 1
        self.usage.input_tokens += input_tokens

        return PostureResult(
            posture=choice,  # type: ignore[arg-type]
            input_tokens=input_tokens,
            estimated_cost_usd=input_tokens * PRICE_PER_MTOK / 1_000_000,
        )

    def _criteria(self) -> dict:
        return {
            "standing": _option(STANDING_DESCRIPTION, self.standing_example),
            "sitting": _option(SITTING_DESCRIPTION, self.sitting_example),
            "away": AWAY_DESCRIPTION,
        }


def _option(description: str, example_path: Path | None) -> str | dict:
    if example_path is not None and example_path.is_file():
        return {
            "description": description,
            "examples": [Image(example_path)],
        }
    return description


def _extract_input_tokens(result: object) -> int:
    usage = getattr(result, "usage", None)
    if usage is None:
        return 0
    tokens = getattr(usage, "input_tokens", None)
    if tokens is None and isinstance(usage, dict):
        tokens = usage.get("input_tokens", 0)
    try:
        return int(tokens or 0)
    except (TypeError, ValueError):
        return 0
