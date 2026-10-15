import AppKit
import Combine
import Foundation
import UserNotifications

@MainActor
final class PythonBridge: ObservableObject {
    @Published private(set) var state = StandingState.empty
    @Published private(set) var workerReady = false
    @Published private(set) var workerError: String?
    @Published var sitWarnText = "30"
    @Published var standWarnText = "45"
    @Published var apiKeyDraft = ""

    let healthKit = HealthKitLogger()

    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var readBuffer = Data()
    private var nextId = 1
    private let repoRoot: URL

    init() {
        self.repoRoot = Self.resolveRepoRoot()
        // UserNotifications only works inside a real .app bundle — never call it
        // from a raw `swift run` binary (crashes with bundleProxyForCurrentProcess).
        if Self.runningInsideAppBundle {
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }
        startWorker()
    }

    func setHealthKitLogging(_ enabled: Bool) {
        Task { await healthKit.setEnabled(enabled) }
    }

    deinit {
        // Best-effort; Process termination from deinit is limited.
    }

    func toggleTracking() { send(cmd: "toggle_tracking") }
    func resetDay() { send(cmd: "reset_day") }
    func toggleSuggestions() { send(cmd: "toggle_suggestions") }

    func setSuggestions(_ enabled: Bool) {
        send(cmd: "set_suggestions", ["enabled": enabled])
    }

