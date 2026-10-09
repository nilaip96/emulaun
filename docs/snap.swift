// Screenshot a page with WebKit (same engine as the app), for README images.
// usage: snap <url> <out.png> <width> <height> [wait-seconds]
import Cocoa
import WebKit

let args = CommandLine.arguments
guard args.count >= 5, let url = URL(string: args[1]), let w = Double(args[3]), let h = Double(args[4]) else {
    print("usage: snap <url> <out.png> <width> <height> [wait-seconds]"); exit(2)
}
let out = args[2]
let wait = args.count > 5 ? Double(args[5]) ?? 4 : 4

class Snapper: NSObject, WKNavigationDelegate {
    let web: WKWebView
    let window: NSWindow
    init(_ size: NSSize) {
        let cfg = WKWebViewConfiguration()
        // offscreen windows count as hidden, which pauses CSS transitions mid-way; turn them off
        let css = "*,*::before,*::after{transition:none!important;animation:none!important}"
        cfg.userContentController.addUserScript(WKUserScript(
            source: "document.documentElement.appendChild(Object.assign(document.createElement('style'),{textContent:'\(css)'}))",
            injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        web = WKWebView(frame: NSRect(origin: .zero, size: size), configuration: cfg)
        window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered, defer: false)
        super.init()
        window.contentView = web
        window.setFrameOrigin(NSPoint(x: -10000, y: -10000))  // offscreen
        window.orderFront(nil)
        web.navigationDelegate = self
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
            let cfg = WKSnapshotConfiguration()
            webView.takeSnapshot(with: cfg) { image, _ in
                guard let image = image, let tiff = image.tiffRepresentation,
                      let rep = NSBitmapImageRep(data: tiff), let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
                try! png.write(to: URL(fileURLWithPath: out))
                exit(0)
            }
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let snapper = Snapper(NSSize(width: w, height: h))
snapper.web.load(URLRequest(url: url))
DispatchQueue.main.asyncAfter(deadline: .now() + wait + 20) { exit(3) }
app.run()
