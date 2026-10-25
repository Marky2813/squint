// Squint.app: the menu bar app users install.
//
// Host mode (double-clicked): checks Ollama + Gemma (first-run setup window), starts the
// bundled Python engine (`python -m squint watch --app`), reads its API URL from stdout,
// and shows a toast + review window when a screenshot has something to hide.
// Client mode (`--url http://127.0.0.1:PORT/?t=TOKEN`): only the toast and review window,
// for `squint watch` from a terminal. All detection logic lives in Python.

import AppKit
import ServiceManagement
import SwiftUI

let gemmaModel = "gemma3:4b"  // keep in sync with squint.core.classify.DEFAULT_MODEL
let ollamaBase = "http://127.0.0.1:11434"

// MARK: - API

struct BoxRect: Codable { let x, y, width, height: Double }

struct FindingItem: Codable, Identifiable {
    let id: Int
    let rule: String
    let tier: String
    let preview: String
    let bbox: BoxRect?
    var flagged: Bool
}

struct DrawnBox: Codable, Identifiable { let id: Int; let x, y, width, height: Double }

struct ImageInfo: Codable { let name: String; let width: Double; let height: Double }

struct Review: Codable {
    let image: ImageInfo
    let source: String
    let classifier_offline: Bool
    var style: String
    let styles: [String]
    var findings: [FindingItem]
    var boxes: [DrawnBox]
}

struct Version: Codable { let version: Int }
struct ChangeReply: Codable { let copied: Bool? }

final class Api {
    let base: String
    let token: String

    init?(url: String) {
        guard let parts = URLComponents(string: url),
              let token = parts.queryItems?.first(where: { $0.name == "t" })?.value,
              let host = parts.host, let port = parts.port, host == "127.0.0.1"
        else { return nil }
        self.base = "http://\(host):\(port)"
        self.token = token
    }

    private func url(_ path: String, _ extra: [URLQueryItem] = []) -> URL {
        var parts = URLComponents(string: base + path)!
        parts.queryItems = [URLQueryItem(name: "t", value: token)] + extra
        return parts.url!
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        let (data, _) = try await URLSession.shared.data(from: url(path))
        return try JSONDecoder().decode(T.self, from: data)
    }

    func post<T: Decodable>(_ path: String, _ body: some Encodable = [String: String]()) async throws -> T {
        var request = URLRequest(url: url(path))
        request.httpMethod = "POST"
        request.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(T.self, from: data)
    }

    /// The redacted image: exactly what is on the clipboard.
    func redactedImage() async throws -> Data {
        let (data, _) = try await URLSession.shared.data(
            from: url("/api/image", [URLQueryItem(name: "view", value: "redacted")]))
        return data
    }
}

// MARK: - Review model

@MainActor
final class Model: ObservableObject {
    let api: Api
    @Published var review: Review?
    @Published var image: NSImage?
    @Published var imageRevision = 0
    @Published var hud: String?
    var version = -1
    var onNewReview: ((Review) -> Void)?
    private var hudTask: Task<Void, Never>?

    init(api: Api) { self.api = api }

    func poll() async {
        guard let current: Version = try? await api.get("/api/version"),
              current.version != version else { return }
        version = current.version
        guard await reload(), let review else { return }
        if review.findings.contains(where: \.flagged) { onNewReview?(review) }
    }

    @discardableResult
    func reload() async -> Bool {
        guard let next: Review = try? await api.get("/api/findings"),
              let data = try? await api.redactedImage(),
              let picture = NSImage(data: data) else { return false }
        review = next
        image = picture
        imageRevision += 1
        return true
    }

    private func apply(_ path: String, _ body: some Encodable = [String: String]()) {
        Task {
            let reply: ChangeReply? = try? await api.post(path, body)
            await reload()
            showHud(reply?.copied == false || reply == nil ? "Couldn’t Copy" : "Copied")
        }
    }

    func toggle(_ id: Int) { apply("/api/findings/\(id)/toggle") }
    func removeBox(_ id: Int) { apply("/api/boxes/\(id)/delete") }
    func setStyle(_ style: String) { apply("/api/style", ["style": style]) }
    func addBox(_ rect: CGRect) {
        apply("/api/boxes", ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height])
    }

    func showHud(_ text: String) {
        hudTask?.cancel()
        withAnimation(.easeOut(duration: 0.15)) { hud = text }
        hudTask = Task {
            try? await Task.sleep(for: .seconds(1.2))
            guard !Task.isCancelled else { return }
            withAnimation(.easeIn(duration: 0.3)) { hud = nil }
        }
    }
}

// MARK: - The squint glyph

