import AppIntents

public enum AppIntentCatalog {
    public static let productivityTitle: LocalizedStringResource = "Productivity Actions"

    public static let productivityIntents: [any AppIntent.Type] = [
        ScheduleMeetingIntent.self
    ]
}

public enum AppIntentIdentifiers {
    public static let scheduleMeeting = "cpp_llm.schedule_meeting"
}
