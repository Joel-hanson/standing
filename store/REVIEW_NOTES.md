# Notes for App Review

Paste into App Store Connect → App Review Information → Notes.

---

## Summary
Standing is a macOS **menu bar** (LSUIElement) utility. It uses the camera to
tell sitting from standing at a desk and sends macOS notifications when one
posture lasts too long.

## How to test
1. Launch Standing — it appears only in the menu bar (no Dock icon).  
2. Open **Settings…** from the menu.  
3. Paste the TypeSafe API key we provided in **App Review** contact notes / demo
   field (or create a free key at https://console.typesafe.ai).  
4. Allow **Camera** and **Notifications** when prompted.  
5. **Calibrate sitting**, then **Calibrate standing**, then **Start Tracking**.  
6. Sit or stand in view of the camera; after motion or the heartbeat interval,
   status should update. Thresholds are adjustable in Settings.

There is no login. Without an API key, Start Tracking stays hidden (by design).

## Camera & network
- Camera entitlement: posture stills only.  
- Outbound HTTPS: TypeSafe Jev image API, only when the user has saved an API
  key and a check runs.  
- Privacy policy: https://standing.joelhanson.com/privacy.html  

## Technical notes reviewers may ask about
- The app embeds a private **Python helper** (`StandingWorker`) plus OpenCV/NumPy
  for camera capture and motion gating. The SwiftUI shell owns the UI and
  spawns the helper from `Contents/Resources`.  
- Hardened Runtime exceptions
  (`allow-unsigned-executable-memory`, `disable-library-validation`, `allow-jit`)
  are required for that embedded interpreter and native wheels.  
- App Sandbox is enabled (`Standing.mas.entitlements`).  
- We do **not** use Sparkle auto-update on Mac App Store builds; updates go
  through the App Store.  

## In-app “Support Standing” link
Opens Buy Me a Coffee in the browser. The app is fully free; the link is
optional patronage and does not unlock features. Happy to remove it if it
conflicts with guideline interpretation.

## Contact
Use the email on the App Store Connect account / GitHub
https://github.com/Joel-hanson/standing