/// A narrowed eye: an almond whose upper lid cuts the top of the pupil.
/// Unit coordinates with y pointing down; `flipY` maps them into a y-up CoreGraphics rect.
func squintPaths(in r: CGRect, flipY: Bool = false) -> (outline: CGPath, pupil: CGPath) {
    func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
        CGPoint(x: r.minX + x * r.width, y: flipY ? r.maxY - y * r.height : r.minY + y * r.height)
    }
    let outline = CGMutablePath()
    outline.move(to: p(0.04, 0.5))
    outline.addQuadCurve(to: p(0.96, 0.5), control: p(0.5, 0.26))
    outline.addQuadCurve(to: p(0.04, 0.5), control: p(0.5, 0.74))
    outline.closeSubpath()
    let radius = 0.155 * r.width
    let center = p(0.5, 0.5)
    let circle = CGPath(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius,
                                          width: 2 * radius, height: 2 * radius), transform: nil)
    return (outline, circle.intersection(outline))
}

struct SquintGlyph: View {
    var lineWidth: CGFloat = 1.5
    var body: some View {
        Canvas { context, size in
            let side = min(size.width, size.height)
            let rect = CGRect(x: (size.width - side) / 2, y: (size.height - side) / 2, width: side, height: side)
            let paths = squintPaths(in: rect)
            context.stroke(Path(paths.outline), with: .foreground,
                           style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
            context.fill(Path(paths.pupil), with: .foreground)
        }
    }
}

/// The app icon: a graphite squircle on Apple's 1024 grid with a white squint glyph.
func drawAppIcon(_ ctx: CGContext, size: CGFloat) {
    let inset = size * 100 / 1024
    let tile = CGRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
    let shape = CGPath(roundedRect: tile, cornerWidth: tile.width * 0.225, cornerHeight: tile.width * 0.225, transform: nil)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -size * 0.01), blur: size * 0.03,
                  color: CGColor(gray: 0, alpha: 0.35))
    ctx.addPath(shape)
    ctx.setFillColor(CGColor(gray: 0.1, alpha: 1))
    ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(shape)
    ctx.clip()
    let gradient = CGGradient(colorSpace: CGColorSpaceCreateDeviceRGB(), colorComponents: [
        0.25, 0.26, 0.29, 1,
        0.09, 0.09, 0.11, 1,
    ], locations: [0, 1], count: 2)!
    ctx.drawLinearGradient(gradient, start: CGPoint(x: 0, y: tile.maxY), end: CGPoint(x: 0, y: tile.minY), options: [])
    let glyphRect = tile.insetBy(dx: tile.width * 0.2, dy: tile.width * 0.2)
    let paths = squintPaths(in: glyphRect, flipY: true)
    ctx.setStrokeColor(CGColor(gray: 1, alpha: 1))
    ctx.setFillColor(CGColor(gray: 1, alpha: 1))
    ctx.setLineWidth(tile.width * 0.045)
    ctx.setLineCap(.round)
    ctx.setLineJoin(.round)
    ctx.addPath(paths.outline)
    ctx.strokePath()
    ctx.addPath(paths.pupil)
    ctx.fillPath()
    ctx.restoreGState()
}

func appIconImage(size: CGFloat) -> NSImage {
    NSImage(size: NSSize(width: size, height: size), flipped: false) { _ in
        guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
        drawAppIcon(ctx, size: size)
        return true
    }
}

func menuBarImage() -> NSImage {
    let image = NSImage(size: NSSize(width: 20, height: 18), flipped: false) { rect in
        guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
        let paths = squintPaths(in: CGRect(x: 1, y: 0, width: 18, height: 18), flipY: true)
        ctx.setLineWidth(1.6)
        ctx.setLineJoin(.round)
        ctx.addPath(paths.outline)
        ctx.strokePath()
        ctx.addPath(paths.pupil)
        ctx.fillPath()
        return true
    }
    image.isTemplate = true
    return image
}

/// `Squint --render-icon out.png` writes the 1024px icon (used by the app build script).
func renderIcon(to path: String) -> Int32 {
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                     colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
          let context = NSGraphicsContext(bitmapImageRep: rep) else { return 1 }
    NSGraphicsContext.current = context
    drawAppIcon(context.cgContext, size: 1024)
    context.flushGraphics()
    guard let png = rep.representation(using: .png, properties: [:]),
          (try? png.write(to: URL(fileURLWithPath: path))) != nil else { return 1 }
    return 0
}

// MARK: - Toast

