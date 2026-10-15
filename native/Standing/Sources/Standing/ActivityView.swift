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
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private var todayHeader: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Today")
                .font(.title2.weight(.semibold))
            Text(bridge.state.statusTitle)
                .foregroundStyle(Color.secondary)
            Text(bridge.state.todayLine)
                .font(.body.monospacedDigit())
        }
    }

    private var dayList: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recent days")
                .font(.headline)

            if bridge.state.history.isEmpty {
                Text(bridge.state.historyLabel)
                    .foregroundStyle(Color.secondary)
            } else {
                ForEach(Array(bridge.state.history.prefix(14))) { day in
                    HStack(alignment: .firstTextBaseline) {
                        Text(day.label)
                            .frame(width: 88, alignment: .leading)
                        Text(
                            "\(day.standUps) stand-ups · Stand \(StandingState.format(day.standingSeconds)) · Sit \(StandingState.format(day.sittingSeconds))"
                        )
                        .font(.subheadline)
                        .foregroundStyle(Color.secondary)
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
            Text(bridge.state.usageLabel)
                .font(.subheadline)
                .foregroundStyle(Color.secondary)
        }
    }
}
