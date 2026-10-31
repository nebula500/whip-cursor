import AppKit
import SwiftUI
import AVFoundation
import CoreGraphics
import Combine
import Carbon
import Darwin

// Everything runs on the main run loop. No event interception or input injection.
enum CrackStyle: String, CaseIterable, Identifiable {
    case classic, sharp, dry, cinematic
    var id: String { rawValue }
    var title: String {
        switch self {
        case .classic: return "Classic bullwhip"
        case .sharp: return "Sharp snap"
        case .dry: return "Dry crack"
        case .cinematic: return "Swoosh + crack"
        }
    }
    var detail: String {
        switch self {
        case .classic: return "A natural outdoor whip crack."
        case .sharp: return "A crisp, punchy whip recording."
        case .dry: return "A short, direct leather snap."
        case .cinematic: return "A sweeping whoosh followed by a crack."
        }
    }
}

enum HandleShape: String, CaseIterable, Identifiable {
    case straight, tapered, flared
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    func radius(at distance: Double) -> Double {
        let t = min(1, max(0, distance / WhipSimulation.handlePixels))
        switch self {
        case .straight: return 5.5
        case .tapered: return 6.5 - 2.2*t
        case .flared: return 4.4 + 2.7*pow(1-t, 3) + 1.3*pow(t, 6)
        }
    }
}

// Button state is independent of AppKit's clickCount. Each release in load mode
// produces exactly one crack, including double-clicks and either mouse button.
struct WhipGesture {
    private var presses: [Int: TimeInterval] = [:]
    mutating func press(_ button: Int, at time: TimeInterval, loading: Bool) -> Bool {
        guard presses[button] == nil else { return false }
        presses[button] = time
        return !loading
    }
    mutating func release(_ button: Int, at time: TimeInterval, loading: Bool) -> Double? {
        guard let start = presses.removeValue(forKey: button) else { return nil }
        return loading ? min(1, max(0, (time-start)/0.9)) : nil
    }
    func charge(at time: TimeInterval, loading: Bool) -> Double {
        guard loading, let start = presses.values.min() else { return 0 }
        return min(1, max(0, (time-start)/0.9))
    }
    func isPressed(_ button: Int) -> Bool { presses[button] != nil }
    mutating func cancel() { presses.removeAll() }
}

// Cursor replacement needs a private WindowServer connection property to work
// while another app is frontmost. Resolve symbols at runtime so unsupported
// systems can retain the visible pointer rather than failing to launch.
final class CursorReplacement {
    typealias Connection = @convention(c) () -> Int32
    typealias SetProperty = @convention(c) (Int32, Int32, CFString, CFTypeRef) -> Int32
    private let connection: Connection?
    private let property: SetProperty?
    private(set) var hidden = false
    private var configured = false
    private var hiddenDisplays: [CGDirectDisplayID] = []
    private var suddenTerminationHeld = false
    var available: Bool { connection != nil && property != nil }
    init() {
        let symbols = UnsafeMutableRawPointer(bitPattern: -2)
        let c = dlsym(symbols, "CGSMainConnectionID") ?? dlsym(symbols, "_CGSDefaultConnection")
        let p = dlsym(symbols, "CGSSetConnectionProperty")
        connection = c.map { unsafeBitCast($0, to: Connection.self) }
        property = p.map { unsafeBitCast($0, to: SetProperty.self) }
    }
    private func activeDisplays() -> [CGDirectDisplayID] {
        var count: UInt32 = 0
        CGGetActiveDisplayList(0, nil, &count)
        var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
        CGGetActiveDisplayList(count, &ids, &count)
        let active = Array(ids.prefix(Int(count)))
        return active.isEmpty ? [CGMainDisplayID()] : active
    }
    @discardableResult func hide() -> Bool {
        if hidden { return true }
        guard let connection = connection, let property = property else { return false }
        let id = connection()
        guard property(id, id, "SetsCursorInBackground" as CFString, kCFBooleanTrue) == 0 else { return false }
        configured = true
        var hiddenIDs: [CGDirectDisplayID] = []
        for display in activeDisplays() {
            if CGDisplayHideCursor(display) == .success { hiddenIDs.append(display) }
        }
        if !hiddenIDs.isEmpty {
            hiddenDisplays = hiddenIDs
            hidden = true
            if !suddenTerminationHeld {
                ProcessInfo.processInfo.disableSuddenTermination()
                suddenTerminationHeld = true
            }
            return true
        }
        restore()
        return false
    }
    func restore() {
        if hidden {
            for display in hiddenDisplays { CGDisplayShowCursor(display) }
            hiddenDisplays.removeAll()
            hidden = false
        }
        if suddenTerminationHeld {
            ProcessInfo.processInfo.enableSuddenTermination()
            suddenTerminationHeld = false
        }
        if configured, let connection = connection, let property = property {
            let id = connection()
            _ = property(id, id, "SetsCursorInBackground" as CFString, kCFBooleanFalse)
        }
        configured = false
    }
    deinit { restore() }
}

final class PauseShortcut {
    private var hotKey: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private let action: () -> Void
    private(set) var registered = false
    init(action: @escaping () -> Void) {
        self.action = action
        var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let callback: EventHandlerUPP = { _, event, context in
            guard let context = context, let event = event else { return OSStatus(eventNotHandledErr) }
            var id = EventHotKeyID()
            let result = GetEventParameter(event,EventParamName(kEventParamDirectObject),EventParamType(typeEventHotKeyID),nil,MemoryLayout<EventHotKeyID>.size,nil,&id)
            guard result == noErr, id.signature == 0x57485043, id.id == 1 else { return OSStatus(eventNotHandledErr) }
            Unmanaged<PauseShortcut>.fromOpaque(context).takeUnretainedValue().action()
            return noErr
        }
        let installed = InstallEventHandler(GetApplicationEventTarget(), callback, 1, &type,
                                            Unmanaged.passUnretained(self).toOpaque(), &handler)
        if installed == noErr {
            let id = EventHotKeyID(signature: 0x57485043, id: 1)
            var key: EventHotKeyRef?
            if RegisterEventHotKey(UInt32(kVK_ANSI_W), UInt32(optionKey | shiftKey), id, GetApplicationEventTarget(), 0, &key) == noErr {
                hotKey = key
                registered = true
            }
        }
    }
    deinit {
        if let hotKey = hotKey { UnregisterEventHotKey(hotKey) }
        if let handler = handler { RemoveEventHandler(handler) }
    }
}

final class Preferences: ObservableObject {
    @Published var enabled = false
    @Published var handleShape: HandleShape { didSet { UserDefaults.standard.set(handleShape.rawValue, forKey: "handleShape") } }
    @Published var loadMode: Bool { didSet { UserDefaults.standard.set(loadMode, forKey: "loadMode") } }
    @Published var replacePointer: Bool { didSet { UserDefaults.standard.set(replacePointer, forKey: "replacePointer") } }
    @Published var replacementAvailable = true
    @Published var pauseShortcutAvailable = true
    @Published var crackStyle: CrackStyle { didSet { UserDefaults.standard.set(crackStyle.rawValue, forKey: "crackStyle") } }
    @Published var sound: Bool { didSet { UserDefaults.standard.set(sound, forKey: "sound") } }
    @Published var volume: Double { didSet { UserDefaults.standard.set(volume, forKey: "volume") } }
    @Published var thickness: Double { didSet { UserDefaults.standard.set(thickness, forKey: "thickness") } }
    @Published var length: Double { didSet { UserDefaults.standard.set(length, forKey: "length") } }
    @Published var color: Color { didSet { saveColor() } }
    init() {
        let d = UserDefaults.standard
        handleShape = HandleShape(rawValue: d.string(forKey: "handleShape") ?? "") ?? .straight
        loadMode = d.object(forKey: "loadMode") as? Bool ?? false
        replacePointer = d.object(forKey: "replacePointer") as? Bool ?? true
        crackStyle = CrackStyle(rawValue: d.string(forKey: "crackStyle") ?? "") ?? .classic
        sound = d.object(forKey: "sound") as? Bool ?? true
        volume = clamped(d.object(forKey: "volume") as? Double ?? 0.45, 0, 1)
        let storedLength = d.object(forKey: "length") as? Double
        if storedLength != nil, d.object(forKey: "lashLengthV2") == nil {
            length = clamped((storedLength ?? 170) * 2, 180, 540)
            d.set(true, forKey: "lashLengthV2")
        } else {
            length = clamped(storedLength ?? 340, 180, 540)
        }
        thickness = clamped(d.object(forKey: "thickness") as? Double ?? 1.0, 0.5, 2.5)
        if let a = d.array(forKey: "color") as? [Double], a.count == 3 {
            color = Color(red: a[0], green: a[1], blue: a[2])
        } else { color = Color(red: 0.96, green: 0.47, blue: 0.26) }
    }
    var nsColor: NSColor { NSColor(color).usingColorSpace(.deviceRGB) ?? .systemOrange }
    func matchesSwatch(_ swatch: Color) -> Bool { colorsMatch(nsColor, NSColor(swatch)) }
    private func saveColor() {
        let c = nsColor
        UserDefaults.standard.set([c.redComponent, c.greenComponent, c.blueComponent], forKey: "color")
    }
}