struct ToastView: View {
    let title: String
    let subtitle: String
    let onHover: (Bool) -> Void
    var onClose: () -> Void = {}
    @State private var hovering = false

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(nsImage: appIconImage(size: 80))
                .resizable()
                .frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 1) {
                HStack(alignment: .firstTextBaseline) {
                    Text("Squint").font(.system(size: 13, weight: .semibold))
                    Spacer()
                    Text("now").font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Text(title).font(.system(size: 13))
                Text(subtitle).font(.system(size: 13)).foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(width: 356, alignment: .leading)
        .contentShape(Rectangle())
        .overlay(alignment: .topLeading) {
            if hovering {  // like a system banner: a close button appears on hover
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                        .frame(width: 18, height: 18)
                        .background(.regularMaterial, in: Circle())
                        .overlay(Circle().strokeBorder(Color(nsColor: .separatorColor), lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .offset(x: 4, y: 4)
            }
        }
        .onHover { inside in
            hovering = inside
            onHover(inside)
        }
    }
}

final class ClickHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

@MainActor
final class Toast {
    private var panel: NSPanel?
    private var hide: DispatchWorkItem?

    func show(title: String, subtitle: String, seconds: Double = 5, onClick: @escaping () -> Void) {
        panel?.orderOut(nil)
        let view = ToastView(title: title, subtitle: subtitle, onHover: { [weak self] hovering in
            hovering ? self?.hide?.cancel() : self?.scheduleHide(after: 2.5)
        }, onClose: { [weak self] in self?.dismiss() })
        .onTapGesture(perform: onClick)
        let host = ClickHostingView(rootView: view)
        let size = host.fittingSize

        // A live vibrancy view (stays "active" although the panel never becomes key).
        let effect = NSVisualEffectView(frame: NSRect(origin: .zero, size: size))
        effect.material = .popover
        effect.state = .active
        effect.blendingMode = .behindWindow
        effect.wantsLayer = true
        effect.layer?.cornerRadius = 22
        effect.layer?.cornerCurve = .continuous
        effect.layer?.masksToBounds = true
        effect.layer?.borderWidth = 0.5
        effect.layer?.borderColor = NSColor.separatorColor.cgColor
        host.frame = effect.bounds
        host.autoresizingMask = [.width, .height]
        effect.addSubview(host)

        let next = NSPanel(contentRect: effect.frame, styleMask: [.borderless, .nonactivatingPanel],
                           backing: .buffered, defer: false)
        next.contentView = effect
        next.isOpaque = false
        next.backgroundColor = .clear
        next.hasShadow = true
        next.level = .statusBar
        next.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        guard let screen = NSScreen.main?.visibleFrame else { return }
        let final = NSRect(x: screen.maxX - size.width - 12, y: screen.maxY - size.height - 12,
                           width: size.width, height: size.height)
        next.setFrame(final.offsetBy(dx: 40, dy: 0), display: false)
        next.alphaValue = 0
        next.orderFrontRegardless()
        // Animate the frame (not the origin: NSWindow ignores animated setFrameOrigin).
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.35
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            next.animator().setFrame(final, display: true)
            next.animator().alphaValue = 1
        }
        panel = next
        scheduleHide(after: seconds)
    }

    private func scheduleHide(after seconds: Double) {
        hide?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.dismiss() }
        hide = work
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
    }

    func dismiss() {
        hide?.cancel()
        guard let current = panel else { return }
        panel = nil
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.25
            current.animator().setFrame(current.frame.offsetBy(dx: 40, dy: 0), display: true)
            current.animator().alphaValue = 0
        }) { current.orderOut(nil) }
    }
}

// MARK: - Review window

enum Target: Equatable { case finding(Int), box(Int) }

struct ReviewView: View {
    @ObservedObject var model: Model
    @State private var dragStart: CGPoint?
    @State private var dragRect: CGRect?
    @State private var pending: CGRect?  // a drawn box shown solid until the new image arrives
    @State private var hover: Target?

    static let hintHeight: CGFloat = 32

