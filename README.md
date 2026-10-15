# Standing

Watches your webcam, decides sit vs stand, and nudges you when one posture lasts too long. Motion-gated locally; only sends a small JPEG to [Jev](https://docs.typesafe.ai/images) when a new check is worthwhile.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Create a TypeSafe API key at [console.typesafe.ai](https://console.typesafe.ai)
2. Paste it in **Settings → AI API key** (Keychain), or set `TYPESAFE_API_KEY` in `.env` for local dev
3. **Calibrate sitting**, then **Calibrate standing**, then **Start Tracking**

Data lives in `~/Library/Application Support/Standing/`; logs in `~/Library/Logs/Standing/`.

## Run

| Shell | Command | Notes |
| --- | --- | --- |
| rumps (Python) | `python -m src.main` | Fast iteration |
| SwiftUI | `./scripts/run-native.sh` | Native menu bar — use this, not bare `swift run` |

Both drive the same `StandingCore` in `src/core.py`.

```bash
python -m src.main --sit-warn-minutes 25 --stand-warn-minutes 40 -v
```

## Shipping

DMG first, Mac App Store later — see [SHIPPING.md](SHIPPING.md).