func clamped(_ value: Double, _ lo: Double, _ hi: Double) -> Double { min(hi, max(lo, value)) }

func colorsMatch(_ a: NSColor, _ b: NSColor, epsilon: CGFloat = 0.02) -> Bool {
    guard let x = a.usingColorSpace(.deviceRGB), let y = b.usingColorSpace(.deviceRGB) else { return false }
    return abs(x.redComponent - y.redComponent) < epsilon
        && abs(x.greenComponent - y.greenComponent) < epsilon
        && abs(x.blueComponent - y.blueComponent) < epsilon
}

func flagValue(_ name: String, in args: [String] = CommandLine.arguments) -> String? {
    guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
    let value = args[index + 1]
    return value.hasPrefix("-") ? nil : value
}

func positionalOutputPath(in args: [String] = CommandLine.arguments) -> String? {
    if let output = flagValue("--output", in: args) { return output }
    let consumed = Set([flagValue("--handle", in: args), flagValue("--thickness", in: args)].compactMap { $0 })
    return args.dropFirst().last { !$0.hasPrefix("-") && !consumed.contains($0) }
}

// Preserve one crack per mouse-down, including both halves of a double-click.
// Keep very fast pairs far enough apart for their transients to remain audible.
struct CrackTiming {
    private var lastStart: TimeInterval = -.infinity
    mutating func nextStart(now: TimeInterval) -> TimeInterval {
        let start = max(now + 0.006, lastStart + 0.095)
        lastStart = start
        return start
    }
}

final class CrackAudio {
    private var players: [CrackStyle: [AVAudioPlayer]] = [:]
    private var index = 0
    private var timing = CrackTiming()
    init() {
        for style in CrackStyle.allCases {
            guard let url = Bundle.main.url(forResource: "crack-" + style.rawValue, withExtension: "wav") else { continue }
            players[style] = (0..<6).compactMap { _ in
                guard let p = try? AVAudioPlayer(contentsOf: url) else { return nil }
                p.prepareToPlay()
                return p
            }
        }
    }
    func play(_ prefs: Preferences, mouseClick: Bool = false) {
        guard prefs.sound, let pool = players[prefs.crackStyle], !pool.isEmpty else { return }
        let p = pool[index % pool.count]
        index += 1
        p.stop(); p.currentTime = 0; p.volume = Float(prefs.volume)
        if mouseClick {
            p.play(atTime: timing.nextStart(now: p.deviceCurrentTime))
        } else {
            p.play()
        }
    }
}