    func saveApiKey() {
        let key = apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return }
        send(cmd: "save_api_key", ["key": key])
        apiKeyDraft = ""
    }

    func clearApiKey() { send(cmd: "clear_api_key") }
    func connectStrava() { send(cmd: "connect_strava") }
    func disconnectStrava() { send(cmd: "disconnect_strava") }

    func applyThresholds() {
        let sit = Double(sitWarnText) ?? state.sitWarnMinutes
        let stand = Double(standWarnText) ?? state.standWarnMinutes
        send(cmd: "apply_thresholds", [
            "sit_warn_minutes": sit,
            "stand_warn_minutes": stand,
        ])
    }

    func calibrateSitting() { send(cmd: "calibrate", ["posture": "sitting"]) }
    func calibrateStanding() { send(cmd: "calibrate", ["posture": "standing"]) }
    func clearCalibration() { send(cmd: "clear_calibration") }
    func openLog() { send(cmd: "open_log") }

    func quitApp() {
        send(cmd: "shutdown")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            NSApp.terminate(nil)
        }
    }

    // MARK: - Worker lifecycle

    private func startWorker() {
        let python = Self.resolvePython(repoRoot: repoRoot)
        let process = Process()
        process.executableURL = python
        process.arguments = ["-m", "src.worker"]
        process.currentDirectoryURL = repoRoot
        process.environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONUNBUFFERED": "1",
        ]) { _, new in new }

        let stdin = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { @MainActor in
                self?.consumeStdout(data)
            }
        }
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if let line = String(data: data, encoding: .utf8), !line.isEmpty {
                FileHandle.standardError.write(data)
            }
        }
        process.terminationHandler = { [weak self] proc in
            Task { @MainActor in
                self?.workerReady = false
                if proc.terminationStatus != 0 {
                    self?.workerError = "Worker exited (\(proc.terminationStatus))"
                }
            }
        }

        do {
            try process.run()
            self.process = process
            self.stdinPipe = stdin
            self.stdoutPipe = stdout
            self.stderrPipe = stderr
            workerError = nil
        } catch {
            workerError = "Could not start Python worker: \(error.localizedDescription)"
        }
    }

    private func send(cmd: String, _ extra: [String: Any] = [:]) {
        var payload: [String: Any] = ["cmd": cmd, "id": nextId]
        nextId += 1
        for (k, v) in extra { payload[k] = v }
        guard
            let data = try? JSONSerialization.data(withJSONObject: payload),
            var line = String(data: data, encoding: .utf8)
        else { return }
        line.append("\n")
        stdinPipe?.fileHandleForWriting.write(Data(line.utf8))
    }

    private func consumeStdout(_ data: Data) {
        readBuffer.append(data)
        while let range = readBuffer.range(of: Data([0x0A])) {
            let lineData = readBuffer.subdata(in: readBuffer.startIndex..<range.lowerBound)
            readBuffer.removeSubrange(readBuffer.startIndex...range.lowerBound)
            guard
                let obj = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any],
                let event = obj["event"] as? String
            else { continue }
            handleEvent(event, obj)
        }
    }

    private func handleEvent(_ event: String, _ obj: [String: Any]) {
        switch event {
        case "ready":
            workerReady = true
            workerError = nil
        case "state":
            if let stateObj = obj["state"] as? [String: Any] {
                let next = StandingState.from(json: stateObj)
                // Don't clobber threshold fields while the user is editing.
                let prevSit = String(Int(state.sitWarnMinutes))
                let prevStand = String(Int(state.standWarnMinutes))
                if sitWarnText == prevSit || sitWarnText.isEmpty {
                    sitWarnText = String(Int(next.sitWarnMinutes))
                }
                if standWarnText == prevStand || standWarnText.isEmpty {
                    standWarnText = String(Int(next.standWarnMinutes))
                }
                state = next
            }
        case "notify":
            let title = obj["title"] as? String ?? "Standing"
            let message = obj["message"] as? String ?? ""
            postNotification(title: title, message: message)
        case "standing_bout_ended":
            let seconds = obj["elapsed_seconds"] as? Double
                ?? Double(obj["elapsed_seconds"] as? Int ?? 0)
            healthKit.logStandingBout(elapsedSeconds: seconds)
        case "error":
            workerError = obj["message"] as? String
        case "ack":
            break
        default:
            break
        }
    }

    private func postNotification(title: String, message: String) {
        if Self.runningInsideAppBundle {
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = message
            let req = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: nil
            )
            UNUserNotificationCenter.current().add(req, withCompletionHandler: nil)
            return
        }
        // Fallback for unpackaged `swift run` binaries.
        Self.displayNotificationViaAppleScript(title: title, message: message)
    }

    private static var runningInsideAppBundle: Bool {
        Bundle.main.bundleURL.pathExtension == "app"
    }

    private static func displayNotificationViaAppleScript(title: String, message: String) {
        func escape(_ s: String) -> String {
            s
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
        }
        let script =
            "display notification \"\(escape(message))\" with title \"\(escape(title))\""
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        proc.arguments = ["-e", script]
        try? proc.run()
    }

    // MARK: - Paths

    static func resolveRepoRoot() -> URL {
        if let env = ProcessInfo.processInfo.environment["STANDING_ROOT"], !env.isEmpty {
            return URL(fileURLWithPath: env)
        }
        // Release DMG: Python + src live inside the app bundle.
        if let resources = Bundle.main.resourceURL {
            let bundled = resources.appendingPathComponent("StandingPayload")
            if FileManager.default.fileExists(atPath: bundled.appendingPathComponent("src/worker.py").path) {
                return bundled
            }
        }
        // native/Standing → repo root (two levels up from Package.swift directory when running via swift)
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let candidates = [
            cwd,
            cwd.deletingLastPathComponent(),
            cwd.deletingLastPathComponent().deletingLastPathComponent(),
            Bundle.main.bundleURL
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent(),
        ]
        for url in candidates {
            let marker = url.appendingPathComponent("src/worker.py")
            if FileManager.default.fileExists(atPath: marker.path) {
                return url
            }
        }
        // Fallback: walk up from this source file location isn't available at runtime;
        // use cwd and hope the launch script set it.
        return cwd
    }

    static func resolvePython(repoRoot: URL) -> URL {
        if let env = ProcessInfo.processInfo.environment["STANDING_PYTHON"], !env.isEmpty {
            return URL(fileURLWithPath: env)
        }
        let venv = repoRoot.appendingPathComponent(".venv/bin/python3")
        if FileManager.default.isExecutableFile(atPath: venv.path) {
            return venv
        }
        return URL(fileURLWithPath: "/usr/bin/python3")
    }
}
