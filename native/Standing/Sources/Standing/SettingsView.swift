import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var bridge: PythonBridge
    @EnvironmentObject private var healthKit: HealthKitLogger
    @EnvironmentObject private var updater: UpdaterController

    var body: some View {
        Form {
            Section("Support") {
                Text("Standing is free. One-time support helps keep it going.")
                    .foregroundStyle(Color.secondary)
                    .font(.callout)
                Link("Support Standing… ($5)", destination: SupportLinks.oneTimeURL)
            }

            Section("Account") {
                LabeledContent("AI API key") {
                    Text(bridge.state.hasApiKey ? "Saved in Keychain" : "Not set")
                        .foregroundStyle(bridge.state.hasApiKey ? Color.secondary : Color.orange)
                }
                SecureField(
                    bridge.state.hasApiKey ? "Paste new key to replace" : "Paste TypeSafe AI API key",
                    text: $bridge.apiKeyDraft
                )
                HStack {
                    Button("Save AI key") { bridge.saveApiKey() }
                        .disabled(bridge.apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button("Clear key", role: .destructive) { bridge.clearApiKey() }
                        .disabled(!bridge.state.hasApiKey)
                }
                Link("Get a TypeSafe API key…", destination: URL(string: "https://console.typesafe.ai")!)
                    .font(.caption)
            }

            if bridge.state.stravaUiEnabled {
                Section("Strava") {
                    Text(bridge.state.stravaLabel)
                        .foregroundStyle(Color.secondary)
                    HStack {
                        Button("Connect Strava") { bridge.connectStrava() }
                            .disabled(!bridge.state.stravaConfigured || bridge.state.stravaConnected)
                        Button("Disconnect", role: .destructive) { bridge.disconnectStrava() }
                            .disabled(!bridge.state.stravaConnected)
                    }
                    if !bridge.state.stravaConfigured {
                        Text("Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to .env")
                            .font(.caption)
                            .foregroundStyle(Color.orange)
                    }
                }
            }

            Section("Apple Health") {
                if healthKit.isAvailable {
                    Toggle(
                        "Log standing sessions",
                        isOn: Binding(
                            get: { healthKit.isEnabled },
                            set: { bridge.setHealthKitLogging($0) }
                        )
                    )
                    Text(
                        "Off by default. When on, standing bouts of 10+ minutes are saved as Workouts in Apple Health (not the Watch Stand ring)."
                    )
                    .font(.caption)
                    .foregroundStyle(Color.secondary)
                    if let err = healthKit.lastError {
                        Text(err)
                            .font(.caption)
                            .foregroundStyle(Color.red)
                    }
                } else {
                    Text("Apple Health is not available on this Mac.")
                        .foregroundStyle(Color.secondary)
                }
            }

            Section("Standing nudges") {
                Toggle("Suggestions & posture tips", isOn: Binding(
                    get: { bridge.state.suggestionsEnabled },
                    set: { bridge.setSuggestions($0) }
                ))
                LabeledContent("Remind after sitting") {
                    HStack(spacing: 6) {
                        TextField("", text: $bridge.sitWarnText, prompt: Text("30"))
                            .multilineTextAlignment(.trailing)
                            .labelsHidden()
                            .frame(width: 44)
                            .onSubmit { bridge.applyThresholds() }
                        Text("min").foregroundStyle(Color.secondary)
                    }
                }
                LabeledContent("Remind after standing") {
                    HStack(spacing: 6) {
                        TextField("", text: $bridge.standWarnText, prompt: Text("45"))
                            .multilineTextAlignment(.trailing)
                            .labelsHidden()
                            .frame(width: 44)
                            .onSubmit { bridge.applyThresholds() }
                        Text("min").foregroundStyle(Color.secondary)
                    }
                }
            }
            .onDisappear { bridge.applyThresholds() }

            Section("Calibration") {
                Text(bridge.state.calibrationLabel.replacingOccurrences(of: "Calibration: ", with: ""))
                    .foregroundStyle(Color.secondary)
                HStack {
                    Button("Calibrate sitting") { bridge.calibrateSitting() }
                    Button("Calibrate standing") { bridge.calibrateStanding() }
                }
                Button("Clear calibration", role: .destructive) { bridge.clearCalibration() }
            }

            Section("Worker") {
                LabeledContent("Status") {
                    Text(bridge.workerReady ? "Connected" : "Starting…")
                        .foregroundStyle(bridge.workerReady ? Color.green : Color.secondary)
                }
                if let err = bridge.workerError {
                    Text(err).foregroundStyle(Color.red)
                }
                Button("Open log") { bridge.openLog() }
            }

            Section("Updates") {
                LabeledContent("Version") {
                    Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—")
                        .foregroundStyle(Color.secondary)
                }
                if updater.isConfigured {
                    Button("Check for Updates…") { updater.checkForUpdates() }
                } else {
                    Text("Auto-updates activate after the app is packaged with a Sparkle feed URL.")
                        .font(.caption)
                        .foregroundStyle(Color.secondary)
                }
            }
        }
        .formStyle(.grouped)
        // Keep a compact preference-pane width — Form otherwise stretches too wide.
        .frame(width: 400)
        .padding(.vertical, 8)
    }
}
