import SwiftUI

/// MenuBarExtra label: icon always, streak title only when non-empty.
///
/// SwiftUI drops the icon when `Label { Text("") } icon: { … }` is used, so
/// paused / away / error states (empty `bar_title`) must use `Image` alone.
struct MenuBarStatusLabel: View {
    let title: String
    let systemImage: String

    var body: some View {
        if title.isEmpty {
            Image(systemName: systemImage)
                .accessibilityLabel("Standing")
        } else {
            Label(title, systemImage: systemImage)
        }
    }
}
