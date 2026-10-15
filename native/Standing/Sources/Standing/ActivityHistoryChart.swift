import Charts
import SwiftUI

/// Last-7-days stand vs sit time as stacked bars (minutes).
struct ActivityHistoryChart: View {
    let days: [StandingState.HistoryDay]

    private struct BarPoint: Identifiable {
        var id: String { "\(day)-\(kind)" }
        let day: String
        let shortLabel: String
        let minutes: Double
        let kind: String
        let standUps: Int
    }

    private var bars: [BarPoint] {
        days.flatMap { day in
            let label = Self.axisLabel(for: day)
            return [
                BarPoint(
                    day: day.day,
                    shortLabel: label,
                    minutes: day.standingSeconds / 60.0,
                    kind: "Standing",
                    standUps: day.standUps
                ),
                BarPoint(
                    day: day.day,
                    shortLabel: label,
                    minutes: day.sittingSeconds / 60.0,
                    kind: "Sitting",
                    standUps: day.standUps
                ),
            ]
        }
    }

    private var hasAnyMinutes: Bool {
        days.contains { $0.standingSeconds >= 1 || $0.sittingSeconds >= 1 }
    }

    private let standColor = StandingTheme.standing
    private let sitColor = StandingTheme.sitting

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Chart(bars) { point in
                BarMark(
                    x: .value("Day", point.shortLabel),
                    y: .value("Minutes", point.minutes)
                )
                .foregroundStyle(by: .value("Kind", point.kind))
                .annotation(position: .top, spacing: 2) {
                    // Annotate once per day (on the Standing series).
                    if point.kind == "Standing", point.standUps > 0 {
                        Text("\(point.standUps)")
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .foregroundStyle(StandingTheme.muted)
                    }
                }
            }
            .chartForegroundStyleScale([
                "Standing": standColor,
                "Sitting": sitColor,
            ])
            .chartLegend(position: .bottom, alignment: .leading)
            .chartYAxisLabel("minutes", position: .leading, alignment: .center)
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                    AxisValueLabel {
                        if let n = value.as(Double.self) {
                            Text("\(Int(n.rounded()))")
                                .font(.caption2)
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks { _ in
                    AxisValueLabel()
                        .font(.caption2)
                }
            }
            .frame(height: 160)
            .opacity(hasAnyMinutes ? 1 : 0.45)

            Text("Numbers above bars are stand-ups that day.")
                .font(.caption2)
                .foregroundStyle(StandingTheme.muted)

            if !hasAnyMinutes {
                Text("Track for a bit — the chart fills as days accumulate.")
                    .font(.caption)
                    .foregroundStyle(StandingTheme.muted)
            }
        }
    }

    private static func axisLabel(for day: StandingState.HistoryDay) -> String {
        if day.label == "Today" {
            return "Today"
        }
        if day.label == "Yesterday" {
            return "Yday"
        }
        let parts = day.label.split(separator: " ")
        if let last = parts.last {
            return String(last)
        }
        return String(day.day.suffix(2))
    }
}

extension StandingState {
    /// Oldest → newest calendar window for the chart (fills missing days with zeros).
    func weekForChart(days count: Int = 7) -> [HistoryDay] {
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        let iso = DateFormatter()
        iso.calendar = cal
        iso.locale = Locale(identifier: "en_US_POSIX")
        iso.dateFormat = "yyyy-MM-dd"

        var byDay: [String: HistoryDay] = [:]
        for row in history {
            byDay[row.day] = row
        }

        let todayKey = iso.string(from: today)
        byDay[todayKey] = HistoryDay(
            day: todayKey,
            standUps: standUps,
            standingSeconds: standingSecondsToday,
            sittingSeconds: sittingSecondsToday,
            label: "Today",
            summary: todayLine
        )

        var out: [HistoryDay] = []
        for offset in stride(from: count - 1, through: 0, by: -1) {
            guard let date = cal.date(byAdding: .day, value: -offset, to: today) else { continue }
            let key = iso.string(from: date)
            if let existing = byDay[key] {
                out.append(existing)
            } else {
                let label: String
                if offset == 0 {
                    label = "Today"
                } else if offset == 1 {
                    label = "Yesterday"
                } else {
                    let short = DateFormatter()
                    short.dateFormat = "MMM d"
                    label = short.string(from: date)
                }
                out.append(
                    HistoryDay(
                        day: key,
                        standUps: 0,
                        standingSeconds: 0,
                        sittingSeconds: 0,
                        label: label,
                        summary: "\(label)  ·  no activity"
                    )
                )
            }
        }
        return out
    }
}
