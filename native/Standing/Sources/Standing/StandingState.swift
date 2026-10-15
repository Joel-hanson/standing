import Foundation

struct StandingState: Equatable, Sendable {
    var posture: String = "unknown"
    var tracking: Bool = false
    var standUps: Int = 0
    var standingSecondsToday: Double = 0
    var sittingSecondsToday: Double = 0
    var standingStreakSeconds: Double = 0
    var sittingStreakSeconds: Double = 0
    var apiCalls: Int = 0
    var inputTokens: Int = 0
    var estimatedCostUsd: Double = 0
    var lastError: String?
    var hasApiKey: Bool = false
    var hasStandingCal: Bool = false
    var hasSittingCal: Bool = false
    var suggestionsEnabled: Bool = true
    var sitWarnMinutes: Double = 30
    var standWarnMinutes: Double = 45
    var calibrationLabel: String = "Calibration: not set"
    var statusTitle: String = "Starting…"
    var barTitle: String = ""
    var barSymbol: String = "pause.circle"
    var usageLabel: String = "—"
    var history: [HistoryDay] = []
    var historyLabel: String = "No activity recorded yet"
    var stravaConnected: Bool = false
    var stravaConfigured: Bool = false
    var stravaLabel: String = "Not connected"
    var stravaUiEnabled: Bool = false

    static let empty = StandingState()

    struct HistoryDay: Equatable, Sendable, Identifiable {
        var id: String { day }
        var day: String
        var standUps: Int
        var standingSeconds: Double
        var sittingSeconds: Double
        var label: String
        var summary: String
    }

    var todayLine: String {
        "Today  \(standUps) stand-ups · Stand \(Self.format(standingSecondsToday)) · Sit \(Self.format(sittingSecondsToday))"
    }

    var setupHint: String? {
        if !hasApiKey { return "1) Add API key  →  2) Calibrate  →  3) Start" }
        if !(hasStandingCal && hasSittingCal) {
            return "\(calibrationLabel) — Settings → Calibration"
        }
        return nil
    }

    static func format(_ seconds: Double) -> String {
        let total = max(0, Int(seconds))
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 { return "\(hours)h \(String(format: "%02d", minutes))m" }
        if minutes > 0 { return "\(minutes)m \(String(format: "%02d", secs))s" }
        return "\(secs)s"
    }

    static func from(json: [String: Any]) -> StandingState {
        var s = StandingState()
        s.posture = json["posture"] as? String ?? "unknown"
        s.tracking = json["tracking"] as? Bool ?? false
        s.standUps = json["stand_ups"] as? Int ?? Int(json["stand_ups"] as? Double ?? 0)
        s.standingSecondsToday = json["standing_seconds_today"] as? Double ?? 0
        s.sittingSecondsToday = json["sitting_seconds_today"] as? Double ?? 0
        s.standingStreakSeconds = json["standing_streak_seconds"] as? Double ?? 0
        s.sittingStreakSeconds = json["sitting_streak_seconds"] as? Double ?? 0
        s.apiCalls = json["api_calls"] as? Int ?? Int(json["api_calls"] as? Double ?? 0)
        s.inputTokens = json["input_tokens"] as? Int ?? Int(json["input_tokens"] as? Double ?? 0)
        s.estimatedCostUsd = json["estimated_cost_usd"] as? Double ?? 0
        s.lastError = json["last_error"] as? String
        s.hasApiKey = json["has_api_key"] as? Bool ?? false
        s.hasStandingCal = json["has_standing_cal"] as? Bool ?? false
        s.hasSittingCal = json["has_sitting_cal"] as? Bool ?? false
        s.suggestionsEnabled = json["suggestions_enabled"] as? Bool ?? true
        s.sitWarnMinutes = json["sit_warn_minutes"] as? Double ?? 30
        s.standWarnMinutes = json["stand_warn_minutes"] as? Double ?? 45
        s.calibrationLabel = json["calibration_label"] as? String ?? "Calibration: not set"
        s.statusTitle = json["status_title"] as? String ?? "—"
        s.barTitle = json["bar_title"] as? String ?? ""
        s.barSymbol = json["bar_symbol"] as? String ?? "pause.circle"
        s.usageLabel = json["usage_label"] as? String ?? "—"
        s.historyLabel = json["history_label"] as? String ?? "No activity recorded yet"
        s.stravaConnected = json["strava_connected"] as? Bool ?? false
        s.stravaConfigured = json["strava_configured"] as? Bool ?? false
        s.stravaLabel = json["strava_label"] as? String ?? "Not connected"
        s.stravaUiEnabled = json["strava_ui_enabled"] as? Bool ?? false
        if let rows = json["history"] as? [[String: Any]] {
            s.history = rows.compactMap { row in
                guard let day = row["day"] as? String else { return nil }
                return HistoryDay(
                    day: day,
                    standUps: row["stand_ups"] as? Int ?? Int(row["stand_ups"] as? Double ?? 0),
                    standingSeconds: row["standing_seconds"] as? Double ?? 0,
                    sittingSeconds: row["sitting_seconds"] as? Double ?? 0,
                    label: row["label"] as? String ?? day,
                    summary: row["summary"] as? String ?? day
                )
            }
        }
        return s
    }
}
