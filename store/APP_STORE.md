# Mac App Store preparation

Standing can ship as a **notarized DMG** today. This folder is the checklist and
assets to list the same Lane B app (`ai.standing.mac`) on the Mac App Store.

Privacy policy URL (required in App Store Connect):
**https://standing.joelhanson.com/privacy.html**

## Status snapshot

| Area | State |
| --- | --- |
| Bundle ID | `ai.standing.mac` (already in Info.plist) |
| Sandbox entitlements | `native/Standing/Standing.mas.entitlements` |
| Privacy manifest | `native/Standing/PrivacyInfo.xcprivacy` |
| MAS packaging | `./scripts/package-mas.sh` → `.pkg` |
| Privacy policy page | `web/privacy.html` → https://standing.joelhanson.com/privacy.html |
| Sparkle on MAS | Feed never baked; UI says “Updates via Mac App Store” |
| Embedded Python + OpenCV | Still required — main Review risk |
| App Store Connect record | **You create** (manual) |
| Distribution / Installer certs + profile | **You create** (manual) |

## One-time Apple setup (you)

1. **Apple Developer Program** membership active.
2. **Identifiers → App IDs → macOS**  
   Bundle ID `ai.standing.mac`  
   Capabilities: App Sandbox, Camera (plus outbound network is entitlement-only).
3. **Profiles → Mac App Store** provisioning profile for that App ID.
4. **Certificates**  
   - Apple Distribution (app)  
   - Mac Installer Distribution / 3rd Party Mac Developer Installer (pkg)
5. **App Store Connect → My Apps → macOS**  
   - Name: Standing  
   - Bundle ID: `ai.standing.mac`  
   - SKU: e.g. `standing-mac`  
   - Primary language: English (U.S.)

## Build & upload

```bash
export STANDING_APP_VERSION=0.2.0
export STANDING_APP_BUILD=3   # must increase every upload
export STANDING_MAS_APP_IDENTITY="Apple Distribution: Your Name (TEAMID)"
export STANDING_MAS_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: Your Name (TEAMID)"
export STANDING_MAS_PROVISIONING_PROFILE="$HOME/path/to/Standing_MAS.provisionprofile"

./scripts/package-mas.sh
# → dist/Standing-0.2.0-mas.pkg

# Upload with Transporter, or:
# xcrun altool --upload-app -f dist/Standing-0.2.0-mas.pkg \
#   --apiKey … --apiIssuer …
```

Without identities, `package-mas.sh` still builds a sandbox-entitled `.app` for
local smoke tests (ad-hoc signed).

Universal binary note: today CI builds **per-arch** DMGs. For the Store, either
upload one arch first (Apple Silicon is fine) or produce a universal `.app`
later (both shells + both Python trees, or lipo + dual payloads — not automated yet).

## App Store Connect listing (copy)

See `METADATA.md` for subtitle, description, keywords, and screenshot notes.
Paste the privacy URL above into **App Privacy** and the nutrition labels.

Suggested App Privacy answers (align with `PrivacyInfo.xcprivacy` + privacy page):

- **Data used to track you:** No  
- **Data linked to you:** No (unless TypeSafe's terms change your answer)  
- **Data not linked to you:** Photos or Videos — App Functionality  
  (camera stills for posture; optional send to TypeSafe with user key)  
- **Tracking:** No

## Age rating / export

- Age rating: 4+ (utilities; no restricted content)  
- Encryption: `ITSAppUsesNonExemptEncryption = false` is already in the MAS Info.plist  
  (HTTPS only via system APIs / standard TLS)

## Review notes

Paste from `REVIEW_NOTES.md` into the App Review notes field. Demo account:
there is none — Reviewers need a TypeSafe API key; provide a short-lived test key
or offer a TestFlight/demo path.

## Remaining product risks (before you press Submit)

1. **Sandbox + embedded CPython/OpenCV** — Hardened Runtime exceptions
   (`allow-unsigned-executable-memory`, `disable-library-validation`, `allow-jit`)
   are in the MAS entitlements. Expect questions; answer honestly in Review notes.
2. **BYO API key** — Fine if disclosed; make onboarding obvious (already is).
3. **Buy Me a Coffee link** — Patronage for a free app is usually OK; remove if
   Review cites external purchase guidelines.
4. **Long-term** — Prefer on-device Vision for sit/stand so Jev is optional “Pro”
   accuracy (see SHIPPING.md). That lowers privacy and packaging risk.

## Parallel track

Keep shipping notarized DMGs via `./scripts/package-dmg.sh` / the Release
workflow. MAS and direct can coexist under the same bundle ID only if you use
separate bundle IDs or carefully manage version trains — safest is **same
bundle ID**, one store listing, and treat DMG as the interim channel until
approved.
