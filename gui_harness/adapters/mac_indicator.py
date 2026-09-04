"""Native, non-activating macOS feedback for one controlled window."""

from __future__ import annotations

import json
import os
import select
import sys


TITLE = "OpenProgram GUI Agent control"


def _bounds(row):
    value = row.get("kCGWindowBounds") or {}
    try:
        return tuple(float(value[key]) for key in ("X", "Y", "Width", "Height"))
    except (KeyError, TypeError, ValueError):
        return None


def _overlaps(left, right):
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


def visible_target(rows, window_id, target_pid, owner_pid):
    """Return the live target bounds only while no unrelated window covers it."""
    target_index = next(
        (index for index, row in enumerate(rows)
         if int(row.get("kCGWindowNumber", -1)) == window_id
         and int(row.get("kCGWindowOwnerPID", -1)) == target_pid),
        None,
    )
    if target_index is None:
        return None
    target = _bounds(rows[target_index])
    if target is None or target[2] <= 1 or target[3] <= 1:
        return None
    for row in rows[:target_index]:
        if int(row.get("kCGWindowOwnerPID", -1)) == owner_pid:
            continue
        layer = int(row.get("kCGWindowLayer", 0))
        if layer < 0 or layer > 3:
            continue
        other = _bounds(row)
        if other and float(row.get("kCGWindowAlpha", 1)) > 0 and _overlaps(other, target):
            return None
    return target


def _symbol(appkit, name, fallback):
    image = appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    return image or appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        fallback, None,
    )


def _color(appkit, red, green, blue, alpha):
    return appkit.NSColor.colorWithSRGBRed_green_blue_alpha_(red, green, blue, alpha)


class Indicator:
    def __init__(self, appkit, window_id, target_pid, app_name):
        self.appkit = appkit
        self.window_id = window_id
        self.target_pid = target_pid
        self.action = None
        self.action_bounds = None
        style = appkit.NSWindowStyleMaskBorderless | appkit.NSWindowStyleMaskNonactivatingPanel
        panel = appkit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            appkit.NSMakeRect(0, 0, 100, 100), style, appkit.NSBackingStoreBuffered, False,
        )
        panel.setTitle_(TITLE)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(appkit.NSColor.clearColor())
        panel.setHasShadow_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setLevel_(appkit.NSFloatingWindowLevel)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(
            appkit.NSWindowCollectionBehaviorTransient
            | appkit.NSWindowCollectionBehaviorIgnoresCycle
        )
        content = appkit.NSView.alloc().initWithFrame_(appkit.NSMakeRect(0, 0, 100, 100))
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(appkit.NSColor.clearColor().CGColor())
        panel.setContentView_(content)

        badge = appkit.NSView.alloc().initWithFrame_(appkit.NSMakeRect(12, 62, 224, 28))
        badge.setWantsLayer_(True)
        badge.layer().setCornerRadius_(14)
        badge.layer().setBackgroundColor_(_color(appkit, 0.35, 0.27, 0.92, 0.94).CGColor())
        content.addSubview_(badge)
        icon = appkit.NSImageView.alloc().initWithFrame_(appkit.NSMakeRect(8, 6, 16, 16))
        icon.setImage_(_symbol(appkit, "rectangle.inset.filled.and.person.filled", "display"))
        icon.setContentTintColor_(appkit.NSColor.whiteColor())
        badge.addSubview_(icon)
        label = appkit.NSTextField.labelWithString_(f"GUI Agent · {app_name}")
        label.setFrame_(appkit.NSMakeRect(30, 5, 186, 18))
        label.setTextColor_(appkit.NSColor.whiteColor())
        label.setFont_(appkit.NSFont.systemFontOfSize_weight_(12, appkit.NSFontWeightSemibold))
        label.setLineBreakMode_(appkit.NSLineBreakByTruncatingTail)
        badge.addSubview_(label)

        marker = appkit.NSView.alloc().initWithFrame_(appkit.NSMakeRect(-100, -100, 42, 42))
        marker.setWantsLayer_(True)
        marker.layer().setCornerRadius_(21)
        marker.layer().setBackgroundColor_(_color(appkit, 0.35, 0.27, 0.92, 0.30).CGColor())
        marker.layer().setBorderColor_(_color(appkit, 0.35, 0.27, 0.92, 0.94).CGColor())
        marker.layer().setBorderWidth_(2)
        marker.setHidden_(True)
        content.addSubview_(marker)
        marker_icon = appkit.NSImageView.alloc().initWithFrame_(appkit.NSMakeRect(9, 9, 24, 24))
        marker_icon.setContentTintColor_(appkit.NSColor.whiteColor())
        marker.addSubview_(marker_icon)

        self.panel = panel
        self.content = content
        self.badge = badge
        self.marker = marker
        self.marker_icon = marker_icon

    def set_action(self, action, bounds):
        self.action = action if isinstance(action, str) else None
        self.action_bounds = bounds if isinstance(bounds, dict) else None

    def update(self, rows):
        target = visible_target(
            rows, self.window_id, self.target_pid, os.getpid(),
        )
        if target is None:
            self.panel.orderOut_(None)
            return
        x, y, width, height = target
        main_top = self.appkit.NSMaxY(self.appkit.NSScreen.mainScreen().frame())
        frame = self.appkit.NSMakeRect(x, main_top - y - height, width, height)
        self.panel.setFrame_display_(frame, True)
        self.content.setFrame_(self.appkit.NSMakeRect(0, 0, width, height))
        self.badge.setFrameOrigin_(self.appkit.NSMakePoint(12, max(0, height - 38)))
        bounds = self.action_bounds
        if bounds:
            marker_x = bounds.get("x", x) - x + bounds.get("width", 0) / 2 - 21
            marker_y = height - (bounds.get("y", y) - y + bounds.get("height", 0) / 2) - 21
            self.marker.setFrameOrigin_(self.appkit.NSMakePoint(marker_x, marker_y))
            symbol = {
                "window_press": "cursorarrow",
                "window_set_text": "text.cursor",
                "window_scroll": "arrow.up.and.down",
            }.get(self.action, "cursorarrow")
            self.marker_icon.setImage_(_symbol(self.appkit, symbol, "cursorarrow"))
            self.marker.setHidden_(False)
        else:
            self.marker.setHidden_(True)
        self.panel.orderFrontRegardless()
        self.panel.displayIfNeeded()

    def close(self):
        self.panel.orderOut_(None)
        self.panel.close()


def main(argv=None):
    import AppKit
    import Quartz

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        return 2
    window_id, target_pid, app_name = int(args[0]), int(args[1]), args[2]
    app = AppKit.NSApplication.sharedApplication()
    app.finishLaunching()
    indicator = Indicator(AppKit, window_id, target_pid, app_name)
    try:
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if ready:
                line = sys.stdin.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                except ValueError:
                    continue
                indicator.set_action(payload.get("action"), payload.get("bounds"))
            rows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
            ) or []
            indicator.update(rows)
            AppKit.NSRunLoop.currentRunLoop().runUntilDate_(
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.01),
            )
    finally:
        indicator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
