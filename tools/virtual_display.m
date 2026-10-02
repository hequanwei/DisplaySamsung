/**
 * virtual_display.m
 * macOS 原生轻量虚拟显示器命令行工具 (支持横竖屏方向自适应与多方位排布)
 * 基于 CoreGraphics 私有 CGVirtualDisplay API 实现。
 * 支持横屏 (2800x1752) 与竖屏 (1752x2800) HiDPI 自由切换，支持摆放位置（左/右/上/下）即时调节。
 */

#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <signal.h>
#import <unistd.h>

// 声明 CoreGraphics 获取显示器 UUID 函数
extern CFUUIDRef CGDisplayCreateUUIDFromDisplayID(CGDirectDisplayID display);

// 私有 CoreGraphics 虚拟显示器类声明
@interface CGVirtualDisplayDescriptor : NSObject
@property (nonatomic, copy) NSString *name;
@property (nonatomic, assign) uint32_t maxPixelsWide;
@property (nonatomic, assign) uint32_t maxPixelsHigh;
@property (nonatomic, assign) CGSize sizeInMillimeters;
@property (nonatomic, assign) uint32_t productID;
@property (nonatomic, assign) uint32_t vendorID;
@property (nonatomic, assign) uint32_t serialNum;
@property (nonatomic, strong) dispatch_queue_t queue;
@property (nonatomic, copy) id terminationHandler;
@end

@interface CGVirtualDisplayMode : NSObject
@property (nonatomic, readonly) uint32_t width;
@property (nonatomic, readonly) uint32_t height;
@property (nonatomic, readonly) double refreshRate;
- (instancetype)initWithWidth:(uint32_t)width height:(uint32_t)height refreshRate:(double)refreshRate;
@end

@interface CGVirtualDisplaySettings : NSObject
@property (nonatomic, strong) NSArray *modes;
@property (nonatomic, assign) uint32_t hiDPI;
@end

@interface CGVirtualDisplay : NSObject
@property (nonatomic, readonly) CGDirectDisplayID displayID;
- (instancetype)initWithDescriptor:(CGVirtualDisplayDescriptor *)descriptor;
- (BOOL)applySettings:(CGVirtualDisplaySettings *)settings;
@end

static CGVirtualDisplay *g_virtualDisplay = nil;

// 信号处理：退出 RunLoop
static void handle_signal(int sig) {
    (void)sig;
    CFRunLoopStop(CFRunLoopGetMain());
}

