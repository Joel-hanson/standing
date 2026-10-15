import Combine
import Foundation
import HealthKit
import os
import UserNotifications

/// Optional Apple Health logging for completed standing-desk bouts (Lane B only).
/// Off by default; when on, writes an `HKWorkout` (not Watch Stand ring time).
@MainActor
final class HealthKitLogger: ObservableObject {
    /// Match Strava’s floor so brief posture flips do not spam Health.
    static let minSeconds: TimeInterval = 600

    @Published private(set) var isEnabled: Bool
    @Published private(set) var isAvailable: Bool
    @Published private(set) var lastError: String?

    private let defaultsKey = "healthkitLoggingEnabled"
    private let store = HKHealthStore()
    private let log = Logger(subsystem: "ai.standing.mac", category: "HealthKit")

    init() {
        isAvailable = HKHealthStore.isHealthDataAvailable()
        isEnabled = UserDefaults.standard.bool(forKey: defaultsKey)
    }

    func setEnabled(_ enabled: Bool) async {
        guard isAvailable else {
            isEnabled = false
            UserDefaults.standard.set(false, forKey: defaultsKey)
            lastError = "Apple Health is not available on this Mac."
            return
        }

        if !enabled {
            isEnabled = false
            UserDefaults.standard.set(false, forKey: defaultsKey)
            lastError = nil
            return
        }

        do {
            try await requestAuthorization()
            // Apple may not reveal write denial via status; treat explicit deny only.
            if store.authorizationStatus(for: HKObjectType.workoutType()) == .sharingDenied {
                isEnabled = false
                UserDefaults.standard.set(false, forKey: defaultsKey)
                lastError = "Health access was denied. Enable Standing in System Settings → Privacy & Security → Health."
                return
            }
            isEnabled = true
            UserDefaults.standard.set(true, forKey: defaultsKey)
            lastError = nil
        } catch {
            isEnabled = false
            UserDefaults.standard.set(false, forKey: defaultsKey)
            lastError = error.localizedDescription
        }
    }

    /// Called when the worker reports a finished standing bout.
    func logStandingBout(elapsedSeconds: TimeInterval, endedAt: Date = Date()) {
        guard isEnabled, isAvailable else { return }
        guard elapsedSeconds >= Self.minSeconds else {
            log.debug("Skip HealthKit log (\(Int(elapsedSeconds))s < \(Int(Self.minSeconds))s)")
            return
        }
        Task {
            await saveWorkout(elapsedSeconds: elapsedSeconds, endedAt: endedAt)
        }
    }

    private func requestAuthorization() async throws {
        let share: Set<HKSampleType> = [HKObjectType.workoutType()]
        try await store.requestAuthorization(toShare: share, read: [])
    }

    private func saveWorkout(elapsedSeconds: TimeInterval, endedAt: Date) async {
        let start = endedAt.addingTimeInterval(-elapsedSeconds)
        let minutes = max(1, Int(elapsedSeconds / 60))
        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .other
        configuration.locationType = .indoor

        do {
            let builder = HKWorkoutBuilder(healthStore: store, configuration: configuration, device: .local())
            try await builder.beginCollection(at: start)
            try await builder.addMetadata([HKMetadataKeyWorkoutBrandName: "Standing"])
            try await builder.endCollection(at: endedAt)
            _ = try await builder.finishWorkout()
            lastError = nil
            log.info("Logged standing bout to Health (\(minutes)m)")
            postNotify(title: "Logged to Apple Health", message: "Standing desk · \(minutes)m")
        } catch {
            lastError = error.localizedDescription
            log.error("HealthKit save failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func postNotify(title: String, message: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = message
        let req = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(req, withCompletionHandler: nil)
    }
}
