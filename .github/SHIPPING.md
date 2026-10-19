# Shipping Standing (AI-based standing tracker)

## Decision: DMG now, Mac App Store next

**Notarized DMG remains the primary channel.** Mac App Store packaging is prepared
in-repo — follow [`store/APP_STORE.md`](store/APP_STORE.md) when you are ready to
create the App Store Connect record and upload a `.pkg`.

| | DMG (shipping) | Mac App Store (prepared) |
| --- | --- | --- |
| Effort | Days | Days to first upload; Review may take longer |
| Review | Apple notarization only | Full App Review |
| Camera + BYO API key | Straightforward | Privacy policy + nutrition labels ([standing.joelhanson.com](https://standing.joelhanson.com/privacy.html)) |
| Stack today | **Lane B** SwiftUI + Python worker | Same; sandbox entitlements in `Standing.mas.entitlements` |
| Package | `./scripts/package-dmg.sh` | `./scripts/package-mas.sh` |
| Updates | Sparkle + hosted appcast/DMG | App Store Connect (no Sparkle feed) |

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
- Requiring every customer's TypeSafe key is fine, but Review will scrutinize it

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
export STANDING_APP_BUILD=3
# optional Sparkle:
# export STANDING_SPARKLE_FEED_URL=https://…/appcast.xml
# export STANDING_SPARKLE_PUBLIC_ED_KEY=…
./scripts/package-dmg.sh   # → dist/Standing-0.2.0.dmg
```

**Multi-arch DMGs (native per CPU).** GitHub Actions builds two release
artifacts on matching runners:

| Arch | Runner | Asset |
| --- | --- | --- |
| Apple Silicon | `macos-15` | `Standing-<ver>-arm64.dmg` (+ legacy `Standing-<ver>.dmg`) |
| Intel | `macos-15-intel` | `Standing-<ver>-x86_64.dmg` |

Each build runs `swift build --arch <host>` and embeds a relocatable CPython
via `uv` (`cpython-3.12-macos-aarch64-none` or `…-x86_64-none`) under
`Standing.app/Contents/Resources/StandingPayload/python/`, with worker deps
installed into that tree. The launcher is renamed to `StandingWorker` so macOS
never prompts about `python3.12`. The Swift shell owns the API-key Keychain
entry and passes `TYPESAFE_API_KEY` into the helper (`STANDING_DISABLE_KEYRING=1`).
Customers do not need Python installed. Packaging refuses virtualenvs and
host-Framework symlinks so Save AI key cannot ship broken again. Cross-compiling
from one Mac to the other is not supported (OpenCV/NumPy wheels must match the host).

Also installs `requirements-release.txt` (no rumps/PyObjC) and strips
tests/pip/unused stdlib (never `.env` or local data). Dev builds
(`./scripts/run-native.sh`) still point at the repo `.venv` + full
`requirements.txt`.

Manual Apple steps (or let CI do them — see below):
1. Apple Developer ID certificate
2. `codesign` → `notarytool` → staple
3. Host the DMG on GitHub Releases

## GitHub Actions CI (macOS smoke)

Every push to `main` and every PR runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml) on a matrix:

- `macos-15` (arm64)
- `macos-15-intel` (x86_64)

Each job: install deps → import core modules → `package-app.sh` (dev) → wrap/mount a DMG.

Locally: `./scripts/ci-smoke.sh` (host arch). Release-embed smoke:
`STANDING_CI_RELEASE_SMOKE=1 ./scripts/ci-smoke.sh`.

## GitHub Actions release

Push a version tag (or run **Release** via workflow_dispatch):

```bash
git tag v0.2.0
git push origin v0.2.0
```

Workflow: [`.github/workflows/release.yml`](.github/workflows/release.yml)

| Step | What it does |
| --- | --- |
| Build | Matrix: `macos-15` (arm64) + `macos-15-intel` (x86_64) |
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
export STANDING_APP_BUILD=3
export STANDING_SPARKLE_FEED_URL="https://YOUR_HOST/appcast.xml"
export STANDING_SPARKLE_PUBLIC_ED_KEY="YOUR_ED25519_PUBLIC_KEY"
./scripts/run-native.sh
```

**Each patch**
1. Bump version and push `vX.Y.Z` (CI packages, optionally notarizes, and publishes), **or** locally:
2. Notarize the new DMG
3. Run `sign_update Standing.dmg` and paste signature + length into `appcast.xml`
4. Publish the DMG + updated appcast — existing installs pick it up (or via **Check for Updates…**)

## Store path

**Ready in repo**
1. Lane B SwiftUI shell + sandboxed MAS entitlements  
2. `PrivacyInfo.xcprivacy`, privacy policy page, App Review notes  
3. `./scripts/package-app.sh --mas` and `./scripts/package-mas.sh`  
4. Listing draft + checklist: [`store/APP_STORE.md`](store/APP_STORE.md)

**Still on you (Apple account)**
1. App ID + Mac App Store provisioning profile for `ai.standing.mac`  
2. Apple Distribution + Mac Installer certificates  
3. App Store Connect record, screenshots, privacy nutrition labels  
4. Upload `.pkg` via Transporter and answer Review

**After first approval (product hardening)**
1. Prefer on-device Vision for sit/stand; keep Jev as optional accuracy  
2. Consider dropping Sparkle from the MAS binary entirely (feed already omitted)  
3. Universal binary / multi-arch Store package if you need Intel + Apple Silicon in one upload  

This repo already has: local API key storage, suggestions + notifications, cost-aware Jev calls, and a SwiftUI shell over the same core.

## Monetization (one-time Support)

- **Everything is free** — tracking, history, nudges. No paywall, no license key.
- Optional **one-time Support** via [Buy Me a Coffee](https://buymeacoffee.com/joelhanson): Settings, menu bar, and the landing page.
- URL lives in `src/support.py`, `SupportLinks.swift`, and `web/index.html` (Python shell can also use `STANDING_SUPPORT_URL`).
- Move to subscriptions only if you later host recurring COGS (proxied Jev, cloud sync, etc.).
