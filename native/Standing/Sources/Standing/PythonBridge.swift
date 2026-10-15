import AppKit
import Combine
import Foundation
import UserNotifications

@MainActor
final class PythonBridge: ObservableObject {
    @Published private(set) var state = StandingState.empty
    @Published private(set) var workerReady = false
    @Published private(set) var workerError: String?
    @Published private(set) var apiKeyStatus: String?
    @Published var sitWarnText = "30"
    @Published var standWarnText = "45"
    @Published var apiKeyDraft = ""

    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var readBuffer = Data()
    private var nextId = 1
    private var pendingSaveId: Int?
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
        guard workerIsAlive else {
            workerError = "AI helper is not running. Quit Standing from the menu bar and reopen it, then try again."
            apiKeyStatus = nil
            return
        }
        apiKeyStatus = "Saving…"
        let id = nextId
        nextId += 1
        pendingSaveId = id
        send(cmd: "save_api_key", ["key": key], id: id)
    }

    func clearApiKey() { send(cmd: "clear_api_key") }

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
        if python.path == "/usr/bin/python3", Self.runningInsideAppBundle {
            workerError =
                "Bundled Python is missing. Reinstall Standing from a fresh DMG (or run a dev build)."
        }
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
            // Capture immutable copy — weak `self` is a var and can't cross concurrency boundaries.
            Task { @MainActor [self] in
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
            Task { @MainActor [self] in
                self?.workerReady = false
                if self?.pendingSaveId != nil {
                    self?.pendingSaveId = nil
                    self?.apiKeyStatus = nil
                }
                if proc.terminationStatus != 0 {
                    self?.workerError =
                        "AI helper quit unexpectedly (\(proc.terminationStatus)). Open Settings → Open log, or reinstall Standing."
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

    private var workerIsAlive: Bool {
        workerReady && process?.isRunning == true
    }

    private func send(cmd: String, _ extra: [String: Any] = [:], id: Int? = nil) {
        let reqId: Int
        if let id {
            reqId = id
        } else {
            reqId = nextId
            nextId += 1
        }

        var payload: [String: Any] = ["cmd": cmd, "id": reqId]
        for (k, v) in extra { payload[k] = v }
        guard
            let data = try? JSONSerialization.data(withJSONObject: payload),
            var line = String(data: data, encoding: .utf8)
        else { return }
        line.append("\n")

        guard process?.isRunning == true, let handle = stdinPipe?.fileHandleForWriting else {
            workerReady = false
            workerError = "AI helper is not running — quit and reopen Standing."
            return
        }
        // Avoid FileHandle.write crashing the app on a broken pipe when the worker died.
        do {
            try handle.write(contentsOf: Data(line.utf8))
        } catch {
            workerReady = false
            workerError = "Lost connection to AI helper. Quit and reopen Standing."
            if pendingSaveId != nil {
                pendingSaveId = nil
                apiKeyStatus = nil
            }
        }
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
        case "error":
            workerError = obj["message"] as? String
        case "ack":
            handleAck(obj)
        default:
            break
        }
    }

    private func handleAck(_ obj: [String: Any]) {
        let ackId = obj["id"] as? Int ?? Int(obj["id"] as? Double ?? -1)
        guard ackId == pendingSaveId else { return }
        pendingSaveId = nil
        let ok = obj["ok"] as? Bool ?? false
        if ok {
            apiKeyDraft = ""
            apiKeyStatus = "Saved in Keychain"
            workerError = nil
        } else {
            let err = obj["error"] as? String ?? "Could not save key"
            apiKeyStatus = nil
            workerError = err
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
        // Prefer a real executable (broken venv symlinks must not win).
        let candidates = [
            repoRoot.appendingPathComponent(".venv/bin/python3"),
            repoRoot.appendingPathComponent("python/bin/python3"),
            repoRoot.appendingPathComponent("python/bin/python3.12"),
        ]
        for url in candidates {
            if let resolved = usablePython(at: url) {
                return resolved
            }
        }
        return URL(fileURLWithPath: "/usr/bin/python3")
    }

    /// Returns a resolvable python path, or nil if missing / dangling symlink.
    private static func usablePython(at url: URL) -> URL? {
        let path = url.path
        var isDir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: path, isDirectory: &isDir), !isDir.boolValue else {
            return nil
        }
        let resolved = url.resolvingSymlinksInPath()
        guard FileManager.default.isExecutableFile(atPath: resolved.path) else {
            return nil
        }
        return resolved
    }
}
