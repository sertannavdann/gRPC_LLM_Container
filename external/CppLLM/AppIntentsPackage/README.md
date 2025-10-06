# AppIntentsPackage

Shared Swift package that defines App Intents used by the CppLLM microservice and its extensions. Sprint 1 delivers the
initial "Schedule Meeting" action, exposing it to both the iOS/macOS Host app and the Intents extension for Siri Shortcuts.

## Contents

- `ScheduleMeetingIntent`: An `AppIntent` placeholder that captures a contact name, start date, and duration.
- `AppIntentCatalog`: Convenience accessors for bundling intent groups.
- `AppIntentIdentifiers`: String constants for cross-language lookups (e.g., from Objective-C++ and gRPC handlers).

## Usage

Add the package to your Xcode project and reference `ProductivityIntentCollection` from both the main app and the Intents
extension. During Sprint 2 the CppLLM gRPC handlers will invoke these intents directly using the identifiers above.

```swift
import AppIntentsPackage

let intents = AppIntentCatalog.productivityIntents
```

Run the unit tests from the package root:

```bash
swift test
```

> **Note:** The `perform()` implementation is a stub. The real calendar interaction happens in Objective-C++ adapters during
Sprint 2 after the gRPC bridge is in place.