    var body: some View {
        VStack(spacing: 0) {
            screenshot
                .overlay(alignment: .bottom) { hud }
            Divider()
            hintBar
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    /// A Preview-style status line: says what a click will do right now.
    var hintBar: some View {
        HStack(spacing: 6) {
            Image(systemName: hintSymbol).foregroundStyle(.secondary)
            Text(hintText).lineLimit(1).minimumScaleFactor(0.8)
        }
        .font(.system(size: 12))
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity)
        .frame(height: Self.hintHeight)
        .animation(.easeOut(duration: 0.12), value: hintText)
    }

    var hintText: String {
        switch hover {
        case .finding(let id):
            let hidden = model.review?.findings.first { $0.id == id }?.flagged ?? false
            return hidden ? "Click to show this" : "Click to hide this"
        case .box:
            return "Click to remove this box"
        case nil:
            if dragRect != nil { return "Release to cover this area" }
            return "Click an item to hide or show it · Drag to cover anything else"
        }
    }

    var hintSymbol: String {
        switch hover {
        case .finding(let id):
            let hidden = model.review?.findings.first { $0.id == id }?.flagged ?? false
            return hidden ? "eye" : "eye.slash"
        case .box: return "xmark.square"
        case nil: return dragRect != nil ? "rectangle.dashed" : "cursorarrow.click"
        }
    }

    var screenshot: some View {
        GeometryReader { geo in
            if let review = model.review, let image = model.image {
                let scale = min(geo.size.width / review.image.width, geo.size.height / review.image.height)
                let size = CGSize(width: review.image.width * scale, height: review.image.height * scale)
                ZStack(alignment: .topLeading) {
                    Image(nsImage: image).resizable().interpolation(.high)
                        .frame(width: size.width, height: size.height)
                    ForEach(review.findings) { finding in
                        if let box = finding.bbox {
                            findingMark(finding, rect(box, scale))
                        }
                    }
                    ForEach(review.boxes) { box in
                        if hover == .box(box.id) {
                            boxMark(rect(BoxRect(x: box.x, y: box.y, width: box.width, height: box.height), scale))
                        }
                    }
                    if let pending {
                        Rectangle().fill(Color(nsColor: .labelColor))
                            .frame(width: pending.width, height: pending.height)
                            .offset(x: pending.minX, y: pending.minY)
                    }
                    if let dragRect {
                        Rectangle().fill(Color.accentColor.opacity(0.12))
                            .overlay(Rectangle().strokeBorder(Color.accentColor, lineWidth: 1.5))
                            .frame(width: dragRect.width, height: dragRect.height)
                            .offset(x: dragRect.minX, y: dragRect.minY)
                    }
                }
                .frame(width: size.width, height: size.height)
                .contentShape(Rectangle())
                .gesture(drawOrClick(review, scale: scale, bounds: CGRect(origin: .zero, size: size)))
                .onContinuousHover { phase in
                    switch phase {
                    case .active(let point):
                        hover = target(at: point, review, scale)
                        (hover == nil ? NSCursor.crosshair : NSCursor.pointingHand).set()
                    case .ended:
                        hover = nil
                        NSCursor.arrow.set()
                    }
                }
                .contextMenu { styleMenu(review) }
                .position(x: geo.size.width / 2, y: geo.size.height / 2)
                .onChange(of: model.imageRevision) { pending = nil }
                .overlay(alignment: .top) { offlineNote(review) }
            }
        }
    }

    func rect(_ box: BoxRect, _ scale: CGFloat) -> CGRect {
        CGRect(x: box.x * scale, y: box.y * scale, width: box.width * scale, height: box.height * scale)
    }

    func target(at point: CGPoint, _ review: Review, _ scale: CGFloat) -> Target? {
        for box in review.boxes.reversed()
        where rect(BoxRect(x: box.x, y: box.y, width: box.width, height: box.height), scale)
            .insetBy(dx: -2, dy: -2).contains(point) {
            return .box(box.id)
        }
        for finding in review.findings {
            if let box = finding.bbox, rect(box, scale).insetBy(dx: -2, dy: -2).contains(point) {
                return .finding(finding.id)
            }
        }
        return nil
    }

    /// One gesture for everything: a click toggles what is under it, a drag draws a box.
    func drawOrClick(_ review: Review, scale: CGFloat, bounds: CGRect) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                let start = dragStart ?? value.startLocation
                dragStart = start
                guard hypot(value.translation.width, value.translation.height) >= 4 else { return }
                dragRect = CGRect(x: min(start.x, value.location.x), y: min(start.y, value.location.y),
                                  width: abs(value.location.x - start.x), height: abs(value.location.y - start.y))
                    .intersection(bounds)
            }
            .onEnded { value in
                defer { dragStart = nil; dragRect = nil }
                guard let drawn = dragRect, drawn.width >= 3, drawn.height >= 3 else {
                    switch target(at: value.startLocation, review, scale) {
                    case .finding(let id): model.toggle(id)
                    case .box(let id): model.removeBox(id)
                    case nil: break
                    }
                    return
                }
                pending = drawn
                model.addBox(CGRect(x: drawn.minX / scale, y: drawn.minY / scale,
                                    width: drawn.width / scale, height: drawn.height / scale))
            }
    }

    @ViewBuilder
    func findingMark(_ finding: FindingItem, _ r: CGRect) -> some View {
        let hovered = hover == .finding(finding.id)
        if !finding.flagged || hovered {
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(Color.accentColor.opacity(hovered && !finding.flagged ? 0.10 : 0))
                .overlay(
                    RoundedRectangle(cornerRadius: 3, style: .continuous).strokeBorder(
                        hovered ? Color.accentColor : Color.accentColor.opacity(0.85),
                        style: StrokeStyle(lineWidth: hovered ? 1.5 : 1, dash: finding.flagged ? [] : [3, 2]))
                )
                .frame(width: r.width, height: r.height)
                .offset(x: r.minX, y: r.minY)
                .allowsHitTesting(false)
        }
    }

    func boxMark(_ r: CGRect) -> some View {
        RoundedRectangle(cornerRadius: 2, style: .continuous)
            .strokeBorder(Color.accentColor, lineWidth: 1.5)
            .overlay(alignment: .topTrailing) {
                Image(systemName: "xmark.circle.fill")
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(.white, Color.accentColor)
                    .font(.system(size: 14))
                    .offset(x: 7, y: -7)
            }
            .frame(width: r.width, height: r.height)
            .offset(x: r.minX, y: r.minY)
            .allowsHitTesting(false)
    }

    @ViewBuilder
    func styleMenu(_ review: Review) -> some View {
        ForEach(review.styles, id: \.self) { style in
            Button {
                model.setStyle(style)
            } label: {
                if style == review.style {
                    Label(style.capitalized, systemImage: "checkmark")
                } else {
                    Text(style.capitalized)
                }
            }
        }
    }

    @ViewBuilder
    func offlineNote(_ review: Review) -> some View {
        if review.classifier_offline {
            Label("Gemma is offline, so everything uncertain is hidden", systemImage: "exclamationmark.triangle")
                .font(.system(size: 11, weight: .medium))
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(.regularMaterial, in: Capsule())
                .padding(.top, 8)
        }
    }

    @ViewBuilder
    var hud: some View {
        if let text = model.hud {
            Label(text, systemImage: text == "Copied" ? "doc.on.clipboard" : "exclamationmark.triangle")
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(.regularMaterial, in: Capsule())
                .overlay(Capsule().strokeBorder(Color(nsColor: .separatorColor), lineWidth: 0.5))
                .padding(.bottom, 14)
                .transition(.opacity.combined(with: .scale(scale: 0.95)))
                .allowsHitTesting(false)
        }
    }
}

