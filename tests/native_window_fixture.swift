// Disposable native acceptance fixture. Launch the signed bundle with open -g.
import Cocoa
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let window = NSWindow(contentRect: NSRect(x: 40, y: 40, width: 360, height: 160),
                      styleMask: [.titled], backing: .buffered, defer: false)
window.title = "GUI Harness background acceptance"
let field = NSTextField(frame: NSRect(x: 20, y: 80, width: 300, height: 30))
field.stringValue = "before"
field.setAccessibilityLabel("Acceptance text")
window.contentView!.addSubview(field)
class Target: NSObject {
    @objc func clicked(_ sender: Any?) { field.stringValue = "pressed" }
}
let target = Target()
let button = NSButton(title: "Acceptance press", target: target, action: #selector(Target.clicked(_:)))
button.frame = NSRect(x: 20, y: 30, width: 160, height: 30)
window.contentView!.addSubview(button)
window.orderBack(nil)
app.run()
