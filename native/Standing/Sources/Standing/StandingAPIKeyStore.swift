import Foundation

/// Local API key storage for the Swift shell.
///
/// Uses Application Support (mode 0600) — not Keychain. Ad-hoc / frequently
/// re-signed builds cannot keep a stable Keychain ACL, which caused endless
/// “Standing wants to use your confidential information…” prompts.
enum StandingAPIKeyStore {
    private static let fileName = "api_key"

    private static var fileURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Standing", isDirectory: true)
            .appendingPathComponent(fileName)
    }

    static func get() -> String? {
        let url = fileURL
        guard let data = try? Data(contentsOf: url),
              let value = String(data: data, encoding: .utf8)?
              .trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty
        else { return nil }
        return value
    }

    static func set(_ key: String) throws {
        let cleaned = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { throw StoreError.empty }
        let dir = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Data(cleaned.utf8).write(to: fileURL, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: fileURL.path
        )
    }

    static func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }

    enum StoreError: LocalizedError {
        case empty

        var errorDescription: String? {
            switch self {
            case .empty:
                return "API key cannot be empty"
            }
        }
    }
}
