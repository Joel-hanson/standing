# App Store Connect metadata (draft)

Use these as starting copy — tweak tone before submit.

## Name
Standing

## Subtitle (30 characters max)
Desk posture nudges for Mac

## Category
Primary: Utilities  
Secondary: Health & Fitness (optional)

## Keywords (100 characters max, comma-separated)
posture,standing desk,sit stand,webcam,menu bar,reminders,desk,ergonomics

## Promotional text (optional, 170 chars — changeable without new binary)
Quiet menu bar posture checks. Bring your own TypeSafe API key; camera stays on your Mac until a check is needed.

## Description
Standing is a quiet macOS menu bar app that watches your desk posture and nudges you when you've been sitting—or standing—too long.

HOW IT WORKS
• Motion-gated locally: Standing only asks AI when a check is worthwhile  
• Short camera stills; optional classification via TypeSafe (Jev) with your own API key  
• Calibrate sitting and standing once so checks match how you work  
• macOS notifications for gentle sit/stand reminders  

YOUR KEY, YOUR MAC
• Paste a TypeSafe API key in Settings (stored on this Mac)  
• No Standing account and no cloud sync of your history  
• Stats and calibration stay in Application Support  

REQUIREMENTS
• macOS 14 or later  
• A webcam  
• A TypeSafe API key from console.typesafe.ai (usage billed by TypeSafe)

Standing is free. Optional one-time support helps keep the project going.

## What's New (0.2.0)
Mac App Store packaging path, privacy policy, improved app icon, and clearer update messaging for direct vs App Store builds.

## Support URL
https://github.com/Joel-hanson/standing

## Marketing URL
https://standing.joelhanson.com/

## Privacy Policy URL
https://standing.joelhanson.com/privacy.html

## Copyright
© 2026 Joel Hanson

## Screenshots (you capture)
Mac App Store needs macOS screenshots (typically 1280×800 or 1440×900 for 16:10; check current ASC sizes).

Suggested set (3–5):
1. Menu bar glance open (status + Start Tracking)  
2. Settings — API key + thresholds  
3. Activity / history window  
4. Notification example (optional)  

Repo helper: `scripts/capture_screenshots.py` (extend if needed for ASC crops).
Place finals in `store/screenshots/` (gitignored binaries OK; keep a README if large).
