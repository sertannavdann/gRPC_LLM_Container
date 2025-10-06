import XCTest
@testable import AppIntentsPackage

final class ScheduleMeetingIntentTests: XCTestCase {
    func testIntentMetadata() {
        XCTAssertEqual(ScheduleMeetingIntent.title, "Schedule Meeting")
        XCTAssertTrue(String(describing: ScheduleMeetingIntent.description).contains("calendar"))
    }

    func testIntentInit() throws {
        var components = DateComponents()
        components.year = 2025
        components.month = 10
        components.day = 5
        components.hour = 14
        components.minute = 0

        let intent = ScheduleMeetingIntent(person: "Alex", startDate: components, durationMinutes: 45)
        XCTAssertEqual(intent.person, "Alex")
        XCTAssertEqual(intent.durationMinutes, 45)
        XCTAssertEqual(intent.startDate.hour, 14)
    }
}