struct Particle {
    var p: CGPoint
    var previous: CGPoint
}
final class WhipSimulation {
    static let count = 40
    static let restAngle = Double.pi / 3
    static let handlePixels = 46.0
    static let throatPixels = 36.0
    var particles: [Particle] = []
    var anchor = CGPoint.zero
    var flash: Double = 0
    var loadAmount: Double = 0
    var handleAngle = WhipSimulation.restAngle
    var handleAngularVelocity = 0.0
    var wave = -1.0
    var waveStrength = 0.0
    var releaseBend = 0.0
    var hangRoll = 0.0
    var cursorTravel = 0.0
    var initialized = false
    func reset(_ point: CGPoint, length: Double) {
        anchor = point
        handleAngle = Self.restAngle
        handleAngularVelocity = 0
        wave = -1
        waveStrength = 0
        releaseBend = 0
        hangRoll = 0
        cursorTravel = 0
        popArmed = false
        particles = (0..<Self.count).map { i in
            let dist = Double(i) / Double(Self.count - 1) * length
            let p = restPoint(from: point, distance: dist, length: length)
            return Particle(p: p, previous: p)
        }
        initialized = true
    }
    private var popArmed = false
    func takePop() -> Bool {
        if !popArmed { return false }
        popArmed = false
        return true
    }
    private func restPoint(from point: CGPoint, distance: Double, length: Double) -> CGPoint {
        curvePoint(from: point, distance: distance, length: length, bend: 0, extend: -1)
    }
    // Rest hangs. A crack is an open U: straight thong, round loop, short free end.
    // The loop runs outward, tightens, and the pop is when it reaches the tip.
    private func curvePoint(from point: CGPoint, distance: Double, length: Double, bend: Double, extend: Double) -> CGPoint {
        let hx = cos(handleAngle), hy = sin(handleAngle)
        if distance <= Self.handlePixels {
            return CGPoint(x: point.x + hx * distance, y: point.y + hy * distance)
        }
        let ferrule = CGPoint(x: point.x + hx * Self.handlePixels, y: point.y + hy * Self.handlePixels)
        let lash = max(1, length - Self.handlePixels)
        let s = distance - Self.handlePixels
        if extend < 0 && bend <= 0 {
            return hangPoint(from: ferrule, distance: s, length: lash)
        }
        if extend < 0 {
            return loadPoint(from: ferrule, distance: s, length: lash, bend: bend)
        }
        return crackPoint(from: ferrule, distance: s, length: lash, bend: bend, extend: extend)
    }
    // The crack begins on the drape, then a loop grows out of it and runs to the tip.
    // The leather past the loop keeps hanging, so the shape never swaps in one frame.
    private func crackPoint(from ferrule: CGPoint, distance s: Double, length lash: Double, bend: Double, extend: Double) -> CGPoint {
        let drape = bend > 0.02
            ? loadPoint(from: ferrule, distance: s, length: lash, bend: bend)
            : hangPoint(from: ferrule, distance: s, length: lash)
        if extend <= 0.001 { return drape }
        let thrown = -0.1
        let T = CGPoint(x: cos(thrown), y: sin(thrown))
        let N = CGPoint(x: -sin(thrown), y: cos(thrown))
        if extend >= 1 {
            let straight = aimed(from: ferrule, distance: s, length: lash, toward: thrown, spanFraction: 0.32)
            let hang = hangPoint(from: ferrule, distance: s, length: lash)
            let settle = min(1, max(0, (extend - 1.08) / 0.36))
            let eased = settle * settle * (3 - 2 * settle)
            return CGPoint(x: straight.x * (1 - eased) + hang.x * eased,
                           y: straight.y * (1 - eased) + hang.y * eased)
        }
        let loop = extend * 0.94
        let half = min(max(0, loop - 0.015), max(0.028 * (1 - extend), 0.17 * pow(1 - extend, 1.1)))
        let shaped: CGPoint
        if half < 0.01 && extend < 0.72 {
            shaped = drape
        } else if half < 0.01 {
            shaped = aimed(from: ferrule, distance: s, length: lash, toward: thrown, spanFraction: 0.32)
        } else {
            let R = max(10, (2 * half * lash) / .pi)
            let straight = max(0, (loop - half) * lash)
            let loopArc = .pi * R
            let origin = aimed(from: ferrule, distance: straight, length: lash, toward: thrown, spanFraction: 0.32)
            if s <= straight {
                shaped = aimed(from: ferrule, distance: s, length: lash, toward: thrown, spanFraction: 0.32)
            } else if s <= straight + loopArc {
                let theta = (s - straight) / R
                let cx = origin.x + N.x * R
                let cy = origin.y + N.y * R
                shaped = CGPoint(x: cx - N.x * R * cos(theta) + T.x * R * sin(theta),
                                 y: cy - N.y * R * cos(theta) + T.y * R * sin(theta))
            } else {
                let ret = s - straight - loopArc
                let free = min(R * 0.7, max(0, lash - straight - loopArc))
                let hinge = CGPoint(x: origin.x + N.x * 2 * R - T.x * min(ret, free),
                                    y: origin.y + N.y * 2 * R - T.y * min(ret, free))
                if ret <= free {
                    shaped = hinge
                } else {
                    let remain = max(1, lash - straight - loopArc - free)
                    shaped = hangFrom(hinge, distance: ret - free, length: remain, bend: bend, startAngle: thrown + .pi)
                }
            }
        }
        let t = min(1, extend / 0.34)
        let e = t * t * (3 - 2 * t)
        return CGPoint(x: drape.x * (1 - e) + shaped.x * e, y: drape.y * (1 - e) + shaped.y * e)
    }
    // The thong is limp. A short curve leaves the handle, then gravity takes it
    // straight down. Below 90° that curve sits on the right; past 90° it rolls
    // over the top and sits on the left.
    private func drapePoint(from ferrule: CGPoint, distance s: Double, length lash: Double, sideLeft: Bool) -> CGPoint {
        let down = -Double.pi / 2
        let target = sideLeft ? down + 2 * .pi : down
        let delta = target - handleAngle
        let span = min(lash * 0.38, max(52, abs(delta) * 40))
        var x = ferrule.x, y = ferrule.y
        var walked = 0.0
        while walked < s {
            let step = min(3.0, s - walked)
            let u = min(1, walked / span)
            let eased = u * u * (3 - 2 * u)
            let angle = handleAngle + delta * eased
            x += cos(angle) * step
            y += sin(angle) * step
            walked += step
        }
        return CGPoint(x: x, y: y)
    }
    private func loadPoint(from ferrule: CGPoint, distance s: Double, length lash: Double, bend: Double) -> CGPoint {
        let right = drapePoint(from: ferrule, distance: s, length: lash, sideLeft: false)
        let left = drapePoint(from: ferrule, distance: s, length: lash, sideLeft: true)
        let t = hangRoll
        let eased = t * t * (3 - 2 * t)
        return CGPoint(x: right.x * (1 - eased) + left.x * eased, y: right.y * (1 - eased) + left.y * eased)
    }
    private func hangPoint(from ferrule: CGPoint, distance s: Double, length lash: Double) -> CGPoint {
        drapePoint(from: ferrule, distance: s, length: lash, sideLeft: handleAngle > Double.pi / 2)
    }
    private func aimed(from ferrule: CGPoint, distance s: Double, length lash: Double, toward: Double, spanFraction: Double) -> CGPoint {
        let span = max(72, lash * spanFraction)
        var x = ferrule.x, y = ferrule.y
        var walked = 0.0
        while walked < s {
            let step = min(3.0, s - walked)
            let along = min(1, walked / span)
            let eased = along * along * (3 - 2 * along)
            var angle = handleAngle + (toward - handleAngle) * eased
            let tip = min(1, walked / lash)
            if tip > 0.8 {
                let sag = pow((tip - 0.8) / 0.2, 2)
                angle += (-Double.pi / 2 + 0.2 - angle) * sag * 0.28
            }
            x += cos(angle) * step
            y += sin(angle) * step
            walked += step
        }
        return CGPoint(x: x, y: y)
    }
    private func hangFrom(_ origin: CGPoint, distance s: Double, length: Double, bend: Double, startAngle: Double) -> CGPoint {
        let down = -Double.pi / 2 - 0.16 * bend
        var target = down
        while target < startAngle { target += 2 * .pi }
        let span = max(56.0, length * 0.34)
        var x = origin.x, y = origin.y
        var walked = 0.0
        while walked < s {
            let step = min(3.0, s - walked)
            let u = min(1, walked / span)
            let eased = u * u * (3 - 2 * u)
            let angle = startAngle + (target - startAngle) * eased
            x += cos(angle) * step
            y += sin(angle) * step
            walked += step
        }
        return CGPoint(x: x, y: y)
    }
    func crack(strength: Double = 1) {
        guard initialized else { return }
        flash = 0
        releaseBend = loadAmount
        loadAmount = 0
        wave = 0
        waveStrength = strength
        popArmed = false
        handleAngularVelocity = -0.55 * strength
    }
    private func follow(_ point: CGPoint, length: Double, spacing: Double, bend: Double, extend: Double, rate: Double) {
        let handleEnd = particles.indices.first { spacing * Double($0) > Self.handlePixels } ?? 1
        let free = max(1, Double(particles.count - handleEnd))
        for i in handleEnd..<particles.count {
            let t = Double(i - handleEnd) / free
            let target = curvePoint(from: point, distance: spacing * Double(i), length: length, bend: bend, extend: extend)
            let follow = rate * (1 - 0.12 * t)
            particles[i].p.x += (target.x - particles[i].p.x) * follow
            particles[i].p.y += (target.y - particles[i].p.y) * follow
            particles[i].previous = particles[i].p
        }
    }
    // While the cursor is moving the thong lags and bows. Once it stops, the hang returns.
    private func trail(_ point: CGPoint, length: Double, spacing: Double, travel: Double) {
        let handleEnd = particles.indices.first { spacing * Double($0) > Self.handlePixels } ?? 1
        let free = max(1, Double(particles.count - handleEnd))
        let moving = min(1, travel)
        for i in handleEnd..<particles.count {
            let t = Double(i - handleEnd) / free
            let vx = particles[i].p.x - particles[i].previous.x
            let vy = particles[i].p.y - particles[i].previous.y
            particles[i].previous = particles[i].p
            let damp = 0.55 + 0.3 * moving
            particles[i].p.x += vx * damp
            particles[i].p.y += vy * damp
            let target = curvePoint(from: point, distance: spacing * Double(i), length: length, bend: 0, extend: -1)
            let pull = (0.04 + 0.12 * (1 - moving)) * (1 - 0.82 * t)
            particles[i].p.x += (target.x - particles[i].p.x) * pull
            particles[i].p.y += (target.y - particles[i].p.y) * pull
        }
    }
    private func pinHandle(to point: CGPoint, spacing: Double) {
        let hx = cos(handleAngle), hy = sin(handleAngle)
        for i in 0..<particles.count {
            let dist = spacing * Double(i)
            guard dist <= Self.handlePixels else { break }
            particles[i].p = CGPoint(x: point.x + hx * dist, y: point.y + hy * dist)
            particles[i].previous = particles[i].p
        }
    }
    func step(to point: CGPoint, length: Double, charge: Double = 0) {
        if !initialized || hypot(point.x - anchor.x, point.y - anchor.y) > 1100 {
            reset(point, length: length)
        }
        let moved = hypot(point.x - anchor.x, point.y - anchor.y)
        cursorTravel += (min(1, moved / 12) - cursorTravel) * 0.28
        anchor = point
        loadAmount += (charge - loadAmount) * 0.18
        let rest = Self.restAngle
        let spacing = length / Double(Self.count - 1)
        var bend = 0.0
        var extend = -1.0
        var rate = 0.2
        if wave >= 0 {
            if wave >= 1.45 {
                wave = -1
                waveStrength = 0
                releaseBend = 0
            } else {
                let phase = wave
                let flick = phase < 1 ? min(1, phase / 0.22) : max(0, 1 - (phase - 1) / 0.42)
                let flickAngle = rest - 0.42 * min(1.2, waveStrength) * flick
                let depart = min(1, max(0, (phase - 0.05) / 0.3))
                handleAngle += (flickAngle - handleAngle) * (0.05 + 0.42 * depart)
                bend = releaseBend
                extend = phase
                rate = phase < 0.02 ? 0.45 : 1
                let before = wave
                if wave < 1 {
                    wave = min(1, wave + 0.022 + 0.08 * wave)
                } else {
                    wave += 0.04
                }
                if before < 0.92 && wave >= 0.92 {
                    popArmed = true
                    flash = 1
                }
            }
        } else if charge > 0.02 {
            handleAngle += ((rest + Double.pi / 4 * loadAmount) - handleAngle) * 0.14
            let wantRoll = handleAngle > Double.pi / 2 ? 1.0 : 0.0
            hangRoll += (wantRoll - hangRoll) * (wantRoll > hangRoll ? 0.055 : 0.18)
            bend = loadAmount
            extend = -1
            rate = 0.4
        } else {
            handleAngle += (rest - handleAngle) * 0.12
            if handleAngle <= Double.pi / 2 { hangRoll = 0 }
        }
        handleAngle = rest + min(Double.pi / 4, max(-0.75, handleAngle - rest))
        let posing = wave >= 0 || charge > 0.02
        pinHandle(to: point, spacing: spacing)
        if posing {
            follow(point, length: length, spacing: spacing, bend: bend, extend: extend, rate: rate)
        } else {
            trail(point, length: length, spacing: spacing, travel: cursorTravel)
        }
        pinHandle(to: point, spacing: spacing)
        let handleEnd = particles.indices.first { spacing * Double($0) > Self.handlePixels } ?? 1
        if !posing {
            let give = 0.12 + 0.4 * (1 - min(1, cursorTravel))
            pinHandle(to: point, spacing: spacing)
            for i in handleEnd..<particles.count {
                let a = particles[i-1].p, b = particles[i].p
                let dx = b.x-a.x, dy = b.y-a.y
                let distance = max(0.001, hypot(dx, dy))
                let slack = distance - spacing
                let compress = slack < 0 ? 0.2 : 1
                let limit = distance > spacing * 1.7 ? 0.85 : give
                let correction = slack / distance * limit * compress
                if i == handleEnd {
                    particles[i].p.x -= dx * correction
                    particles[i].p.y -= dy * correction
                } else {
                    particles[i-1].p.x += dx * correction * 0.25
                    particles[i-1].p.y += dy * correction * 0.25
                    particles[i].p.x -= dx * correction * 0.75
                    particles[i].p.y -= dy * correction * 0.75
                }
            }
        }
        pinHandle(to: point, spacing: spacing)
        flash = max(0, flash - 0.07)
    }
}

