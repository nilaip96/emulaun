// Draws the Emulaunch app icon and writes an .iconset folder.
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

    // DS body: two halves with a hinge
    let bodyColor = color(0x23232d)
    let top = NSBezierPath(roundedRect: R(232, 535, 560, 300), xRadius: 54 * k, yRadius: 54 * k)
    let bottom = NSBezierPath(roundedRect: R(232, 189, 560, 300), xRadius: 54 * k, yRadius: 54 * k)
    for p in [top, bottom] {
        NSGraphicsContext.saveGraphicsState()
        let sh = NSShadow(); sh.shadowColor = color(0x000000, 0.6); sh.shadowOffset = NSSize(width: 0, height: -8 * k); sh.shadowBlurRadius = 20 * k; sh.set()
        bodyColor.setFill(); p.fill()
        NSGraphicsContext.restoreGraphicsState()
        color(0xffffff, 0.10).setStroke(); p.lineWidth = 3 * k; p.stroke()
    }
    // hinge
    color(0x15151b).setFill()
    NSBezierPath(roundedRect: R(300, 489, 424, 46), xRadius: 18 * k, yRadius: 18 * k).fill()

    // top screen: violet -> cyan with a play button
    let topScreen = NSBezierPath(roundedRect: R(282, 575, 460, 220), xRadius: 26 * k, yRadius: 26 * k)
    NSGraphicsContext.saveGraphicsState(); topScreen.addClip()
    NSGradient(colors: [color(0xa78bfa), color(0x22d3ee)])!.draw(in: R(282, 575, 460, 220), angle: 20)
    NSGraphicsContext.restoreGraphicsState()
    let play = NSBezierPath()
    play.move(to: NSPoint(x: 470 * k, y: 625 * k)); play.line(to: NSPoint(x: 470 * k, y: 745 * k))
    play.line(to: NSPoint(x: 572 * k, y: 685 * k)); play.close()
    play.lineJoinStyle = .round
    color(0xffffff).setFill(); play.fill()
    color(0xffffff).setStroke(); play.lineWidth = 18 * k; play.stroke()

    // bottom screen: warm gradient with a 3x2 grid of game tiles
    let botScreen = NSBezierPath(roundedRect: R(282, 229, 460, 220), xRadius: 26 * k, yRadius: 26 * k)
    NSGraphicsContext.saveGraphicsState(); botScreen.addClip()
    NSGradient(colors: [color(0xff4d6d), color(0xfb923c), color(0xfacc15)])!.draw(in: R(282, 229, 460, 220), angle: 0)
    NSGraphicsContext.restoreGraphicsState()
    let tileW: CGFloat = 112, tileH: CGFloat = 70, gap: CGFloat = 26
    let gx = 282 + (460 - (3 * tileW + 2 * gap)) / 2, gy = 229 + (220 - (2 * tileH + gap)) / 2
    for row in 0..<2 { for col in 0..<3 {
        let r = R(gx + CGFloat(col) * (tileW + gap), gy + CGFloat(row) * (tileH + gap), tileW, tileH)
        color(0x0b0b10, 0.55).setFill()
        NSBezierPath(roundedRect: r, xRadius: 14 * k, yRadius: 14 * k).fill()
    } }

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