/// Esc, Space and ⌘W close the review, like Quick Look.
final class ReviewWindow: NSWindow {
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 || event.keyCode == 49 { orderOut(nil) } else { super.keyDown(with: event) }
    }
    override func cancelOperation(_ sender: Any?) { orderOut(nil) }
}

// MARK: - Engine (the bundled Python process)

enum Log {
    static let url: URL = {
        let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Squint")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("squint.log")
        FileManager.default.createFile(atPath: file.path, contents: nil)  // fresh log each launch
        return file
    }()
    static let handle = try? FileHandle(forWritingTo: url)

    static func write(_ line: String) {
        handle?.write(Data((line + "\n").utf8))
    }
}

final class Engine {
    private var process: Process?
    private var input: Pipe?
    private var buffer = ""
    var onURL: ((String) -> Void)?
    var onExit: (() -> Void)?
    var isRunning: Bool { process?.isRunning == true }

    static var resources: URL { Bundle.main.resourceURL! }
    /// The bundled Python for this Mac's CPU (the app is universal; each slice picks its own).
    static var python: URL {
        #if arch(arm64)
        resources.appendingPathComponent("python-arm64/bin/python3")
        #else
        resources.appendingPathComponent("python-x86_64/bin/python3")
        #endif
    }
    static var isBundled: Bool { FileManager.default.fileExists(atPath: python.path) }

    func start() {
        let python = Self.python
        let process = Process()
        process.executableURL = python
        process.arguments = ["-m", "squint", "watch", "--app"]
        var env = ProcessInfo.processInfo.environment.filter { !$0.key.hasPrefix("PYTHON") }
        env["SQUINT_BIN_DIR"] = Self.resources.appendingPathComponent("bin").path
        env["PYTHONDONTWRITEBYTECODE"] = "1"  // never write into the signed bundle
        env["PYTHONNOUSERSITE"] = "1"
        process.environment = env
        let input = Pipe(), output = Pipe()
        process.standardInput = input  // the engine exits when this closes
        process.standardOutput = output
        process.standardError = output
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.consume(String(decoding: data, as: UTF8.self)) }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.onExit?() }
        }
        do {
            try process.run()
            Log.write("engine started (pid \(process.processIdentifier))")
        } catch {
            Log.write("engine failed to start: \(error)")
            onExit?()
            return
        }
        self.process = process
        self.input = input
    }

    private func consume(_ text: String) {
        buffer += text
        while let newline = buffer.firstIndex(of: "\n") {
            let line = String(buffer[..<newline])
            buffer.removeSubrange(...newline)
            if line.hasPrefix("url ") {
                onURL?(String(line.dropFirst(4)))  // not logged: it carries the API token
            } else {
                Log.write(line)
            }
        }
    }

    /// Close the lifeline so the engine restores the thumbnail setting and exits.
    func stop(then done: @escaping () -> Void) {
        guard let process, process.isRunning else { done(); return }
        onExit = nil
        try? input?.fileHandleForWriting.close()
        DispatchQueue.global().async {
            let deadline = Date().addingTimeInterval(4)
            while process.isRunning && Date() < deadline { usleep(50_000) }
            if process.isRunning { process.terminate() }
            DispatchQueue.main.async(execute: done)
        }
    }
}

