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
- Packaging checklist: exclude `.env` and any local `data/` leftovers. Ship `.env.example` only.
- Runtime state is **not** bundled: stats, history, and calibration live in
  `~/Library/Application Support/Standing/`; logs in `~/Library/Logs/Standing/`.
  (Created on first launch; survives app updates. Override with `STANDING_DATA_DIR` / `STANDING_LOG_DIR`.)
- First launch with no key opens **Settings** and hides **Start Tracking** until a key is saved.

## DMG path (packaging)

Local:

```bash
export STANDING_APP_VERSION=0.2.0
export STANDING_APP_BUILD=2
# optional Sparkle:
# export STANDING_SPARKLE_FEED_URL=https://…/appcast.xml
# export STANDING_SPARKLE_PUBLIC_ED_KEY=…
./scripts/package-dmg.sh   # → dist/Standing-0.2.0.dmg
```

`package-app.sh --release` embeds `src/` + a fresh `.venv` under
`Standing.app/Contents/Resources/StandingPayload/` (never `.env` or local data).
Dev builds (`./scripts/run-native.sh`) still point at the repo `.venv`.

Manual Apple steps (or let CI do them — see below):
1. Apple Developer ID certificate
2. `codesign` → `notarytool` → staple
3. Host the DMG on GitHub Releases

## GitHub Actions CI (macOS smoke)

Every push to `main` and every PR runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml) on `macos-14`:

1. Install Python deps into `.venv`
2. Import core modules (`src.core`, `src.worker`, …)
3. `package-app.sh` → verify `Standing.app` layout
4. Wrap a DMG and mount it to confirm the app is inside

Locally: `./scripts/ci-smoke.sh`

## GitHub Actions release

Push a version tag (or run **Release** via workflow_dispatch):

```bash
git tag v0.2.0
git push origin v0.2.0
```

Workflow: [`.github/workflows/release.yml`](.github/workflows/release.yml)

| Step | What it does |
| --- | --- |
| Build | `package-dmg.sh` on `macos-14` (Swift shell + embedded Python) |
| Sign / notary | If Apple secrets are set — otherwise uploads an unsigned DMG |
| Sparkle | If `SPARKLE_PRIVATE_ED_KEY` is set — attaches `appcast.xml` |
| Publish | Creates a GitHub Release with the DMG (+ appcast when present) |

**Repo secrets** (Settings → Secrets and variables → Actions):

| Secret | Purpose |
| --- | --- |
| `APPLE_CERTIFICATE_P12_BASE64` | `base64` of Developer ID Application `.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | `.p12` export password |
| `APPLE_API_KEY_P8_BASE64` | `base64` of App Store Connect `AuthKey_*.p8` |
| `APPLE_API_KEY_ID` | Key id |
| `APPLE_API_ISSUER_ID` | Issuer UUID |
| `SPARKLE_PRIVATE_ED_KEY` | Sparkle ed25519 private key (optional) |
| `STANDING_SPARKLE_PUBLIC_ED_KEY` | Public key baked into Info.plist (optional) |
| `STANDING_SPARKLE_FEED_URL` | HTTPS appcast URL (optional) |

Without Apple secrets the workflow still publishes a DMG for smoke-testing; other Macs will see a Gatekeeper warning until you add signing + notarization.

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
1. Bump version and push `vX.Y.Z` (CI packages, optionally notarizes, and publishes), **or** locally:
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
