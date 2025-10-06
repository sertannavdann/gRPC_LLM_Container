import AppIntents
import Foundation

public struct ScheduleMeetingIntent: AppIntent {
    public static let title: LocalizedStringResource = "Schedule Meeting"
    public static let description = IntentDescription(
        "Create a calendar event with the supplied attendee, date, and duration.",
        categoryName: "Productivity"
    )

    @Parameter(
        title: "Person",
        description: "Name of the attendee or contact to include in the meeting."
    )
    public var person: String

    @Parameter(
        title: "Date",
        description: "Start date and time for the meeting."
    )
    public var startDate: DateComponents

    @Parameter(
        title: "Duration (minutes)",
        description: "Length of the meeting in minutes.",
        default: 30
    )
    public var durationMinutes: Int

    public init() {}

    public init(person: String, startDate: DateComponents, durationMinutes: Int = 30) {
        self.person = person
        self.startDate = startDate
        self.durationMinutes = durationMinutes
    }

    public func perform() async throws -> some IntentResult & ProvidesDialog {
        // Placeholder implementation. Actual scheduling occurs in the Objective-C++ adapter.
        let summary = "Scheduled meeting with \(person) for \(durationMinutes) minutes"
        return .result(dialog: "✅ \(summary)")
    }
}
