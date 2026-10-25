// Squint review app: a background app that shows a toast when a screenshot has sensitive
// text, and a small review window to flag/dismiss items. It is a thin client of the Python
// API (launched with --url http://127.0.0.1:PORT/?t=TOKEN); all logic lives in Python.

import AppKit
import SwiftUI

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

struct ImageInfo: Codable { let name: String; let width: Double; let height: Double }

struct Review: Codable {
    let image: ImageInfo
    let source: String
    let classifier_offline: Bool
    var style: String
    let styles: [String]
    var findings: [FindingItem]
}

struct Version: Codable { let version: Int }
struct ToggleReply: Codable { let id: Int; let flagged: Bool; let copied: Bool? }
struct StyleReply: Codable { let style: String; let copied: Bool? }

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

    private func url(_ path: String) -> URL {
        var parts = URLComponents(string: base + path)!
        parts.queryItems = [URLQueryItem(name: "t", value: token)]
        return parts.url!
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        let (data, _) = try await URLSession.shared.data(from: url(path))
        return try JSONDecoder().decode(T.self, from: data)
    }

    func post<T: Decodable>(_ path: String, _ body: [String: String] = [:]) async throws -> T {
        var request = URLRequest(url: url(path))
        request.httpMethod = "POST"
        request.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func imageData() async throws -> Data {
        let (data, _) = try await URLSession.shared.data(from: url("/api/image"))
        return data
    }
}

// MARK: - Model

@MainActor
final class Model: ObservableObject {
    let api: Api
    @Published var review: Review?
    @Published var image: NSImage?
    @Published var status = ""
    var version = -1
    var onNewFindings: ((Int) -> Void)?

    init(api: Api) { self.api = api }

    var flaggedCount: Int { review?.findings.filter(\.flagged).count ?? 0 }

    func poll() async {
        guard let current: Version = try? await api.get("/api/version"),
              current.version != version else { return }
        version = current.version
        guard let next: Review = try? await api.get("/api/findings") else { return }
        review = next
        image = (try? await api.imageData()).flatMap(NSImage.init(data:))
        status = flaggedCount > 0 ? "Redacted copy is on your clipboard" : ""
        if flaggedCount > 0 { onNewFindings?(flaggedCount) }
    }

    func toggle(_ id: Int) {
        Task {
            guard let reply: ToggleReply = try? await api.post("/api/findings/\(id)/toggle"),
                  let index = review?.findings.firstIndex(where: { $0.id == id }) else { return }
            review?.findings[index].flagged = reply.flagged
            status = reply.copied == true ? "Clipboard updated" : "Couldn't update clipboard"
        }
    }

    func setStyle(_ style: String) {
        Task {
            guard let reply: StyleReply = try? await api.post("/api/style", ["style": style]) else { return }
            review?.style = reply.style
            status = reply.copied == true ? "Clipboard updated" : "Couldn't update clipboard"
        }
    }
}

// MARK: - Views

struct ToastView: View {
    let count: Int
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "eye.slash.fill")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(Circle().fill(Color.red.opacity(0.85)))
            VStack(alignment: .leading, spacing: 2) {
                Text(count == 1 ? "1 sensitive item hidden" : "\(count) sensitive items hidden")
                    .font(.system(size: 13, weight: .semibold))
                Text("Redacted copy is on your clipboard · Click to review")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(width: 340)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(.white.opacity(0.12)))
        .contentShape(Rectangle())
    }
}

struct ReviewView: View {
    @ObservedObject var model: Model
    let close: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let review = model.review {
                if review.classifier_offline {
                    Label("Classifier offline: every uncertain match is flagged.", systemImage: "exclamationmark.triangle")
                        .font(.callout)
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.yellow.opacity(0.2), in: RoundedRectangle(cornerRadius: 8))
                }
                screenshot(review)
                Text("Click a box or row to hide or show it.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                List(review.findings) { finding in
                    row(finding)
                }
                .listStyle(.inset)
                .frame(minHeight: 90, maxHeight: 180)
                HStack {
                    Picker("Style", selection: Binding(
                        get: { review.style },
                        set: { model.setStyle($0) }
                    )) {
                        ForEach(review.styles, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 260)
                    Spacer()
                    Text(model.status).font(.caption).foregroundStyle(.secondary)
                    Button("Done", action: close).keyboardShortcut(.defaultAction)
                }
            } else {
                Text("Waiting for a screenshot…").foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(minWidth: 560, minHeight: 420)
    }

