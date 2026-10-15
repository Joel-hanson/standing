import AppKit
import SwiftUI

@main
struct StandingApp: App {
    @StateObject private var bridge = PythonBridge()
    @StateObject private var updater = UpdaterController()
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var didOfferOnboarding = false

    var body: some Scene {
        MenuBarExtra {
            GlanceMenu()
                .environmentObject(bridge)
                .environmentObject(updater)
                .onChange(of: bridge.workerReady) { _, ready in
                    offerOnboardingIfNeeded(ready: ready)
                }
                .onChange(of: bridge.state.hasApiKey) { _, _ in
                    offerOnboardingIfNeeded(ready: bridge.workerReady)
                }
        } label: {
            Label {
                Text(bridge.state.barTitle)
            } icon: {
                Image(systemName: bridge.state.barSymbol)
            }
        }
        .menuBarExtraStyle(.menu)

        Window("Activity", id: "activity") {
            ActivityView()
                .environmentObject(bridge)
        }
        .defaultSize(width: 440, height: 560)

        Settings {
            SettingsView()
                .environmentObject(bridge)
                .environmentObject(updater)
                // Pin the system Settings window to a compact preference width.
                .frame(width: 400)
        }
    }

    /// First launch without a key: open Settings (Start is hidden until then).
    private func offerOnboardingIfNeeded(ready: Bool) {
        guard ready, !didOfferOnboarding, !bridge.state.hasApiKey else { return }
        didOfferOnboarding = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}

/// Keep Standing (AI-based standing tracker) out of the Dock — menu-bar accessory app.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }

    func applicationWillTerminate(_ notification: Notification) {
        // PythonBridge owns the worker; Process dies with the app.
    }
}