// Smooth the rope, then place the braid by distance along its curved surface.
// Ridges stay attached to the leather instead of sliding as the rope bends.
func drawWhip(_ simulation: WhipSimulation, color: NSColor, thickness: Double = 1.0, handleShape: HandleShape = .straight, offset: CGPoint = .zero) {
    guard simulation.initialized, simulation.particles.count > 1 else { return }
    let handleLen = WhipSimulation.handlePixels
    let hx = cos(simulation.handleAngle), hy = sin(simulation.handleAngle)
    let butt = CGPoint(x: simulation.particles[0].p.x - offset.x, y: simulation.particles[0].p.y - offset.y)
    let ferrule = CGPoint(x: butt.x + hx * handleLen, y: butt.y + hy * handleLen)
    var control: [CGPoint] = [ferrule]
    var chain = 0.0
    var previousParticle = simulation.particles[0].p
    var passedHandle = false
    for particle in simulation.particles.dropFirst() {
        chain += hypot(particle.p.x - previousParticle.x, particle.p.y - previousParticle.y)
        previousParticle = particle.p
        guard chain >= handleLen else { continue }
        if !passedHandle { passedHandle = true; continue }
        control.append(CGPoint(x: particle.p.x - offset.x, y: particle.p.y - offset.y))
    }
    guard control.count > 1 else { return }
    var points: [CGPoint] = []
    for i in 0..<(control.count - 1) {
        let a = control[i], b = control[i+1]
        for k in 0..<3 {
            let t = Double(k) / 3
            points.append(CGPoint(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t))
        }
    }
    points.append(control.last!)
    func stroke(_ a: CGPoint, _ b: CGPoint, width: Double, ink: NSColor) {
        let path = NSBezierPath(); path.move(to: a); path.line(to: b)
        path.lineWidth = width * thickness; path.lineCapStyle = .round
        ink.setStroke(); path.stroke()
    }
    func blend(_ fraction: Double, _ other: NSColor) -> NSColor {
        color.blended(withFraction: fraction, of: other) ?? color
    }
    func width(_ t: Double) -> Double { handleShape.radius(at: handleLen) * 1.15 * pow(max(0, 1-t), 1.15) + 0.5 }
    var distances = [0.0]
    for i in 1..<points.count {
        distances.append(distances.last! + hypot(points[i].x-points[i-1].x, points[i].y-points[i-1].y))
    }
    let total = max(1, distances.last!)
    // Dark edges, dyed leather body, and a soft highlight give the round cross-section depth.
    for i in 1..<points.count {
        let a = points[i-1], b = points[i]
        let t = distances[i]/total, w = width(t)
        let d = max(0.001, hypot(b.x-a.x,b.y-a.y))
        let normal = CGPoint(x: -(b.y-a.y)/d, y: (b.x-a.x)/d)
        stroke(a,b,width: w+1.0,ink: blend(0.72,.black).withAlphaComponent(0.9))
        stroke(a,b,width: w,ink: blend(0.24,.black))
        let shift = w * 0.20 * thickness
        let aa = CGPoint(x:a.x+normal.x*shift,y:a.y+normal.y*shift)
        let bb = CGPoint(x:b.x+normal.x*shift,y:b.y+normal.y*shift)
        stroke(aa,bb,width: max(0.3,w*0.38),ink: blend(0.22,.white))
    }
    var ridgeDistance = 4.0
    var segment = 1
    while ridgeDistance < total * 0.88 {
        while segment < distances.count-1 && distances[segment] < ridgeDistance { segment += 1 }
        let a = points[segment-1], b = points[segment]
        let span = max(0.001, distances[segment]-distances[segment-1])
        let f = (ridgeDistance-distances[segment-1])/span
        let center = CGPoint(x:a.x+(b.x-a.x)*f,y:a.y+(b.y-a.y)*f)
        let dx = (b.x-a.x)/span, dy = (b.y-a.y)/span
        let w = width(ridgeDistance/total) * 0.46 * thickness
        func local(_ along: Double, _ across: Double) -> CGPoint {
            CGPoint(x:center.x+dx*along*thickness-dy*across,y:center.y+dy*along*thickness+dx*across)
        }
        // Two interwoven leather strips meet in a chevron, with recessed seams.
        let left = local(-1.25,-w), middle = local(1.1,0), right = local(-1.25,w)
        stroke(left,middle,width:0.85,ink:blend(0.7,.black).withAlphaComponent(0.85))
        stroke(middle,right,width:0.85,ink:blend(0.7,.black).withAlphaComponent(0.85))
        stroke(local(-0.65,-w*0.85),local(1.65,0),width:0.45,ink:blend(0.4,.white).withAlphaComponent(0.8))
        stroke(local(1.65,0),local(-0.65,w*0.85),width:0.45,ink:blend(0.23,.white).withAlphaComponent(0.7))
        ridgeDistance += max(2.2, w * 0.95)
    }
    // A leather-wrapped rigid grip. Orientation comes from the simulation, not the floppy lash.
    let a = butt
    let dx = hx, dy = hy
    func grip(_ along: Double, _ across: Double = 0) -> CGPoint {
        CGPoint(x:a.x+dx*along-dy*across*thickness,y:a.y+dy*along+dx*across*thickness)
    }
    let gripPath = NSBezierPath()
    gripPath.move(to: grip(0, -handleShape.radius(at: 0)))
    for r in stride(from: 1.0, through: handleLen, by: 1) { gripPath.line(to: grip(r, -handleShape.radius(at: r))) }
    let tipRadius = handleShape.radius(at: handleLen)
    gripPath.curve(to: grip(handleLen,tipRadius), controlPoint1: grip(handleLen+3,-tipRadius), controlPoint2: grip(handleLen+3,tipRadius))
    for r in stride(from: handleLen-1, through: 0.0, by: -1) { gripPath.line(to: grip(r, handleShape.radius(at: r))) }
    let buttRadius = handleShape.radius(at: 0)
    gripPath.curve(to: grip(0,-buttRadius), controlPoint1: grip(-3,buttRadius), controlPoint2: grip(-3,-buttRadius))
    gripPath.close(); blend(0.72,.black).setFill(); gripPath.fill()
    NSGraphicsContext.saveGraphicsState()
    gripPath.addClip()
    stroke(grip(0,1),grip(handleLen,1),width:7.8,ink:blend(0.45,.black))
    stroke(grip(1,2.6),grip(handleLen,2.6),width:1.2,ink:blend(0.12,.white).withAlphaComponent(0.75))
    for r in stride(from: 3.0, through: handleLen-2, by: 3) {
        let radius = handleShape.radius(at:r) * 0.88
        stroke(grip(r-1,-radius),grip(r+1.5,radius),width:1,ink:blend(0.85,.black))
        stroke(grip(r-0.3,-radius),grip(r+2.2,radius),width:0.55,ink:blend(0.14,.white))
    }
    NSGraphicsContext.restoreGraphicsState()
    for r in [0.0, handleLen] {
        let radius = handleShape.radius(at:r)*0.9
        stroke(grip(r,-radius),grip(r,radius),width:2.1,ink:NSColor(calibratedWhite:0.15,alpha:1))
        stroke(grip(r+0.5,-radius),grip(r+0.5,radius),width:0.7,ink:NSColor(calibratedWhite:0.55,alpha:1))
    }
    if simulation.loadAmount > 0.02 {
        let ring = NSBezierPath()
        ring.appendArc(withCenter:a,radius:14+thickness*3,startAngle:90,
                       endAngle:90+360*simulation.loadAmount,clockwise:false)
        ring.lineWidth = 1.8; ring.lineCapStyle = .round
        color.withAlphaComponent(0.85).setStroke(); ring.stroke()
    }
    NSColor.white.withAlphaComponent(0.8).setFill()
    NSBezierPath(ovalIn: CGRect(x:a.x-1.3,y:a.y-1.3,width:2.6,height:2.6)).fill()
    if simulation.flash > 0, let tip = points.last {
        let f = simulation.flash
        for i in 0..<7 {
            let angle = Double(i) * 2 * .pi / 7
            let inner = 6+(1-f)*15, outer = inner+f*16
            stroke(CGPoint(x:tip.x+cos(angle)*inner,y:tip.y+sin(angle)*inner),
                   CGPoint(x:tip.x+cos(angle)*outer,y:tip.y+sin(angle)*outer),
                   width:1.8,ink:color.withAlphaComponent(f))
        }
    }
}

final class OverlayView: NSView {
    let simulation: WhipSimulation
    let prefs: Preferences
    var origin: CGPoint
    init(frame: NSRect, simulation: WhipSimulation, prefs: Preferences, origin: CGPoint) {
        self.simulation = simulation; self.prefs = prefs; self.origin = origin
        super.init(frame: frame)
    }
    required init?(coder: NSCoder) { fatalError() }
    override var isOpaque: Bool { false }
    override func draw(_ dirtyRect: NSRect) { drawWhip(simulation, color: prefs.nsColor, thickness: prefs.thickness, handleShape: prefs.handleShape, offset: origin) }
}

