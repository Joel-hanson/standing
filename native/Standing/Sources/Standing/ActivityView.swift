import SwiftUI

/// Dedicated activity window — chart, day history, and today's usage.
struct ActivityView: View {
    @EnvironmentObject private var bridge: PythonBridge

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                todayHeader

                ActivityHistoryChart(days: bridge.state.weekForChart())

                dayList

                usageBlock

                HStack {
                    Button("Reset Today…", role: .destructive) {
                        bridge.resetDay()
                    }
                    Spacer()
                }
            }
            .padding(20)
        }
        .frame(minWidth: 420, idealWidth: 440, minHeight: 480)
        .background(StandingTheme.bgDeep)
        .standingChrome()
    }

    private var todayHeader: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Today")
                .font(.title2.weight(.semibold))
                .foregroundStyle(StandingTheme.text)
            Text(bridge.state.statusTitle)
                .foregroundStyle(StandingTheme.muted)
            Text(bridge.state.todayLine)
                .font(.body.monospacedDigit())
                .foregroundStyle(StandingTheme.textSecondary)
        }
    }

    private var dayList: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recent days")
                .font(.headline)
                .foregroundStyle(StandingTheme.text)

            if bridge.state.history.isEmpty {
                Text(bridge.state.historyLabel)
                    .foregroundStyle(StandingTheme.muted)
            } else {
                ForEach(Array(bridge.state.history.prefix(14))) { day in
                    HStack(alignment: .firstTextBaseline) {
                        Text(day.label)
                            .frame(width: 88, alignment: .leading)
                            .foregroundStyle(StandingTheme.textSecondary)
                        Text(
                            "\(day.standUps) stand-ups · Stand \(StandingState.format(day.standingSeconds)) · Sit \(StandingState.format(day.sittingSeconds))"
                        )
                        .font(.subheadline)
                        .foregroundStyle(StandingTheme.muted)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private var usageBlock: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Usage today")
                .font(.headline)
                .foregroundStyle(StandingTheme.text)
            Text(bridge.state.usageLabel)
                .font(.subheadline)
                .foregroundStyle(StandingTheme.muted)
        }
    }
}
