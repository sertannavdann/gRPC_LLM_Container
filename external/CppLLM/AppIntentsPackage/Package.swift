// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AppIntentsPackage",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "AppIntentsPackage",
            targets: ["AppIntentsPackage"]
        )
    ],
    targets: [
        .target(
            name: "AppIntentsPackage",
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .testTarget(
            name: "AppIntentsPackageTests",
            dependencies: ["AppIntentsPackage"]
        )
    ]
)
