// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "MemoryMenubar",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MemoryMenubar", targets: ["MemoryMenubar"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "MemoryMenubar",
            dependencies: [],
            path: ".",
            sources: ["MemoryMenubar.swift"]
        )
    ]
)