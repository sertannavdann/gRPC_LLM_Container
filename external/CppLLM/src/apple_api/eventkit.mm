// EventKit adapter implementation
#import "../../include/eventkit.h"
#import "../../include/eventkit_bridge.h"

#import <EventKit/EventKit.h>
#import <Foundation/Foundation.h>

static NSString *const kEventKitAdapterErrorDomain = @"CppLLM.EventKitAdapter";

@implementation EventKitAdapter

@synthesize eventStore = _eventStore;

- (instancetype)init {
    self = [super init];
    if (self) {
        _eventStore = [[EKEventStore alloc] init];
    }
    return self;
}

- (NSString *)createEventWithPerson:(NSString*)person
                                date:(NSDate*)date
                           duration:(NSTimeInterval)duration
                               error:(NSError **)error {
    if (!self.eventStore) {
        NSLog(@"[EventKitAdapter] Event store unavailable");
        if (error) {
            *error = [NSError errorWithDomain:kEventKitAdapterErrorDomain
                                         code:1
                                     userInfo:@{NSLocalizedDescriptionKey: @"Event store unavailable"}];
        }
        return nil;
    }

    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    __block BOOL granted = NO;
    [self.eventStore requestAccessToEntityType:EKEntityTypeEvent
                                    completion:^(BOOL accessGranted, NSError * _Nullable error) {
        granted = accessGranted;
        if (error) {
            NSLog(@"[EventKitAdapter] Access request error: %@", error);
        }
        dispatch_semaphore_signal(semaphore);
    }];

    dispatch_time_t timeout = dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3 * NSEC_PER_SEC));
    if (dispatch_semaphore_wait(semaphore, timeout) != 0 || !granted) {
        NSLog(@"[EventKitAdapter] Event permission denied or timed out");
        if (error) {
            *error = [NSError errorWithDomain:kEventKitAdapterErrorDomain
                                         code:2
                                     userInfo:@{NSLocalizedDescriptionKey: @"Event permission denied or timed out"}];
        }
        return nil;
    }

    EKEvent *event = [EKEvent eventWithEventStore:self.eventStore];
    event.title = [NSString stringWithFormat:@"Meeting with %@", person ?: @"Unknown"];
    event.startDate = date ?: [NSDate date];
    event.endDate = [event.startDate dateByAddingTimeInterval:duration > 0 ? duration : 30 * 60];
    event.calendar = [self.eventStore defaultCalendarForNewEvents];

    NSError *saveError = nil;
    BOOL success = [self.eventStore saveEvent:event span:EKSpanThisEvent commit:YES error:&saveError];
    if (!success || saveError) {
        NSLog(@"[EventKitAdapter] Failed to save event: %@", saveError);
        if (error) {
            *error = saveError ?: [NSError errorWithDomain:kEventKitAdapterErrorDomain
                                                      code:3
                                                  userInfo:@{NSLocalizedDescriptionKey: @"Failed to save event"}];
        }
        return nil;
    }

    NSLog(@"[EventKitAdapter] Event saved with identifier: %@", event.eventIdentifier);
    return event.eventIdentifier;
}

@end

EventCreationResult createCalendarEvent(const std::string& person,
                                        const std::string& isoStartTime,
                                        int durationMinutes) {
    EventCreationResult result;
    result.success = false;
    result.message.clear();
    result.event_identifier.clear();

    @autoreleasepool {
        EventKitAdapter *adapter = [[EventKitAdapter alloc] init];
        if (!adapter) {
            result.message = "Failed to initialize EventKitAdapter";
            return result;
        }

        NSDate *startDate = nil;
        if (!isoStartTime.empty()) {
            NSString *isoString = [NSString stringWithUTF8String:isoStartTime.c_str()];
            NSISO8601DateFormatter *formatter = [[NSISO8601DateFormatter alloc] init];
            startDate = [formatter dateFromString:isoString];
            if (!startDate) {
                result.message = "Invalid start_time_iso8601 value";
                return result;
            }
        } else {
            startDate = [NSDate date];
        }

        NSTimeInterval duration = durationMinutes > 0 ? durationMinutes * 60.0 : 30 * 60.0;
        NSString *personString = [NSString stringWithUTF8String:person.c_str()];
        NSError *error = nil;

        NSString *identifier = [adapter createEventWithPerson:personString
                                                         date:startDate
                                                    duration:duration
                                                        error:&error];

        if (identifier) {
            result.success = true;
            result.event_identifier = [identifier UTF8String];
            result.message = "Event scheduled";
        } else {
            NSString *errorMessage = error.localizedDescription ?: @"Unknown EventKit error";
            result.message = [errorMessage UTF8String];
        }
    }

    return result;
}
