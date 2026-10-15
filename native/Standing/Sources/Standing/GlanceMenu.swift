import AppKit
import SwiftUI

/// Menu-bar dropdown — glance status first, then a few actions (Mac status-item pattern).
struct GlanceMenu: View {
    @EnvironmentObject private var bridge: PythonBridge
    @EnvironmentObject private var updater: UpdaterController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        // Read-only status rows
        Text(bridge.state.statusTitle)
        Text(bridge.state.todayLine)

        if let hint = bridge.state.setupHint {
            Text(hint)
        }

        if let err = bridge.workerError {
            Text(err)
        }

        Divider()

        if bridge.state.hasApiKey {
            Button(bridge.state.tracking ? "Pause Tracking" : "Start Tracking") {
                bridge.toggleTracking()
            }
        } else {
            SettingsLink {
                Text("Set up Standing…")
            }
        }

        Button("Activity…") {
            NSApp.activate(ignoringOtherApps: true)
            openWindow(id: "activity")
        }

        Divider()

        Toggle("Suggestions", isOn: Binding(
            get: { bridge.state.suggestionsEnabled },
            set: { bridge.setSuggestions($0) }
        ))

        Button("Reset Today…") {
            bridge.resetDay()
        }

        Divider()

        SettingsLink {
            Text("Settings…")
        }

        if updater.isConfigured {
            Button("Check for Updates…") {
                updater.checkForUpdates()
            }
        }

        Link("Support Standing… ($5)", destination: SupportLinks.oneTimeURL)

        Button("Quit Standing") {
            bridge.quitApp()
        }
    }
}
