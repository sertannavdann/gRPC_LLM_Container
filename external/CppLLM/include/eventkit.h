#import <Foundation/Foundation.h>

@class EKEventStore;

@interface EventKitAdapter : NSObject

@property (nonatomic, strong, readonly) EKEventStore *eventStore;

- (instancetype)init;
- (NSString *)createEventWithPerson:(NSString*)person
                                date:(NSDate*)date
                           duration:(NSTimeInterval)duration
                               error:(NSError **)error;

@end