// 调整副屏相对主屏幕的摆放位置 (left, right, top, bottom)
static void apply_display_position(CGDirectDisplayID virtualID, NSString *position, uint32_t virtW, uint32_t virtH) {
    CGDirectDisplayID mainID = CGMainDisplayID();
    CGRect mainBounds = CGDisplayBounds(mainID);

    // 默认以 2x Retina 逻辑尺寸计算跨屏距离
    int32_t logicalW = (int32_t)(virtW / 2);
    int32_t logicalH = (int32_t)(virtH / 2);

    int32_t originX = (int32_t)mainBounds.size.width;
    int32_t originY = 0;

    if ([position isEqualToString:@"left"]) {
        originX = -logicalW;
        originY = 0;
    } else if ([position isEqualToString:@"right"]) {
        originX = (int32_t)mainBounds.size.width;
        originY = 0;
    } else if ([position isEqualToString:@"top"]) {
        originX = 0;
        originY = -logicalH;
    } else if ([position isEqualToString:@"bottom"]) {
        originX = 0;
        originY = (int32_t)mainBounds.size.height;
    }

    CGDisplayConfigRef configRef;
    if (CGBeginDisplayConfiguration(&configRef) == kCGErrorSuccess) {
        CGConfigureDisplayOrigin(configRef, virtualID, originX, originY);
        CGCompleteDisplayConfiguration(configRef, kCGConfigurePermanently);
    }
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        // 注册退出信号
        signal(SIGINT, handle_signal);
        signal(SIGTERM, handle_signal);

        // 解析参数
        uint32_t width = 2800;
        uint32_t height = 1752;
        uint32_t hidpi = 1;
        NSString *name = @"SamsungTab";
        NSString *position = @"right"; // 默认在右侧

        for (int i = 1; i < argc; i++) {
            NSString *arg = [NSString stringWithUTF8String:argv[i]];
            if ([arg isEqualToString:@"--width"] && i + 1 < argc) {
                width = (uint32_t)atoi(argv[++i]);
            } else if ([arg isEqualToString:@"--height"] && i + 1 < argc) {
                height = (uint32_t)atoi(argv[++i]);
            } else if ([arg isEqualToString:@"--hidpi"] && i + 1 < argc) {
                hidpi = (uint32_t)atoi(argv[++i]);
            } else if ([arg isEqualToString:@"--name"] && i + 1 < argc) {
                name = [NSString stringWithUTF8String:argv[++i]];
            } else if ([arg isEqualToString:@"--position"] && i + 1 < argc) {
                position = [NSString stringWithUTF8String:argv[++i]];
            }
        }

        // 构造虚拟显示器描述符
        CGVirtualDisplayDescriptor *descriptor = [[CGVirtualDisplayDescriptor alloc] init];
        descriptor.name = name;
        descriptor.maxPixelsWide = MAX(width, height);
        descriptor.maxPixelsHigh = MAX(width, height);
        
        // 物理尺寸根据横竖屏动态切换
        if (width >= height) {
            descriptor.sizeInMillimeters = CGSizeMake(267, 167); // 横屏
        } else {
            descriptor.sizeInMillimeters = CGSizeMake(167, 267); // 竖屏
        }
        descriptor.productID = 0x2800;
        descriptor.vendorID = 0x1752;
        descriptor.serialNum = (uint32_t)time(NULL);
        descriptor.queue = dispatch_get_main_queue();

        g_virtualDisplay = [[CGVirtualDisplay alloc] initWithDescriptor:descriptor];
        if (!g_virtualDisplay) {
            printf("{\"status\": \"error\", \"message\": \"Failed to create CGVirtualDisplay\"}\n");
            fflush(stdout);
            return 1;
        }

        CGVirtualDisplaySettings *settings = [[CGVirtualDisplaySettings alloc] init];
        
        // 动态根据宽高比例自适应生成缩放档位列表（完美支持横屏和竖屏！）
        NSMutableArray *modeList = [NSMutableArray array];
        double scaleFactors[] = {1.0, 0.8, 0.6, 0.5}; // 1.0 原生，0.5 黄金 2x Retina
        for (int s = 0; s < 4; s++) {
            uint32_t w = (uint32_t)(width * scaleFactors[s]);
            uint32_t h = (uint32_t)(height * scaleFactors[s]);
            // 注册 60Hz 与 120Hz 高刷
            [modeList addObject:[[CGVirtualDisplayMode alloc] initWithWidth:w height:h refreshRate:60.0]];
            [modeList addObject:[[CGVirtualDisplayMode alloc] initWithWidth:w height:h refreshRate:120.0]];
        }

        settings.modes = modeList;
        settings.hiDPI = hidpi;

        if (![g_virtualDisplay applySettings:settings]) {
            printf("{\"status\": \"error\", \"message\": \"Failed to apply display settings\"}\n");
            fflush(stdout);
            return 2;
        }

        CGDirectDisplayID displayID = g_virtualDisplay.displayID;
        
        // 应用摆放位置（左/右/上/下）
        apply_display_position(displayID, position, width, height);

        CFUUIDRef uuidRef = CGDisplayCreateUUIDFromDisplayID(displayID);
        NSString *uuidStr = @"";
        if (uuidRef) {
            CFStringRef cfStr = CFUUIDCreateString(kCFAllocatorDefault, uuidRef);
            uuidStr = (__bridge_transfer NSString *)cfStr;
            CFRelease(uuidRef);
        }

        // 输出 JSON 供上层调度器捕获
        printf("{\"status\": \"ok\", \"display_id\": %u, \"uuid\": \"%s\", \"width\": %u, \"height\": %u, \"hidpi\": %u, \"position\": \"%s\"}\n",
               displayID, [uuidStr UTF8String], width, height, hidpi, [position UTF8String]);
        fflush(stdout);

        // 异步监听 stdin：支持运行时动态调整位置和优雅退出
        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            char buffer[256];
            while (read(STDIN_FILENO, buffer, sizeof(buffer) - 1) > 0) {
                buffer[sizeof(buffer) - 1] = '\0';
                NSString *input = [[NSString stringWithUTF8String:buffer] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
                if ([input isEqualToString:@"quit"] || [input isEqualToString:@"stop"]) {
                    break;
                } else if ([input hasPrefix:@"position "]) {
                    NSString *newPos = [input substringFromIndex:9];
                    dispatch_async(dispatch_get_main_queue(), ^{
                        apply_display_position(displayID, newPos, width, height);
                    });
                }
            }
            CFRunLoopStop(CFRunLoopGetMain());
        });

        // 维持事件循环
        CFRunLoopRun();

        // 销毁并退出
        g_virtualDisplay = nil;
    }
    return 0;
}