final class DesktopEffect {
    let prefs: Preferences
    let audio: CrackAudio
    let simulation = WhipSimulation()
    let cursor = CursorReplacement()
    weak var controlWindow: NSWindow?
    weak var statusButton: NSStatusBarButton?
    var menuOpen = false { didSet { if menuOpen { cursor.restore(); gesture.cancel() } } }
    private var panels: [NSPanel] = []
    private var timer: Timer?
    private var clickMonitors: [Any] = []
    private var observers: [NSObjectProtocol] = []
    private var workspaceObservers: [NSObjectProtocol] = []
    private var gesture = WhipGesture()
    private var previousLoadMode: Bool
    private var suspended = false
    private var stopped = false
    init(prefs: Preferences, audio: CrackAudio) {
        self.prefs = prefs; self.audio = audio; previousLoadMode = prefs.loadMode
        prefs.replacementAvailable = cursor.available
        let events: NSEvent.EventTypeMask = [.leftMouseDown,.rightMouseDown,.leftMouseUp,.rightMouseUp]
        if let monitor = NSEvent.addGlobalMonitorForEvents(matching: events, handler: { [weak self] event in self?.handle(event) }) { clickMonitors.append(monitor) }
        if let monitor = NSEvent.addLocalMonitorForEvents(matching: events, handler: { [weak self] event in
            self?.handle(event); return event
        }) { clickMonitors.append(monitor) }
        observers.append(NotificationCenter.default.addObserver(forName:NSApplication.didChangeScreenParametersNotification,object:nil,queue:.main) { [weak self] _ in
            self?.cursor.restore(); self?.rebuildPanels()
        })
        let center = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.willSleepNotification,NSWorkspace.screensDidSleepNotification,NSWorkspace.sessionDidResignActiveNotification] {
            workspaceObservers.append(center.addObserver(forName:name,object:nil,queue:.main) { [weak self] _ in
                self?.suspended = true; self?.cursor.restore(); self?.gesture.cancel()
                self?.panels.forEach { $0.alphaValue = 0 }
            })
        }
        for name in [NSWorkspace.didWakeNotification,NSWorkspace.screensDidWakeNotification,NSWorkspace.sessionDidBecomeActiveNotification] {
            workspaceObservers.append(center.addObserver(forName:name,object:nil,queue:.main) { [weak self] _ in self?.suspended = false })
        }
        timer = Timer(timeInterval:1.0/60,repeats:true) { [weak self] _ in self?.tick() }
        RunLoop.main.add(timer!,forMode:.common)
    }
    private func overControls(_ point: CGPoint) -> Bool {
        if NSApp.isActive, let window = controlWindow, window.isVisible, window.frame.contains(point) { return true }
        if let button = statusButton, let window = button.window {
            return window.convertToScreen(button.convert(button.bounds,to:nil)).contains(point)
        }
        return false
    }
    func synchronize() {
        if !prefs.enabled {
            cursor.restore(); gesture.cancel(); simulation.loadAmount = 0
            panels.forEach { $0.orderOut(nil) }; panels.removeAll()
        } else if panels.isEmpty { rebuildPanels() }
        if !prefs.replacePointer { cursor.restore() }
    }
    func rebuildPanels() {
        panels.forEach { $0.orderOut(nil) }; panels.removeAll()
        guard prefs.enabled else { return }
        for screen in NSScreen.screens {
            let panel = NSPanel(contentRect:screen.frame,styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
            panel.backgroundColor = .clear; panel.isOpaque = false; panel.hasShadow = false
            panel.ignoresMouseEvents = true; panel.hidesOnDeactivate = false
            panel.level = NSWindow.Level(rawValue:Int(CGWindowLevelForKey(.cursorWindow))-1)
            panel.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary,.stationary,.ignoresCycle]
            panel.contentView = OverlayView(frame:CGRect(origin:.zero,size:screen.frame.size),simulation:simulation,prefs:prefs,origin:screen.frame.origin)
            panel.orderFrontRegardless(); panels.append(panel)
        }
    }
    private func handle(_ event: NSEvent) {
        guard prefs.enabled, !suspended, !menuOpen else { return }
        if let window = event.window, window === controlWindow || window === statusButton?.window {
            gesture.cancel(); return
        }
        guard !overControls(NSEvent.mouseLocation) else { gesture.cancel(); return }
        if previousLoadMode != prefs.loadMode { gesture.cancel(); previousLoadMode = prefs.loadMode }
        let down = event.type == .leftMouseDown || event.type == .rightMouseDown
        simulation.step(to:NSEvent.mouseLocation,length:prefs.length)
        if down {
            if gesture.press(event.buttonNumber,at:event.timestamp,loading:prefs.loadMode) { crack(0) }
        } else if let charge = gesture.release(event.buttonNumber,at:event.timestamp,loading:prefs.loadMode) { crack(charge) }
    }
    private func crack(_ charge: Double) {
        simulation.crack(strength:1+charge*0.65)
    }
    private func tick() {
        guard prefs.enabled else { synchronize(); return }
        if panels.isEmpty { rebuildPanels() }
        if previousLoadMode != prefs.loadMode { gesture.cancel(); previousLoadMode = prefs.loadMode }
        let point = NSEvent.mouseLocation
        let visible = !suspended && !menuOpen && !overControls(point) && NSScreen.screens.contains { $0.frame.contains(point) }
        panels.forEach { $0.alphaValue = visible ? 1 : 0 }
        guard visible else { cursor.restore(); gesture.cancel(); return }
        // Native context-menu tracking can omit a monitored mouse-up. Reconcile
        // only buttons already pressed, so this cannot invent extra clicks.
        let now = ProcessInfo.processInfo.systemUptime
        for button in [0,1] where gesture.isPressed(button) {
            let physical: CGMouseButton = button == 0 ? .left : .right
            if !CGEventSource.buttonState(.combinedSessionState,button:physical),
               let charge = gesture.release(button,at:now,loading:prefs.loadMode) { crack(charge) }
        }
        simulation.step(to:point,length:prefs.length,charge:gesture.charge(at:now,loading:prefs.loadMode))
        if simulation.takePop() { audio.play(prefs, mouseClick: true) }
        panels.forEach { $0.contentView?.needsDisplay = true }
        if prefs.replacePointer && prefs.replacementAvailable {
            if !cursor.hide() { prefs.replacementAvailable = false }
        } else { cursor.restore() }
    }
    func stop() {
        guard !stopped else { return }
        stopped = true
        prefs.enabled = false; synchronize(); timer?.invalidate(); cursor.restore()
        clickMonitors.forEach { NSEvent.removeMonitor($0) }; clickMonitors.removeAll()
        observers.forEach { NotificationCenter.default.removeObserver($0) }; observers.removeAll()
        workspaceObservers.forEach { NSWorkspace.shared.notificationCenter.removeObserver($0) }; workspaceObservers.removeAll()
    }
    deinit { stop() }
}

