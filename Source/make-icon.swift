import AppKit

let size = 1024
let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
let bounds = NSRect(x: 0, y: 0, width: size, height: size)
NSColor(calibratedRed: 0.11, green: 0.075, blue: 0.05, alpha: 1).setFill()
bounds.fill()
let glow = NSGradient(colors: [
    NSColor(calibratedRed: 0.42, green: 0.24, blue: 0.13, alpha: 1),
    NSColor(calibratedRed: 0.16, green: 0.09, blue: 0.06, alpha: 1),
    NSColor(calibratedRed: 0.08, green: 0.05, blue: 0.04, alpha: 1)
])!
glow.draw(in: bounds, relativeCenterPosition: NSPoint(x: -0.15, y: 0.2))

func stroke(_ points: [CGPoint], widths: [CGFloat], color: NSColor) {
    guard points.count > 1 else { return }
    for i in 1..<points.count {
        let path = NSBezierPath()
        path.move(to: points[i - 1])
        path.line(to: points[i])
        path.lineWidth = widths[i]
        path.lineCapStyle = .round
        color.setStroke()
        path.stroke()
    }
}

let angle = CGFloat.pi / 3
let butt = CGPoint(x: 250, y: 250)
let handleLength: CGFloat = 340
let ferrule = CGPoint(x: butt.x + cos(angle) * handleLength, y: butt.y + sin(angle) * handleLength)
var handle: [CGPoint] = []
var handleWidth: [CGFloat] = []
for i in 0...28 {
    let t = CGFloat(i) / 28
    handle.append(CGPoint(x: butt.x + cos(angle) * handleLength * t, y: butt.y + sin(angle) * handleLength * t))
    handleWidth.append(78 - 10 * t)
}
stroke(handle, widths: handleWidth, color: NSColor(calibratedRed: 0.34, green: 0.18, blue: 0.09, alpha: 1))
stroke(handle, widths: handleWidth.map { $0 * 0.62 }, color: NSColor(calibratedRed: 0.62, green: 0.36, blue: 0.16, alpha: 1))

var lash: [CGPoint] = [ferrule]
var lashWidth: [CGFloat] = [46]
let controls = [
    CGPoint(x: ferrule.x + 40, y: ferrule.y + 70),
    CGPoint(x: 760, y: 760),
    CGPoint(x: 860, y: 520),
    CGPoint(x: 690, y: 250),
    CGPoint(x: 760, y: 120)
]
let samples = 48
for i in 1...samples {
    let t = CGFloat(i) / CGFloat(samples)
    var points = [ferrule] + controls
    while points.count > 1 {
        var next: [CGPoint] = []
        for j in 1..<points.count {
            let a = points[j - 1], b = points[j]
            next.append(CGPoint(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t))
        }
        points = next
    }
    lash.append(points[0])
    lashWidth.append(46 * pow(1 - t, 1.15) + 8)
}
stroke(lash, widths: lashWidth, color: NSColor(calibratedRed: 0.22, green: 0.1, blue: 0.05, alpha: 1))
stroke(lash, widths: lashWidth.map { $0 * 0.72 }, color: NSColor(calibratedRed: 0.72, green: 0.4, blue: 0.16, alpha: 1))

NSGraphicsContext.restoreGraphicsState()
let url = URL(fileURLWithPath: CommandLine.arguments[1])
try bitmap.representation(using: .png, properties: [:])!.write(to: url)
print(url.path)
