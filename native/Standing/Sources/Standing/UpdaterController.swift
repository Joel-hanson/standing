import Foundation
import Sparkle

/// Thin Sparkle wrapper. Inactive until `SUFeedURL` + `SUPublicEDKey` are in Info.plist
/// (set via `STANDING_SPARKLE_FEED_URL` / `STANDING_SPARKLE_PUBLIC_ED_KEY` when packaging).
@MainActor
final class UpdaterController: ObservableObject {
    private var controller: SPUStandardUpdaterController?

    /// True when the app was packaged with a Sparkle feed URL and EdDSA public key.
    var isConfigured: Bool {
        Self.infoString("SUFeedURL") != nil && Self.infoString("SUPublicEDKey") != nil
    }

    init() {
        guard isConfigured else { return }
        controller = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
    }

    func checkForUpdates() {
        guard let controller else { return }
        controller.checkForUpdates(nil)
    }

    private static func infoString(_ key: String) -> String? {
        guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
