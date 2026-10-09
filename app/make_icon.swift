// Draws the Emulaunch app icon (a game cartridge with a launch button) and writes an .iconset folder.
// usage: swift make_icon.swift <out.iconset>
import AppKit

func color(_ hex: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: a)
}

func draw(size s: CGFloat) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(s), pixelsHigh: Int(s), bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let k = s / 1024  // design on a 1024 grid

    func R(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> NSRect { NSRect(x: x * k, y: y * k, width: w * k, height: h * k) }

    // base tile (Apple icon grid: 824pt square, 100pt margin)
    let tile = NSBezierPath(roundedRect: R(100, 100, 824, 824), xRadius: 185 * k, yRadius: 185 * k)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow(); shadow.shadowColor = color(0x000000, 0.45)
    shadow.shadowOffset = NSSize(width: 0, height: -10 * k); shadow.shadowBlurRadius = 28 * k; shadow.set()
    color(0x08080b).setFill(); tile.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGraphicsContext.saveGraphicsState()
    tile.addClip()
    NSGradient(colors: [color(0x1b1b24), color(0x060608)])!.draw(in: R(100, 100, 824, 824), angle: -90)
    // soft colored glows in the corners, like the launcher background
    NSGradient(colors: [color(0xa78bfa, 0.35), color(0xa78bfa, 0)])!.draw(fromCenter: NSPoint(x: 200 * k, y: 900 * k), radius: 0,
        toCenter: NSPoint(x: 200 * k, y: 900 * k), radius: 520 * k, options: [])
    NSGradient(colors: [color(0x22d3ee, 0.28), color(0x22d3ee, 0)])!.draw(fromCenter: NSPoint(x: 880 * k, y: 160 * k), radius: 0,
        toCenter: NSPoint(x: 880 * k, y: 160 * k), radius: 520 * k, options: [])
    NSGraphicsContext.restoreGraphicsState()
    color(0xffffff, 0.08).setStroke(); tile.lineWidth = 4 * k; tile.stroke()

    // game cartridge (Game Boy style: top-right corner cut, grip ridges, contact pins)
    let cx0: CGFloat = 262, cx1: CGFloat = 762, cy0: CGFloat = 168, cy1: CGFloat = 862, rad: CGFloat = 46, cut: CGFloat = 110
    let cart = NSBezierPath()
    cart.move(to: NSPoint(x: (cx0 + rad) * k, y: cy0 * k))
    cart.line(to: NSPoint(x: (cx1 - rad) * k, y: cy0 * k))
    cart.curve(to: NSPoint(x: cx1 * k, y: (cy0 + rad) * k), controlPoint1: NSPoint(x: cx1 * k, y: cy0 * k), controlPoint2: NSPoint(x: cx1 * k, y: cy0 * k))
    cart.line(to: NSPoint(x: cx1 * k, y: (cy1 - cut) * k))
    cart.line(to: NSPoint(x: (cx1 - cut) * k, y: cy1 * k))
    cart.line(to: NSPoint(x: (cx0 + rad) * k, y: cy1 * k))
    cart.curve(to: NSPoint(x: cx0 * k, y: (cy1 - rad) * k), controlPoint1: NSPoint(x: cx0 * k, y: cy1 * k), controlPoint2: NSPoint(x: cx0 * k, y: cy1 * k))
    cart.line(to: NSPoint(x: cx0 * k, y: (cy0 + rad) * k))
    cart.curve(to: NSPoint(x: (cx0 + rad) * k, y: cy0 * k), controlPoint1: NSPoint(x: cx0 * k, y: cy0 * k), controlPoint2: NSPoint(x: cx0 * k, y: cy0 * k))
    cart.close()
    NSGraphicsContext.saveGraphicsState()
    let sh = NSShadow(); sh.shadowColor = color(0x000000, 0.65); sh.shadowOffset = NSSize(width: 0, height: -14 * k); sh.shadowBlurRadius = 30 * k; sh.set()
    color(0x2a2a36).setFill(); cart.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGraphicsContext.saveGraphicsState(); cart.addClip()
    NSGradient(colors: [color(0x353545), color(0x1d1d26)])!.draw(in: R(cx0, cy0, cx1 - cx0, cy1 - cy0), angle: -90)
    NSGraphicsContext.restoreGraphicsState()
    color(0xffffff, 0.14).setStroke(); cart.lineWidth = 4 * k; cart.stroke()

    // grip ridges along the top
    for i in 0..<3 {
        let y = 800 - CGFloat(i) * 26
        let ridge = NSBezierPath(roundedRect: R(312, y, 300, 10), xRadius: 5 * k, yRadius: 5 * k)
        color(0x000000, 0.35).setFill(); ridge.fill()
    }

    // label: the launcher's rainbow, with a "launch" play button
    let label = NSBezierPath(roundedRect: R(312, 300, 400, 400), xRadius: 40 * k, yRadius: 40 * k)
    NSGraphicsContext.saveGraphicsState(); label.addClip()
    NSGradient(colors: [color(0xff4d6d), color(0xfb923c), color(0xfacc15), color(0x34d399), color(0x22d3ee), color(0xa78bfa)])!
        .draw(in: R(312, 300, 400, 400), angle: -45)
    NSGradient(colors: [color(0xffffff, 0.22), color(0xffffff, 0)])!.draw(in: R(312, 500, 400, 200), angle: -90)  // gloss
    NSGraphicsContext.restoreGraphicsState()
    color(0x000000, 0.25).setStroke(); label.lineWidth = 4 * k; label.stroke()

    // speed lines + play triangle = "launch"
    NSGraphicsContext.saveGraphicsState()
    let ps = NSShadow(); ps.shadowColor = color(0x000000, 0.35); ps.shadowOffset = NSSize(width: 0, height: -6 * k); ps.shadowBlurRadius = 14 * k; ps.set()
    let cg = NSGraphicsContext.current!.cgContext
    cg.beginTransparencyLayer(auxiliaryInfo: nil)  // one shadow for the whole mark, not per shape
    color(0xffffff).setFill()
    for (i, len) in [CGFloat(70), 100, 70].enumerated() {
        let y = 448 + CGFloat(i) * 40
        NSBezierPath(roundedRect: R(450 - len, y, len, 22), xRadius: 11 * k, yRadius: 11 * k).fill()
    }
    let play = NSBezierPath()
    play.move(to: NSPoint(x: 478 * k, y: 404 * k)); play.line(to: NSPoint(x: 478 * k, y: 596 * k)); play.line(to: NSPoint(x: 640 * k, y: 500 * k)); play.close()
    play.lineJoinStyle = .round; play.lineWidth = 26 * k
    play.fill(); color(0xffffff).setStroke(); play.stroke()
    cg.endTransparencyLayer()
    NSGraphicsContext.restoreGraphicsState()

    // contact pins along the bottom edge
    for i in 0..<8 {
        let x = 322 + CGFloat(i) * 48
        NSBezierPath(roundedRect: R(x, 196, 30, 54), xRadius: 6 * k, yRadius: 6 * k).fill(with: color(0xd4a84a, 0.85))
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep
}

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "AppIcon.iconset"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
for (name, px) in [("16x16", 16), ("16x16@2x", 32), ("32x32", 32), ("32x32@2x", 64), ("128x128", 128),
                   ("128x128@2x", 256), ("256x256", 256), ("256x256@2x", 512), ("512x512", 512), ("512x512@2x", 1024)] {
    let png = draw(size: CGFloat(px)).representation(using: .png, properties: [:])!
    try! png.write(to: URL(fileURLWithPath: "\(out)/icon_\(name).png"))
}
print("wrote", out)

extension NSBezierPath {
    func fill(with c: NSColor) { c.setFill(); fill() }
}
