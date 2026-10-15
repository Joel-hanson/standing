# Shipping Standing (AI-based standing tracker)

## Decision: DMG first, Mac App Store later

**Ship a notarized DMG (direct download) first.** Move to the Mac App Store only after the product and privacy story are stable.

| | DMG (recommended now) | Mac App Store |
| --- | --- | --- |
| Effort | Days | Weeks+ |
| Review | Apple notarization only | Full App Review |
| Camera + BYO API key | Straightforward | Extra privacy labels + review risk |
| Stack today | **Lane A** rumps *or* **Lane B** SwiftUI + Python worker | Prefer Lane B shell; eventually fold worker into app |
| Updates | Sparkle + hosted appcast/DMG | App Store Connect |

## Architecture (current)

```
┌─────────────────────────────┐
│  Shell A: rumps (Python)    │
│  Shell B: SwiftUI MenuBar   │── JSON lines ──►  src.worker / StandingCore
└─────────────────────────────┘                   camera · motion · Jev · Keychain
```

- **Lane A** — `python -m src.main` (polish path, ships sooner via PyInstaller/Briefcase)
- **Lane B** — `./scripts/run-native.sh` (native UI; Python stays a helper process)

## Why not Store yet
- Sandbox + camera + third-party AI image upload needs a clear privacy policy
- Bundling a Python runtime + OpenCV inside a sandboxed app needs packaging work
- Requiring every customer’s TypeSafe key is fine, but Review will scrutinize it

## Secrets (do not ship your key)

- Customer API keys live in **their** macOS Keychain (`Standing` / `typesafe_api_key`), never in the app binary.
- `.env` / `TYPESAFE_API_KEY` is a **dev-only** fallback. It is gitignored; **never** copy `.env` into a DMG, `.app`, or PyInstaller `datas=`.
- Packaging checklist: exclude `.env`, `data/stats.json`, calibration images, and local logs. Ship `.env.example` only.
- First launch with no key opens **Settings** and hides **Start Tracking** until a key is saved.

## DMG path (next packaging step)
1. Apple Developer ID certificate  
2. Prefer packaging **Lane B**: Swift app bundle + embedded `.venv` or PyInstaller worker binary  
3. Fallback: Lane A only with Briefcase / PyInstaller into `Standing.app`  
4. `codesign` → `notarytool` → staple  
5. Wrap in a DMG and host (GitHub Releases is enough)

## In-app updates (Sparkle · Lane B)

Lane B ships with [Sparkle](https://sparkle-project.org). Local/dev builds omit the feed URL so **Check for Updates** stays hidden.

**One-time setup**
1. Install Sparkle tools (`brew install sparkle`) and run `generate_keys`
2. Store the **private** key offline (never commit it)
3. Host `appcast.xml` over HTTPS (see `native/appcast.example.xml`)

**Package a release build with updates enabled**
```bash
export STANDING_APP_VERSION=0.2.0
export STANDING_APP_BUILD=2
export STANDING_SPARKLE_FEED_URL="https://YOUR_HOST/appcast.xml"
export STANDING_SPARKLE_PUBLIC_ED_KEY="YOUR_ED25519_PUBLIC_KEY"
./scripts/run-native.sh
```

**Each patch**
1. Bump `STANDING_APP_VERSION` / `STANDING_APP_BUILD`
2. Notarize the new DMG
3. Run `sign_update Standing.dmg` and paste signature + length into `appcast.xml`
4. Publish the DMG + updated appcast — existing installs pick it up (or via **Check for Updates…**)

## Store path (later)
1. Keep SwiftUI `MenuBarExtra` shell (Lane B)  
2. Move sit/stand detection on-device (Vision) where possible; Jev as Pro accuracy  
3. Keychain for API key; App Store privacy nutrition labels  
4. Drop or tightly sandbox the Python helper  

This repo already has: Keychain API key, suggestions + notifications, cost-aware Jev calls, and a SwiftUI shell over the same core — enough to validate before packaging.

## Monetization (one-time Support)

- **Everything is free** — tracking, history, nudges. No paywall, no license key.
- Optional **one-time Support ($5)** via Gumroad (or similar): Settings, menu bar, and the landing page.
- Set the live product URL in `src/support.py`, `SupportLinks.swift`, and `web/index.html` (Python shell can also use `STANDING_SUPPORT_URL`).
- Move to subscriptions only if you later host recurring COGS (proxied Jev, cloud sync, etc.).
