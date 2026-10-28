// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "PitPatMenuBar",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "PitPatMenuBar"),
        .testTarget(name: "PitPatMenuBarTests", dependencies: ["PitPatMenuBar"]),
    ]
)
