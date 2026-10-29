// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "PitPatMenuBar",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "PitPatMenuBar"),
        .executableTarget(name: "PitPatSafety"),
        .testTarget(name: "PitPatMenuBarTests", dependencies: ["PitPatMenuBar"]),
    ]
)
