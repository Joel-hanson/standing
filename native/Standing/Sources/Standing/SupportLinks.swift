import Foundation

/// One-time Support — app stays fully free; no feature locks.
/// Keep in sync with `src/support.py` (or set STANDING_SUPPORT_URL for the Python shell).
enum SupportLinks {
    static let oneTimeURL = URL(string: "https://gumroad.com/l/standing")!
}
