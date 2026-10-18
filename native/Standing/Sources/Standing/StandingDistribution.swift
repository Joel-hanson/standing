import Foundation

/// How this binary was packaged. Baked into Info.plist as `StandingDistribution`.
enum StandingDistribution: String {
    case development
    case direct // notarized DMG + optional Sparkle
    case mas // Mac App Store (sandbox, no Sparkle updates)

    static var current: StandingDistribution {
        let raw = (Bundle.main.object(forInfoDictionaryKey: "StandingDistribution") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        switch raw {
        case "mas":
            return .mas
        case "direct":
            return .direct
        default:
            return .development
        }
    }

    var isMacAppStore: Bool { self == .mas }
}
