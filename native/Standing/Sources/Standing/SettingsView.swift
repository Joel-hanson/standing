import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var bridge: PythonBridge
    @EnvironmentObject private var updater: UpdaterController

    var body: some View {
        Form {
            Section("Support") {
                Text("Standing is free. One-time support helps keep it going.")
                    .foregroundStyle(.secondary)
                    .font(.callout)
                Link("Support Standing…", destination: SupportLinks.oneTimeURL)
            }

            Section("Account") {
                LabeledContent("AI API key") {
                    Text(bridge.state.hasApiKey ? "Saved in Keychain" : "Not set")
                        .foregroundStyle(.secondary)
                }
                SecureField(
                    bridge.state.hasApiKey ? "Paste new key to replace" : "Paste TypeSafe AI API key",
                    text: $bridge.apiKeyDraft
                )
                HStack {
                    Button("Save AI key") { bridge.saveApiKey() }
                        .disabled(
                            bridge.apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                || !bridge.workerReady
                        )
                    Button("Clear key", role: .destructive) { bridge.clearApiKey() }
                        .disabled(!bridge.state.hasApiKey || !bridge.workerReady)
                }
                if let status = bridge.apiKeyStatus {
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if !bridge.workerReady {
                    Text("Waiting for AI helper before saving…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Link("Get a TypeSafe API key…", destination: URL(string: "https://console.typesafe.ai")!)
                    .font(.caption)
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
                        Text("min").foregroundStyle(.secondary)
                    }
                }
                LabeledContent("Remind after standing") {
                    HStack(spacing: 6) {
                        TextField("", text: $bridge.standWarnText, prompt: Text("45"))
                            .multilineTextAlignment(.trailing)
                            .labelsHidden()
                            .frame(width: 44)
                            .onSubmit { bridge.applyThresholds() }
                        Text("min").foregroundStyle(.secondary)
                    }
                }
            }
            .onDisappear { bridge.applyThresholds() }

            Section("Calibration") {
                Text(bridge.state.calibrationLabel.replacingOccurrences(of: "Calibration: ", with: ""))
                    .foregroundStyle(.secondary)
                HStack {
                    Button("Calibrate sitting") { bridge.calibrateSitting() }
                    Button("Calibrate standing") { bridge.calibrateStanding() }
                }
                Button("Clear calibration", role: .destructive) { bridge.clearCalibration() }
            }

            Section("Worker") {
                LabeledContent("Status") {
                    Text(bridge.workerReady ? "Connected" : "Starting…")
                        .foregroundStyle(.secondary)
                }
                if let err = bridge.workerError {
                    Text(err).foregroundStyle(StandingTheme.primary)
                }
                Button("Open log") { bridge.openLog() }
            }

            Section("Updates") {
                LabeledContent("Version") {
                    Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—")
                        .foregroundStyle(.secondary)
                }
                if updater.isConfigured {
                    Button("Check for Updates…") { updater.checkForUpdates() }
                } else {
                    Text("Auto-updates activate after the app is packaged with a Sparkle feed URL.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .buttonStyle(.bordered)
        // Keep a compact preference-pane width — Form otherwise stretches too wide.
        .frame(width: 400)
        .padding(.vertical, 8)
        .standingChrome()
    }
}