    func screenshot(_ review: Review) -> some View {
        GeometryReader { geo in
            let scale = min(geo.size.width / review.image.width, geo.size.height / review.image.height)
            let size = CGSize(width: review.image.width * scale, height: review.image.height * scale)
            ZStack(alignment: .topLeading) {
                if let image = model.image {
                    Image(nsImage: image).resizable().frame(width: size.width, height: size.height)
                }
                ForEach(review.findings) { finding in
                    if let box = finding.bbox {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(finding.flagged ? Color.red.opacity(0.25) : Color.gray.opacity(0.1))
                            .overlay(
                                RoundedRectangle(cornerRadius: 3)
                                    .strokeBorder(finding.flagged ? Color.red : Color.gray,
                                                  style: StrokeStyle(lineWidth: 2, dash: finding.flagged ? [] : [4]))
                            )
                            .frame(width: box.width * scale, height: box.height * scale)
                            .offset(x: box.x * scale, y: box.y * scale)
                            .onTapGesture { model.toggle(finding.id) }
                            .help(finding.flagged ? "Hidden. Click to show" : "Shown. Click to hide")
                    }
                }
            }
            .frame(width: size.width, height: size.height)
            .position(x: geo.size.width / 2, y: geo.size.height / 2)
        }
        .frame(minHeight: 200)
    }

    func row(_ finding: FindingItem) -> some View {
        HStack {
            Image(systemName: finding.flagged ? "eye.slash.fill" : "eye")
                .foregroundStyle(finding.flagged ? Color.red : Color.secondary)
                .frame(width: 20)
            Text(finding.rule.replacingOccurrences(of: "_", with: " ").capitalized)
                .strikethrough(!finding.flagged)
            Spacer()
            Text(finding.preview).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
        }
        .contentShape(Rectangle())
        .onTapGesture { model.toggle(finding.id) }
    }
}

// MARK: - Windows

final class ClickHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    var model: Model!
    var toast: NSPanel?
    var window: NSWindow?
    var hideToast: DispatchWorkItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--url"), index + 1 < args.count,
              let api = Api(url: args[index + 1]) else {
            FileHandle.standardError.write("usage: Squint --url http://127.0.0.1:PORT/?t=TOKEN\n".data(using: .utf8)!)
            exit(2)
        }
        NSApp.setActivationPolicy(.accessory)
        model = Model(api: api)
        model.onNewFindings = { [weak self] count in self?.showToast(count) }
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.model.poll() }
        }
    }

    func showToast(_ count: Int) {
        if window?.isVisible == true { return }  // already reviewing; the window updates in place
        toast?.orderOut(nil)
        let host = ClickHostingView(rootView: ToastView(count: count).onTapGesture { [weak self] in
            self?.openReview()
        })
        host.frame.size = host.fittingSize
        let panel = NSPanel(
            contentRect: host.frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered, defer: false
        )
        panel.contentView = host
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        if let screen = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: screen.maxX - host.frame.width - 16,
                                         y: screen.maxY - host.frame.height - 16))
        }
        panel.alphaValue = 0
        panel.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { $0.duration = 0.2; panel.animator().alphaValue = 1 }
        toast = panel

        hideToast?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.dismissToast() }
        hideToast = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 6, execute: work)
    }

    func dismissToast() {
        guard let panel = toast else { return }
        NSAnimationContext.runAnimationGroup({ $0.duration = 0.25; panel.animator().alphaValue = 0 }) {
            panel.orderOut(nil)
        }
        toast = nil
    }

    func openReview() {
        dismissToast()
        if window == nil {
            let view = ReviewView(model: model) { [weak self] in self?.window?.orderOut(nil) }
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 720, height: 560),
                styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
                backing: .buffered, defer: false
            )
            win.title = "Squint"
            win.isReleasedWhenClosed = false
            win.contentView = NSHostingView(rootView: view)
            win.center()
            window = win
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}

@main
struct SquintMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
}
