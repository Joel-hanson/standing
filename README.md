# Standing

You want to stand more at your desk. A timer alone does not know if you stood up. Standing watches the webcam, decides sit vs stand, and nudges you when one posture lasts too long.

**The idea:** Local code watches for motion. Only when something makes a new posture check worthwhile does it send a small photo to [Jev](https://docs.typesafe.ai/images) (TypeSafe) and ask “sitting or standing?”

```text
Webcam frame (every ~0.5s)
        │
        ▼
  MotionGate ── still? ──► skip API (cheap)
        │
     moved / heartbeat / start
        │
        ▼
  Scene+pose cache ── familiar? ──► reuse label (no API)
        │
     new / ambiguous / start / confirm
        │
        ▼
  resize JPEG (~360px) ──► Jev ──► sit | stand
        │
        ▼
  StandingTracker ──► menu bar + optional nudge
```

## One concrete pass

1. You are sitting. Frames look almost the same. Motion score stays low. No API call.
2. You stand up. Frame difference crosses the motion threshold. Standing sends one JPEG to Jev.
3. Jev returns `standing`. The tracker starts a standing streak and updates the menu bar. That `(scene, pose band)` is remembered locally.
4. For the next ~15s (cooldown), more motion does not trigger another call.
5. If you stay still for ~3 minutes (heartbeat), Standing checks again — but if the scene and coarse pose still match a recent label, it reuses the cache instead of calling Jev.
6. Every 8th cache hit on the same key forces one Jev refresh so labels do not go stale.

That is the whole cost model: **motion gate + scene/pose cache + cooldown + heartbeat**, not “every frame.” The cache only *skips* calls the gates already planned; it never adds spend. It stores a tiny JSON file (≤32 entries, ~32 KB, 7-day TTL, no photos).

## Two shells, one brain

The UI and the detection logic are separate. Either shell drives the same `StandingCore` in `src/core.py` (camera, motion, Jev, tracker, Keychain, suggestions).

```text
┌──────────────────────────────┐
│  A · rumps (Python menu bar) │
│  B · SwiftUI MenuBarExtra    │── JSON lines ──► src.worker
└──────────────────────────────┘                      │
                                                      ▼
                                              StandingCore
                                         camera · motion · Jev
                                         tracker · Keychain
```

| Shell | Run | When to use |
| --- | --- | --- |
| **A · rumps** | `python -m src.main` | Fast iteration; AppKit Settings |
| **B · SwiftUI** | `./scripts/run-native.sh` | Native menu bar + Activity window |

Do **not** use bare `swift run Standing` day to day. A raw binary is not an app bundle; notifications will crash.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### TypeSafe / Jev API key

Standing uses your own TypeSafe key (bring-your-own).

1. Sign in at [console.typesafe.ai](https://console.typesafe.ai)
2. **API Keys** → create a key
3. Paste it in **Settings → AI API key** (saved in macOS Keychain)

`.env` / `TYPESAFE_API_KEY` works as a **dev-only** fallback. Never ship it in a DMG or app bundle. See [TypeSafe quick start](https://docs.typesafe.ai/introduction/quickstart).

### First run

1. Launch shell A or B
2. **Settings** opens if no key is set — paste the key
3. **Calibrate sitting**, then **Calibrate standing** (reference photos for Jev)
4. **Start Tracking** (hidden until a key exists)

Look in the **menu bar** (near the clock) for the sit/stand icon.

Stats, history, and calibration photos are stored in
`~/Library/Application Support/Standing/` (not in the app or repo). Logs go to
`~/Library/Logs/Standing/`. A one-time migrate copies any old repo `data/` files there.

### Shell A — rumps

```bash
python -m src.main
```

### Shell B — SwiftUI

Requires Xcode / Swift 5.9+ (macOS 14+). Packages a real `.app`:

```bash
./scripts/run-native.sh
```

## What you get

| Piece | Role |
| --- | --- |
| Menu bar | Icon + streak while tracking |
| Glance menu | Status, today’s stand-ups / times, Start/Pause |
| Settings | API key, calibration, sit/stand thresholds, Support |
| Activity (B) | 7-day stand/sit chart, recent days, usage |
| Nudges | Notifications after ~30 min sitting or ~45 min standing |
| Cost controls | Motion gate, scene+pose cache, heartbeat (~180s), cooldown (~15s), ~360px images |
| Support | Optional one-time **$5** — app stays free (no feature locks) |

```bash
python -m src.main --sit-warn-minutes 25 --stand-warn-minutes 40 -v
```

## Logs

```bash
python -m src.main -v
# worker: stderr only — stdout is IPC
python -m src.worker -v
tail -f data/standing.log
```

## Shipping

**DMG first, Mac App Store later** — see [SHIPPING.md](SHIPPING.md). Lane B is the Store-shaped shell; Python remains the worker for now.

CI: every push/PR runs a macOS smoke build (`./scripts/ci-smoke.sh`). Release: push a `v*` tag → builds `Standing.dmg` and publishes a GitHub Release. Add Apple Developer secrets for notarized builds.

## Boundaries worth knowing

- Calibration photos improve accuracy but cost tokens when sent — calibrate once, keep both set.
- Default image longest side is **360px** (fewer tokens than 512; still above TypeSafe’s minimum).
- Customer keys live in **their** Keychain (`Standing` / `typesafe_api_key`), never in the app binary.
