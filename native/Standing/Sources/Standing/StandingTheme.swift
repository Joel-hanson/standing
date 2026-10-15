import SwiftUI

/// Brand colors — keep in sync with `web/index.html` `:root`.
enum StandingTheme {
    static let bgDeep = Color(hex: 0x0A0A0A)
    static let bgSurface = Color(hex: 0x111111)
    static let bgElevated = Color(hex: 0x1A1A1A)
    static let text = Color(hex: 0xFAFAFA)
    static let textSecondary = Color(hex: 0xD4D4D4)
    static let muted = Color(hex: 0xA3A3A3)
    static let line = Color(hex: 0x262626)
    static let primary = Color(hex: 0xDC143C)
    static let primaryHover = Color(hex: 0xB91432)
    static let accent = Color(hex: 0xF8718A)

    /// Chart / status: standing time uses brand crimson.
    static let standing = primary
    /// Chart: sitting time stays quiet so standing reads first.
    static let sitting = muted
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        self.init(.sRGB, red: r, green: g, blue: b, opacity: opacity)
    }
}

extension View {
    /// Dark chrome matching the marketing site.
    func standingChrome() -> some View {
        self
            .preferredColorScheme(.dark)
            .tint(StandingTheme.primary)
    }
}