final class PreviewView: NSView {
    let prefs: Preferences
    let audio: CrackAudio
    let simulation = WhipSimulation()
    var timer: Timer?
    var tracking: NSTrackingArea?
    var inside = false
    var target = CGPoint(x: 190, y: 140)
    var time: Double = 0
    var gesture = WhipGesture()
    var previousLoadMode = false
    init(prefs: Preferences, audio: CrackAudio) {
        self.prefs = prefs; self.audio = audio
        super.init(frame: .zero)
    }
    required init?(coder: NSCoder) { fatalError() }
    override func viewDidMoveToWindow() {
        timer?.invalidate(); timer = nil
        if window != nil {
            timer = Timer(timeInterval: 1.0/60, repeats: true) { [weak self] _ in
                guard let self = self else { return }
                guard self.window?.isVisible == true else { return }
                self.time += 1.0/60
                if !self.inside { self.target = CGPoint(x: self.bounds.midX + sin(self.time * 0.8)*65, y: self.bounds.height - 32 + cos(self.time)*8) }
                if self.previousLoadMode != self.prefs.loadMode { self.gesture.cancel(); self.previousLoadMode = self.prefs.loadMode }
                self.simulation.step(to:self.target,length:self.prefs.length*0.72,charge:self.gesture.charge(at:ProcessInfo.processInfo.systemUptime,loading:self.prefs.loadMode))
                if self.simulation.takePop() { self.audio.play(self.prefs, mouseClick: true) }
                self.needsDisplay = true
            }
            RunLoop.main.add(timer!, forMode: .common)
        }
    }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking = tracking { removeTrackingArea(tracking) }
        let area = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .mouseMoved, .activeInKeyWindow, .inVisibleRect], owner: self)
        addTrackingArea(area); tracking = area
    }
    override func resetCursorRects() {
        let image = NSImage(size: NSSize(width: 1, height: 1))
        addCursorRect(bounds, cursor: NSCursor(image: image, hotSpot: .zero))
    }
    override func mouseEntered(with event: NSEvent) { inside = true; mouseMoved(with: event) }
    override func mouseExited(with event: NSEvent) { inside = false; gesture.cancel() }
    override func mouseMoved(with event: NSEvent) { target = convert(event.locationInWindow, from: nil) }
    override func mouseDragged(with event: NSEvent) { mouseMoved(with: event) }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func mouseDown(with event: NSEvent) {
        mouseMoved(with:event)
        if previousLoadMode != prefs.loadMode { gesture.cancel(); previousLoadMode = prefs.loadMode }
        if gesture.press(event.buttonNumber,at:event.timestamp,loading:prefs.loadMode) { crack(0) }
    }
    override func mouseUp(with event: NSEvent) {
        mouseMoved(with:event)
        if let charge = gesture.release(event.buttonNumber,at:event.timestamp,loading:prefs.loadMode) { crack(charge) }
    }
    private func crack(_ charge: Double) {
        simulation.step(to:target,length:prefs.length*0.72)
        simulation.crack(strength:1+charge*0.65)
    }
    override func rightMouseDown(with event: NSEvent) { mouseDown(with:event) }
    override func rightMouseUp(with event: NSEvent) { mouseUp(with:event) }
    override func rightMouseDragged(with event: NSEvent) { mouseMoved(with:event) }
    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.085, blue: 0.095, alpha: 1).setFill(); bounds.fill()
        NSColor.white.withAlphaComponent(0.065).setFill()
        for x in stride(from: 16.0, to: bounds.width, by: 20) {
            for y in stride(from: 16.0, to: bounds.height, by: 20) {
                NSBezierPath(ovalIn: CGRect(x: x, y: y, width: 1.5, height: 1.5)).fill()
            }
        }
        drawWhip(simulation, color: prefs.nsColor, thickness: prefs.thickness, handleShape: prefs.handleShape)
    }
}
struct Preview: NSViewRepresentable {
    let prefs: Preferences
    let audio: CrackAudio
    func makeNSView(context: Context) -> PreviewView { PreviewView(prefs: prefs, audio: audio) }
    func updateNSView(_ nsView: PreviewView, context: Context) { nsView.needsDisplay = true }
}

struct ContentView: View {
    @ObservedObject var prefs: Preferences
    let audio: CrackAudio
    var viewportHeight: CGFloat? = nil
    var previewHeight: CGFloat = 220
    private let swatches: [(String, Color)] = [
        ("Ember", Color(red: 0.96, green: 0.47, blue: 0.26)),
        ("Mint", Color(red: 0.42, green: 0.89, blue: 0.72)),
        ("Lavender", Color(red: 0.68, green: 0.58, blue: 1)),
        ("Ice", Color(red: 0.40, green: 0.76, blue: 1)),
        ("Rose", Color(red: 1, green: 0.48, blue: 0.66)),
        ("Pearl", Color(red: 0.94, green: 0.94, blue: 0.88))
    ]
    var body: some View {
        Group {
            if let height = viewportHeight {
                ScrollView { content }.frame(width:450,height:height)
            } else {
                content
            }
        }
        .background(Color(red:0.105,green:0.115,blue:0.13))
        .preferredColorScheme(.dark)
    }
    private var content: some View {
        VStack(alignment: .leading, spacing: 19) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("WHIP").font(.system(size: 12, weight: .bold, design: .monospaced)).tracking(5).foregroundStyle(prefs.color)
                    Text("A little snap.").font(.system(size: 31, weight: .semibold, design: .rounded))
                    Text("Give your cursor a wild side.").font(.system(size: 13)).foregroundStyle(.secondary)
                }
                Spacer()
                HStack(spacing: 6) {
                    Circle().fill(prefs.enabled ? Color.green : Color.gray).frame(width: 6, height: 6)
                    Text(prefs.enabled ? "LIVE" : "PAUSED").font(.system(size: 10, weight: .bold, design: .monospaced))
                }.padding(.horizontal, 10).padding(.vertical, 7).background(.white.opacity(0.06), in: Capsule())
            }
            ZStack(alignment: .bottomLeading) {
                Preview(prefs: prefs, audio: audio)
                HStack {
                    Image(systemName: "cursorarrow.motionlines")
                    Text(prefs.loadMode ? "Hold to load. Release to crack." : "Click to crack. Double-click for two.")
                }.font(.system(size: 11)).foregroundStyle(.white.opacity(0.45)).padding(15).allowsHitTesting(false)
            }.frame(height: previewHeight).clipShape(RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).strokeBorder(.white.opacity(0.08)))
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("MAKE IT YOURS").font(.system(size: 10, weight: .bold, design: .monospaced)).tracking(2).foregroundStyle(.secondary)
                    Spacer()
                    ColorPicker("Custom color", selection: $prefs.color, supportsOpacity: false).font(.system(size: 11)).fixedSize()
                }
                HStack(spacing: 13) {
                    ForEach(swatches, id: \.0) { name, color in
                        Button { prefs.color = color } label: {
                            Circle().fill(color).frame(width: 30, height: 30)
                                .overlay(Circle().strokeBorder(.black.opacity(0.15), lineWidth: 1))
                                .padding(4)
                                .overlay(Circle().strokeBorder(prefs.matchesSwatch(color) ? Color.white.opacity(0.8) : .clear, lineWidth: 1))
                        }.buttonStyle(.plain).help(name).accessibilityLabel(name)
                    }
                    Spacer(minLength: 0)
                }
                HStack {
                    Text("Whip length").font(.system(size: 12)).frame(width: 85, alignment: .leading)
                    Slider(value: $prefs.length, in: 180...540).tint(prefs.color).accessibilityLabel("Whip length")
                    Text("\(Int(prefs.length))").font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary).frame(width: 30)
                }
                HStack {
                    Text("Thickness").font(.system(size: 12)).frame(width: 85, alignment: .leading)
                    Slider(value: $prefs.thickness, in: 0.5...2.5, step: 0.05).tint(prefs.color).accessibilityLabel("Whip thickness")
                    Text("\(Int((prefs.thickness * 100).rounded()))%").font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary).frame(width: 36)
                }
            }
                HStack {
                    Text("Handle").font(.system(size:12)).frame(width:60,alignment:.leading)
                    Picker("Handle shape",selection:$prefs.handleShape) {
                        ForEach(HandleShape.allCases) { shape in Text(shape.title).tag(shape) }
                    }.labelsHidden().pickerStyle(.segmented)
                }
            VStack(alignment:.leading,spacing:10) {
                Toggle("Replace system pointer",isOn:$prefs.replacePointer).toggleStyle(.switch).controlSize(.small)
                if prefs.replacePointer && !prefs.replacementAvailable {
                    Text("Replacement is unavailable on this Mac. The normal pointer stays visible.").font(.system(size:10)).foregroundStyle(.secondary)
                }
                Toggle("Hold to load the whip",isOn:$prefs.loadMode).toggleStyle(.switch).controlSize(.small)
                Text(prefs.loadMode ? "Hold either mouse button to coil the whip; release to crack." : "Crack immediately on each left or right click.")
                    .font(.system(size:10)).foregroundStyle(.secondary)
            }.font(.system(size:12)).tint(prefs.color)
            Divider().overlay(.white.opacity(0.03))
            VStack(spacing: 14) {
                HStack {
                    Image(systemName: "waveform").foregroundStyle(prefs.color).frame(width: 22)
                    Text("Crack on click").font(.system(size: 13, weight: .medium))
                    Spacer()
                    Toggle("Crack on click", isOn: $prefs.sound).labelsHidden().toggleStyle(.switch).controlSize(.small).tint(prefs.color)
                }
                HStack {
                    Text("Sound").font(.system(size: 12)).frame(width: 52, alignment: .leading)
                    Picker("Sound", selection: $prefs.crackStyle) {
                        ForEach(CrackStyle.allCases) { style in Text(style.title).tag(style) }
                    }.labelsHidden().pickerStyle(.menu).tint(prefs.color)
                    Button("Preview") { audio.play(prefs) }.controlSize(.small).disabled(!prefs.sound)
                }
                Text(prefs.crackStyle.detail).font(.system(size: 10)).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 12) {
                    Image(systemName: "speaker.fill").font(.system(size: 11)).foregroundStyle(.secondary).frame(width: 22)
                    Slider(value: $prefs.volume, in: 0...1).tint(prefs.color).disabled(!prefs.sound).accessibilityLabel("Crack volume")
                    Button("Test") { audio.play(prefs) }.controlSize(.small).disabled(!prefs.sound)
                }
            }
            Button { prefs.enabled.toggle() } label: {
                HStack(spacing: 8) {
                    Image(systemName: prefs.enabled ? "pause.fill" : "bolt.fill")
                    Text(prefs.enabled ? "Pause desktop whip" : "Unleash the whip").fontWeight(.semibold)
                }.frame(maxWidth: .infinity).padding(.vertical, 13)
                    .background(prefs.color, in: RoundedRectangle(cornerRadius: 11))
                    .foregroundStyle(Color.black.opacity(0.85))
            }.buttonStyle(.plain).keyboardShortcut("e", modifiers: [.command])
            VStack(spacing: 5) {
                Text("Menu bar: click to toggle · right-click for settings")
                if prefs.pauseShortcutAvailable {
                    Text("Pause from the menu bar or press ⌥ ⇧ W.")
                } else {
                    Text("⌥ ⇧ W is already in use. Pause from the menu bar or Settings instead.")
                }
            }.font(.system(size: 10)).foregroundStyle(.secondary).frame(maxWidth: .infinity)
        }
        .padding(28).frame(width: 450)
        .background(Color(red: 0.105, green: 0.115, blue: 0.13))
        .preferredColorScheme(.dark)
    }
}

