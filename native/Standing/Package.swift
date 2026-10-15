// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Standing",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "Standing", targets: ["Standing"]),
    ],
    dependencies: [
        .package(url: "https://github.com/sparkle-project/Sparkle", from: "2.6.4"),
    ],
    targets: [
        .executableTarget(
            name: "Standing",
            dependencies: [
                .product(name: "Sparkle", package: "Sparkle"),
            ],
            path: "Sources/Standing"
        ),
    ]
)