// MARK: - First-run setup (Ollama + Gemma)

struct OllamaTags: Codable { struct Entry: Codable { let name: String }; let models: [Entry] }
struct PullLine: Codable { let status: String?; let total: Double?; let completed: Double?; let error: String? }

@MainActor
final class Setup: ObservableObject {
    enum OllamaState: Equatable { case checking, missing, stopped, running }
    enum GemmaState: Equatable { case unknown, missing, downloading(Double), ready, failed(String) }

    @Published var ollama = OllamaState.checking
    @Published var gemma = GemmaState.unknown
    @Published var openAtLogin = true
    var ready: Bool { ollama == .running && gemma == .ready }

    static var ollamaApp: URL? {
        NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.electron.ollama")
            ?? ["/Applications/Ollama.app", NSHomeDirectory() + "/Applications/Ollama.app"]
                .map(URL.init(fileURLWithPath:))
                .first { FileManager.default.fileExists(atPath: $0.path) }
    }

    func refresh() async {
        var request = URLRequest(url: URL(string: ollamaBase + "/api/tags")!)
        request.timeoutInterval = 1.5
        guard let (data, _) = try? await URLSession.shared.data(for: request),
              let tags = try? JSONDecoder().decode(OllamaTags.self, from: data) else {
            ollama = Self.ollamaApp == nil ? .missing : .stopped
            return
        }
        ollama = .running
        if case .downloading = gemma { return }
        gemma = tags.models.contains { $0.name == gemmaModel } ? .ready : .missing
    }

    /// Start Ollama in the background (no window); it is a menu bar app itself.
    func launchOllama() {
        guard let app = Self.ollamaApp else { return }
        let config = NSWorkspace.OpenConfiguration()
        config.activates = false
        config.hides = true
        NSWorkspace.shared.openApplication(at: app, configuration: config)
    }

    func pullGemma() {
        gemma = .downloading(0)
        Task {
            var request = URLRequest(url: URL(string: ollamaBase + "/api/pull")!)
            request.httpMethod = "POST"
            request.httpBody = try? JSONEncoder().encode(["model": gemmaModel, "name": gemmaModel])
            request.timeoutInterval = 3600
            do {
                let (bytes, _) = try await URLSession.shared.bytes(for: request)
                for try await line in bytes.lines {
                    guard let update = try? JSONDecoder().decode(PullLine.self, from: Data(line.utf8)) else { continue }
                    if let error = update.error { gemma = .failed(error); return }
                    if let total = update.total, let done = update.completed, total > 0 {
                        gemma = .downloading(done / total)
                    }
                    if update.status == "success" { gemma = .ready; return }
                }
                await refresh()
            } catch {
                gemma = .failed(error.localizedDescription)
            }
        }
    }
}

struct SetupView: View {
    @ObservedObject var setup: Setup
    let start: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Image(nsImage: appIconImage(size: 128)).resizable().frame(width: 80, height: 80)
            VStack(spacing: 6) {
                Text("Welcome to Squint").font(.system(size: 20, weight: .semibold))
                Text("Squint checks every screenshot for passwords, keys and personal details, and puts a redacted copy on your clipboard. Everything stays on your Mac.")
                    .font(.system(size: 13))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(spacing: 0) {
                row(symbol: "shippingbox", title: "Ollama", detail: "Runs AI models locally") { ollamaStatus }
                Divider().padding(.leading, 44)
                row(symbol: "sparkles", title: "Gemma 3", detail: "Decides what’s private · 3.3 GB") { gemmaStatus }
            }
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Color(nsColor: .separatorColor), lineWidth: 0.5))
            Toggle("Open Squint at login", isOn: $setup.openAtLogin)
                .toggleStyle(.checkbox)
                .font(.system(size: 13))
                .frame(maxWidth: .infinity, alignment: .leading)
            Button(action: start) {
                Text("Start Squint").frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .disabled(!setup.ready)
        }
        .padding(28)
        .frame(width: 420)
    }

    func row(symbol: String, title: String, detail: String, @ViewBuilder status: () -> some View) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 17)).foregroundStyle(.secondary).frame(width: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 13, weight: .medium))
                Text(detail).font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            status()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(height: 52)
    }

    var done: some View {
        Image(systemName: "checkmark.circle.fill").font(.system(size: 17)).foregroundStyle(.green)
    }

    @ViewBuilder
    var ollamaStatus: some View {
        switch setup.ollama {
        case .checking: ProgressView().controlSize(.small)
        case .missing:
            Button("Download") { NSWorkspace.shared.open(URL(string: "https://ollama.com/download/mac")!) }
        case .stopped:
            Button("Open") { setup.launchOllama() }
        case .running: done
        }
    }

    @ViewBuilder
    var gemmaStatus: some View {
        switch setup.gemma {
        case .unknown: Text("—").foregroundStyle(.tertiary)
        case .missing: Button("Download") { setup.pullGemma() }
        case .downloading(let fraction):
            HStack(spacing: 8) {
                ProgressView(value: fraction).frame(width: 90)
                Text("\(Int(fraction * 100))%").font(.system(size: 11).monospacedDigit()).foregroundStyle(.secondary)
            }
        case .failed:
            Button("Retry") { setup.pullGemma() }
        case .ready: done
        }
    }
}