// A resolution-independent template image keeps the whip legible in either
// menu bar appearance and at Retina scale. ON/OFF text carries its state.
func makeWhipMenuIcon() -> NSImage {
    let image = NSImage(size:NSSize(width:18,height:18),flipped:false) { _ in
        NSColor.black.setStroke()
        let lash = NSBezierPath()
        lash.move(to:NSPoint(x:6.6,y:8))
        lash.curve(to:NSPoint(x:10,y:15.5),controlPoint1:NSPoint(x:1.5,y:12.5),controlPoint2:NSPoint(x:4,y:17))
        lash.curve(to:NSPoint(x:14,y:10),controlPoint1:NSPoint(x:16.7,y:14.7),controlPoint2:NSPoint(x:17.3,y:9.2))
        lash.curve(to:NSPoint(x:10.5,y:6.5),controlPoint1:NSPoint(x:10.6,y:10.8),controlPoint2:NSPoint(x:8,y:8.8))
        lash.lineWidth = 1.35; lash.lineCapStyle = .round; lash.lineJoinStyle = .round; lash.stroke()
        let tip = NSBezierPath()
        tip.move(to:NSPoint(x:10.5,y:6.5))
        tip.curve(to:NSPoint(x:17,y:4),controlPoint1:NSPoint(x:12,y:4.2),controlPoint2:NSPoint(x:15.4,y:5.2))
        tip.lineWidth = 0.8; tip.lineCapStyle = .round; tip.stroke()
        let grip = NSBezierPath()
        grip.move(to:NSPoint(x:2.5,y:2)); grip.line(to:NSPoint(x:6.6,y:8))
        grip.lineWidth = 3.2; grip.lineCapStyle = .round; grip.stroke()
        // Small cuts hint at the leather wrapping without adding tiny detail.
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current?.compositingOperation = .destinationOut
        NSColor.black.setStroke()
        for y in [3.3,5.0,6.7] {
            let x = 2.5 + (y-2)*0.7
            let seam = NSBezierPath()
            seam.move(to:NSPoint(x:x-0.7,y:y+0.45)); seam.line(to:NSPoint(x:x+0.7,y:y-0.45))
            seam.lineWidth = 0.45; seam.stroke()
        }
        NSGraphicsContext.restoreGraphicsState()
        return true
    }
    image.isTemplate = true
    image.accessibilityDescription = "Whip"
    return image
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let prefs = Preferences()
    let audio = CrackAudio()
    var effect: DesktopEffect!
    var window: NSWindow!
    var statusItem: NSStatusItem!
    private let whipMenuIcon = makeWhipMenuIcon()
    var statusMenu: NSMenu!
    var observation: AnyCancellable?
    var shortcut: PauseShortcut?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        effect = DesktopEffect(prefs:prefs,audio:audio)
        statusItem = NSStatusBar.system.statusItem(withLength:NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.target = self; button.action = #selector(statusClicked)
            button.sendAction(on:[.leftMouseUp,.rightMouseUp])
        }
        statusMenu = NSMenu(); statusMenu.delegate = self
        statusMenu.addItem(withTitle:"Enable whip",action:#selector(toggle),keyEquivalent:"e")
        statusMenu.addItem(withTitle:"Settings…",action:#selector(showWindow),keyEquivalent:",")
        statusMenu.addItem(.separator())
        statusMenu.addItem(withTitle:"Quit Whip Cursor",action:#selector(quit),keyEquivalent:"q")
        statusMenu.items.forEach { $0.target = self }
        let main = NSMenu(), application = NSMenu(), applicationItem = NSMenuItem()
        main.addItem(applicationItem); applicationItem.submenu = application
        let settings = application.addItem(withTitle:"Whip Cursor Settings…",action:#selector(showWindow),keyEquivalent:",")
        settings.target = self
        let pauseItem = application.addItem(withTitle:"Pause whip",action:#selector(pause),keyEquivalent:"w")
        pauseItem.target = self; pauseItem.keyEquivalentModifierMask = [.option,.shift]
        application.addItem(.separator())
        let quitItem = application.addItem(withTitle:"Quit Whip Cursor",action:#selector(quit),keyEquivalent:"q")
        quitItem.target = self; NSApp.mainMenu = main
        window = NSWindow(contentRect:NSRect(x:0,y:0,width:450,height:800),styleMask:[.titled,.closable,.miniaturizable],backing:.buffered,defer:false)
        window.title = "Whip Cursor"; window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(calibratedRed:0.105,green:0.115,blue:0.13,alpha:1)
        window.isReleasedWhenClosed = false
        // Size to all controls by default; use a scroll view only if the screen
        // physically cannot accommodate the complete settings panel.
        let fullContent = NSHostingView(rootView:ContentView(prefs:prefs,audio:audio))
        let titleBarHeight = window.frame.height - window.contentLayoutRect.height
        let screenHeight = (window.screen ?? NSScreen.main)?.visibleFrame.height ?? 1100
        let availableHeight = max(360,screenHeight-titleBarHeight-8)
        let overflow = max(0,fullContent.fittingSize.height-availableHeight)
        // Recover a little space from the preview before requiring scrolling.
        let previewHeight = max(150,220-overflow-1)
        let fitted = NSHostingView(rootView:ContentView(prefs:prefs,audio:audio,previewHeight:previewHeight))
        let idealSize = fitted.fittingSize
        if idealSize.height <= availableHeight {
            window.contentView = fitted
        } else {
            window.contentView = NSHostingView(rootView:ContentView(prefs:prefs,audio:audio,viewportHeight:availableHeight,previewHeight:previewHeight))
        }
        window.setContentSize(NSSize(width:450,height:min(idealSize.height,availableHeight)))
        window.center()
        effect.controlWindow = window; effect.statusButton = statusItem.button
        observation = prefs.$enabled.sink { [weak self] _ in
            DispatchQueue.main.async { self?.refreshStatus(); self?.effect.synchronize() }
        }
        shortcut = PauseShortcut { [weak self] in
            self?.prefs.enabled = false; self?.effect.synchronize(); self?.refreshStatus()
        }
        prefs.pauseShortcutAvailable = shortcut?.registered == true
        refreshStatus(); showWindow()
    }
    private func refreshStatus() {
        guard let button = statusItem.button else { return }
        button.image = whipMenuIcon
        button.title = prefs.enabled ? " ON" : " OFF"
        button.font = NSFont.monospacedSystemFont(ofSize:10,weight:.semibold)
        button.toolTip = "Whip \(prefs.enabled ? "on" : "off") · Click to toggle · Right-click for settings"
        button.setAccessibilityLabel("Whip \(prefs.enabled ? "on" : "off"). Click to toggle. Right-click for settings.")
    }
    @objc func statusClicked() {
        if NSApp.currentEvent?.type == .rightMouseUp || NSApp.currentEvent?.modifierFlags.contains(.control) == true {
            effect.menuOpen = true
            if let button = statusItem.button { statusMenu.popUp(positioning:nil,at:NSPoint(x:0,y:button.bounds.height+4),in:button) }
            effect.menuOpen = false
        } else { toggle() }
    }
    func menuWillOpen(_ menu: NSMenu) {
        effect.menuOpen = true
        menu.items[0].title = prefs.enabled ? "Pause whip" : "Enable whip"
        menu.items[0].state = prefs.enabled ? .on : .off
    }
    func menuDidClose(_ menu: NSMenu) { effect.menuOpen = false }
    @objc func showWindow() { effect?.cursor.restore(); NSApp.activate(ignoringOtherApps:true); window.makeKeyAndOrderFront(nil) }
    @objc func pause() { prefs.enabled = false; effect.synchronize(); refreshStatus() }
    @objc func toggle() { prefs.enabled.toggle(); effect.synchronize(); refreshStatus() }
    @objc func quit() { effect.stop(); NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        effect?.stop()
        shortcut = nil
        return .terminateNow
    }
    func applicationWillTerminate(_ notification: Notification) { effect?.stop(); shortcut = nil }
    func applicationShouldHandleReopen(_ sender: NSApplication,hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
}

if CommandLine.arguments.contains("--render-test") {
    guard let outputPath = positionalOutputPath() else {
        fputs("usage: WhipCursor --render-test [--handle <shape>] [--thickness <n>] [--loaded] [--output] <png>\n", stderr)
        exit(1)
    }
    let simulation = WhipSimulation()
    simulation.reset(CGPoint(x: 110, y: 160), length: 190)
    for i in 0..<WhipSimulation.count {
        let t = Double(i)/Double(WhipSimulation.count-1)
        simulation.particles[i].p = CGPoint(x:110+t*155,y:160-90*sin(t*2.6))
    }
    let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:960,pixelsHigh:600,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:bitmap)
    NSColor(calibratedWhite:0.08,alpha:1).setFill()
    NSRect(x:0,y:0,width:960,height:600).fill()
    let transform = NSAffineTransform(); transform.scale(by:3); transform.concat()
    var renderThickness = 1.0
    if let value = flagValue("--thickness") {
        renderThickness = clamped(Double(value) ?? 1.0, 0.5, 2.5)
    }
    let shape = HandleShape(rawValue: flagValue("--handle") ?? "") ?? .straight
    if CommandLine.arguments.contains("--loaded") {
        for _ in 0..<100 { simulation.step(to:CGPoint(x:160,y:100),length:140,charge:1) }
    }
    drawWhip(simulation,color:NSColor(calibratedRed:0.65,green:0.32,blue:0.13,alpha:1),thickness:renderThickness,handleShape:shape)
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:outputPath))
    print("PASS: textured leather renderer")
} else if CommandLine.arguments.contains("--self-test") {
    let simulation = WhipSimulation()
    for i in 0..<1200 {
        let t = Double(i) / 60
        simulation.step(to: CGPoint(x: 500 + sin(t)*200, y: 500 + cos(t*2)*100), length: 170)
        if i % 30 == 0 { simulation.crack() }
        precondition(simulation.particles.allSatisfy { $0.p.x.isFinite && $0.p.y.isFinite })
        precondition(simulation.particles[0].p == simulation.anchor)
    }
    simulation.step(to: CGPoint(x: -1500, y: 900), length: 260)
    precondition(simulation.particles.allSatisfy { $0.p.x.isFinite && $0.p.y.isFinite })
    let maxSegment = zip(simulation.particles, simulation.particles.dropFirst()).map { hypot($0.p.x-$1.p.x, $0.p.y-$1.p.y) }.max()!
    let spacing = 260 / Double(WhipSimulation.count - 1)
    precondition(maxSegment < spacing * 3.0, "Constraint solver failed")
    for style in CrackStyle.allCases {
        let url = Bundle.main.url(forResource: "crack-" + style.rawValue, withExtension: "wav")!
        let file = try! AVAudioFile(forReading:url)
        precondition(file.length > 2000 && file.processingFormat.sampleRate == 48000)
    }
    // Model very fast left and right double-clicks on the audio device clock.
    // Both presses must retain distinct starts, with no debounce or dropped second crack.
    for _ in ["left", "right"] {
        var timing = CrackTiming()
        let first = timing.nextStart(now: 10.0)
        let second = timing.nextStart(now: 10.025)
        precondition(first < second && second - first >= 0.0949)
        precondition(second < 10.13)
        let nextSingle = timing.nextStart(now: 11.0)
        precondition(abs(nextSingle - 11.006) < 0.0001)
    }
    for button in [0,1] {
        var gesture = WhipGesture()
        precondition(gesture.press(button,at:1,loading:false))
        precondition(gesture.release(button,at:1.02,loading:false) == nil)
        precondition(gesture.press(button,at:1.1,loading:false))
        precondition(gesture.release(button,at:1.12,loading:false) == nil)
        precondition(!gesture.press(button,at:2,loading:true))
        precondition(gesture.charge(at:2.45,loading:true) > 0.49)
        precondition(gesture.release(button,at:3,loading:true) == 1)
        precondition(gesture.release(button,at:3.1,loading:true) == nil)
        for time in [4.0,4.1] {
            precondition(!gesture.press(button,at:time,loading:true))
            precondition(gesture.release(button,at:time+0.025,loading:true) != nil)
        }
        _ = gesture.press(button,at:5,loading:true); gesture.cancel()
        precondition(gesture.charge(at:6,loading:true) == 0)
        precondition(gesture.release(button,at:6,loading:true) == nil)
    }
    for _ in 0..<240 { simulation.step(to:CGPoint(x:200,y:200),length:170,charge:1) }
    precondition(simulation.loadAmount > 0.99)
    simulation.crack(strength:1.65)
    for _ in 0..<120 { simulation.step(to:CGPoint(x:200,y:200),length:170) }
    precondition(simulation.particles.allSatisfy { $0.p.x.isFinite && $0.p.y.isFinite })
    precondition(abs(simulation.handleAngle - WhipSimulation.restAngle) < 0.25)
    simulation.crack(strength: 1.4)
    precondition(simulation.handleAngularVelocity < 0)
    for _ in 0..<180 { simulation.step(to: CGPoint(x: 200, y: 200), length: 170) }
    precondition(abs(simulation.handleAngle - WhipSimulation.restAngle) < 0.25)
    precondition(Set(HandleShape.allCases.map { $0.radius(at:0) }).count == 3)
    precondition(clamped(-1, 0, 1) == 0 && clamped(2, 0, 1) == 1 && clamped(170, 90, 260) == 170)
    precondition(clamped(0.2, 0.5, 2.5) == 0.5 && clamped(9, 90, 260) == 90)
    let ember = NSColor(calibratedRed: 0.96, green: 0.47, blue: 0.26, alpha: 1)
    precondition(colorsMatch(ember, NSColor(calibratedRed: 0.961, green: 0.472, blue: 0.258, alpha: 1)))
    precondition(!colorsMatch(ember, NSColor(calibratedRed: 0.40, green: 0.76, blue: 1, alpha: 1)))
    precondition(positionalOutputPath(in: ["app", "--render-test"]) == nil)
    precondition(positionalOutputPath(in: ["app", "--render-test", "--handle", "flared"]) == nil)
    precondition(positionalOutputPath(in: ["app", "--render-test", "/tmp/a.png"]) == "/tmp/a.png")
    precondition(positionalOutputPath(in: ["app", "--render-test", "--handle", "flared", "/tmp/a.png"]) == "/tmp/a.png")
    precondition(positionalOutputPath(in: ["app", "--render-test", "--output", "/tmp/b.png"]) == "/tmp/b.png")
    print("PASS: immediate clicks, loaded releases, left/right double-clicks, cancellation, charged physics, three handles")
    print("PASS: two distinct cracks for fast left/right click pairs, next single remains immediate")
    print("PASS: four bundled recorded sound options")
    print("PASS: 1,200 simulation frames, repeated cracks, finite coordinates, anchor tracking, multi-display jump, length constraints")
} else if CommandLine.arguments.contains("--physics-golden") {
    // Fixed script shared with the Windows, Linux, and web ports.
    // Prints one state per line. Coordinates stay in the macOS y-up space.
    let simulation = WhipSimulation()
    func dump(_ tag: String) {
        var parts = [tag, String(simulation.particles.count)]
        func num(_ value: Double) -> String { String(format: "%.9f", value) }
        parts.append(contentsOf: [
            num(simulation.anchor.x), num(simulation.anchor.y),
            num(simulation.handleAngle), num(simulation.loadAmount),
            num(simulation.wave), num(simulation.flash),
            num(simulation.hangRoll), num(simulation.waveStrength),
            num(simulation.releaseBend), num(simulation.cursorTravel)
        ])
        for particle in simulation.particles {
            parts.append(num(particle.p.x))
            parts.append(num(particle.p.y))
        }
        print(parts.joined(separator: " "))
    }
    for i in 0..<180 {
        let t = Double(i) / 60.0
        simulation.step(to: CGPoint(x: 500 + sin(t) * 200, y: 500 + cos(t * 2) * 100), length: 340)
        if i == 40 { simulation.crack() }
        if i == 0 || i == 40 || i == 41 || i == 70 || i == 110 || i == 179 { dump("move-\(i)") }
    }
    for i in 0..<240 {
        simulation.step(to: CGPoint(x: 200, y: 200), length: 340, charge: 1)
        if i == 30 || i == 239 { dump("load-\(i)") }
    }
    simulation.crack(strength: 1.65)
    dump("release-0")
    for i in 0..<80 {
        simulation.step(to: CGPoint(x: 200, y: 200), length: 340)
        if i == 8 || i == 20 || i == 45 || i == 79 { dump("settle-\(i)") }
    }
    simulation.step(to: CGPoint(x: -1500, y: 900), length: 260)
    dump("jump")
} else {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