// MARK: - App

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var model: Model?
    let toast = Toast()
    var window: NSWindow?
    var setupWindow: NSWindow?
    let setup = Setup()
    let engine = Engine()
    var statusItem: NSStatusItem?
    var status = "Starting…"
    var poller: Timer?
    var launchedAtLogin = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        let args = CommandLine.arguments
        if let index = args.firstIndex(of: "--url") {
            guard index + 1 < args.count, let api = Api(url: args[index + 1]) else {
                FileHandle.standardError.write("usage: Squint --url http://127.0.0.1:PORT/?t=TOKEN\n".data(using: .utf8)!)
                exit(2)
            }
            connect(api)  // client of a terminal `squint watch`
            return
        }
        // One Squint at a time (e.g. one opened from the DMG and one from Applications):
        // two would both rewrite the clipboard. Wake the running one so it says it's on.
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: Bundle.main.bundleIdentifier ?? "")
            .filter { $0 != .current }
        if let running = others.first, let url = running.bundleURL {
            let config = NSWorkspace.OpenConfiguration()
            config.activates = false
            NSWorkspace.shared.openApplication(at: url, configuration: config) { _, _ in exit(0) }
            return
        }
        setUpMenuBar()
        launchedAtLogin = Self.launchedAtLogin
        guard Engine.isBundled else {
            status = "Squint is incomplete; reinstall it"
            return
        }
        Task { await prepare() }
    }

    // MARK: Startup

    func prepare() async {
        await setup.refresh()
        // Confirm right away unless setup is needed (its window is the confirmation).
        if (setup.ready || setup.ollama == .stopped) && !launchedAtLogin {
            announceRunning(again: false)
        }
        if setup.ollama == .stopped {
            setup.launchOllama()
            for _ in 0..<40 where setup.ollama != .running {  // up to ~20 s
                try? await Task.sleep(for: .milliseconds(500))
                await setup.refresh()
            }
        }
        if setup.ready {
            startEngine()
        } else {
            showSetup()
        }
    }

    func showSetup() {
        status = "Waiting for setup"
        if setupWindow == nil {
            let view = SetupView(setup: setup) { [weak self] in self?.finishSetup() }
            let win = NSWindow(contentRect: .zero, styleMask: [.titled, .closable, .fullSizeContentView],
                               backing: .buffered, defer: false)
            win.titlebarAppearsTransparent = true
            win.titleVisibility = .hidden
            win.isReleasedWhenClosed = false
            win.contentView = NSHostingView(rootView: view)
            win.center()
            setupWindow = win
            Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] timer in
                Task { @MainActor in
                    guard let self, self.setupWindow?.isVisible == true else { timer.invalidate(); return }
                    await self.setup.refresh()
                }
            }
        }
        NSApp.activate(ignoringOtherApps: true)
        setupWindow?.makeKeyAndOrderFront(nil)
    }

    func finishSetup() {
        setupWindow?.orderOut(nil)
        setOpenAtLogin(setup.openAtLogin)
        startEngine()
        announceRunning(again: false)
    }

    /// Squint has no Dock icon, so opening it must visibly confirm it is running.
    func announceRunning(again: Bool) {
        toast.show(title: again ? "Squint is already on" : "Squint is on",
                   subtitle: "It lives in the menu bar · Take a screenshot to try it",
                   seconds: 5) { [weak self] in
            self?.toast.dismiss()
            self?.statusItem?.button?.performClick(nil)
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if setupWindow?.isVisible == true || status == "Waiting for setup" {
            showSetup()
        } else if statusItem != nil {
            announceRunning(again: true)
        }
        return false
    }

    static var launchedAtLogin: Bool {
        guard let event = NSAppleEventManager.shared().currentAppleEvent else { return false }
        return event.eventID == kAEOpenApplication
            && event.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem
    }

    func startEngine() {
        status = "Getting ready…"
        engine.onURL = { [weak self] url in
            guard let self, let api = Api(url: url) else { return }
            self.status = "Watching screenshots"
            self.connect(api)
        }
        engine.onExit = { [weak self] in
            self?.status = "Squint stopped"
            self?.poller?.invalidate()
        }
        engine.start()
    }

    func connect(_ api: Api) {
        let model = Model(api: api)
        model.onNewReview = { [weak self] review in self?.announce(review) }
        self.model = model
        poller?.invalidate()
        poller = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.model?.poll() }
        }
    }

    // MARK: Toast + review

    func announce(_ review: Review) {
        if window?.isVisible == true {  // already reviewing: the window updates in place
            fit(window!, to: review)
            return
        }
        let count = review.findings.filter(\.flagged).count
        let title = count == 1 ? "Hid 1 thing in your screenshot" : "Hid \(count) things in your screenshot"
        let subtitle = review.classifier_offline
            ? "Gemma is offline, so everything uncertain is hidden"
            : "The redacted copy is on your clipboard"
        toast.show(title: title, subtitle: subtitle) { [weak self] in self?.openReview() }
    }

    func openReview() {
        toast.dismiss()
        guard let model, let review = model.review else { return }
        if window == nil {
            let win = ReviewWindow(contentRect: .zero, styleMask: [.titled, .closable, .resizable, .miniaturizable],
                                   backing: .buffered, defer: false)
            win.titlebarAppearsTransparent = true
            win.titleVisibility = .hidden
            win.isReleasedWhenClosed = false
            win.contentView = NSHostingView(rootView: ReviewView(model: model))
            window = win
        }
        fit(window!, to: review)
        window?.center()
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    /// Size the window to the screenshot's own shape (no empty margins): natural size in
    /// points, small crops enlarged to a readable width, large ones capped to 70% of the screen.
    func fit(_ win: NSWindow, to review: Review) {
        guard let screen = win.screen ?? NSScreen.main else { return }
        let backing = screen.backingScaleFactor
        let natural = CGSize(width: review.image.width / backing, height: review.image.height / backing)
        let chrome = ReviewView.hintHeight + 1
        let limit = CGSize(width: screen.visibleFrame.width * 0.7,
                           height: screen.visibleFrame.height * 0.7 - chrome)
        let enlarge = min(2, max(1, 480 / natural.width))
        let scale = min(enlarge, limit.width / natural.width, limit.height / natural.height)
        win.setContentSize(CGSize(width: (natural.width * scale).rounded(),
                                  height: (natural.height * scale).rounded() + chrome))
    }

    // MARK: Menu bar

    func setUpMenuBar() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = menuBarImage()
        item.button?.toolTip = "Squint"
        let menu = NSMenu()
        menu.delegate = self
        item.menu = menu
        statusItem = item
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let state = NSMenuItem(title: status, action: nil, keyEquivalent: "")
        state.isEnabled = false
        menu.addItem(state)
        if status == "Squint stopped" {
            menu.addItem(item("Restart Squint", #selector(restart)))
        }
        if status == "Waiting for setup" {
            menu.addItem(item("Finish Setup…", #selector(openSetup)))
        }
        menu.addItem(.separator())
        let review = item("Review Last Screenshot", #selector(reviewLast))
        review.isEnabled = model?.review != nil
        menu.addItem(review)
        menu.addItem(.separator())
        let login = item("Open at Login", #selector(toggleLogin))
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        menu.addItem(login)
        menu.addItem(item("Show Log", #selector(showLog)))
        menu.addItem(.separator())
        menu.addItem(item("Quit Squint", #selector(quit), key: "q"))
    }

    func item(_ title: String, _ action: Selector, key: String = "") -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.target = self
        return item
    }

    @objc func reviewLast() { openReview() }
    @objc func openSetup() { showSetup() }
    @objc func restart() { startEngine() }
    @objc func showLog() { NSWorkspace.shared.open(Log.url) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func toggleLogin() { setOpenAtLogin(SMAppService.mainApp.status != .enabled) }

    func setOpenAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            Log.write("open at login: \(error)")
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard engine.isRunning else { return .terminateNow }
        engine.stop { NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }
}

@main
struct SquintMain {
    static func main() {
        let args = CommandLine.arguments
        if let index = args.firstIndex(of: "--render-icon"), index + 1 < args.count {
            exit(renderIcon(to: args[index + 1]))
        }
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
}
