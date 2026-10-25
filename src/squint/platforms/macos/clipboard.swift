// Squint clipboard helper: reports new clipboard images and writes redacted ones back.
//
// Usage: squint-clip <dir>
// stdout: "ready" once watching (images copied before this are not reported)
//         "image <path>" for each new image placed on the clipboard (saved as PNG in <dir>)
//         "copied" / "error" in reply to a copy command
// stdin:  "copy <path>" puts that PNG on the clipboard, tagged so it is never re-reported.
// The helper exits when stdin closes, so it never outlives the Python process.

import AppKit
import Foundation

let marker = NSPasteboard.PasteboardType("dev.squint.redacted")
let pasteboard = NSPasteboard.general
let directory = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ".")
var lastChange = pasteboard.changeCount

setvbuf(stdout, nil, _IOLBF, 0)

func pngData() -> Data? {
    if let png = pasteboard.data(forType: .png) { return png }
    guard let tiff = pasteboard.data(forType: .tiff),
          let bitmap = NSBitmapImageRep(data: tiff) else { return nil }
    return bitmap.representation(using: .png, properties: [:])
}

func check() {
    let change = pasteboard.changeCount
    guard change != lastChange else { return }
    lastChange = change
    let types = pasteboard.types ?? []
    guard !types.contains(marker), let data = pngData() else { return }
    let url = directory.appendingPathComponent("clipboard-\(change).png")
    do {
        try data.write(to: url, options: .atomic)
        print("image \(url.path)")
    } catch {
        FileHandle.standardError.write("write failed: \(error)\n".data(using: .utf8)!)
    }
}

func copy(_ path: String) -> Bool {
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else { return false }
    pasteboard.clearContents()
    pasteboard.declareTypes([.png, marker], owner: nil)
    let ok = pasteboard.setData(data, forType: .png) && pasteboard.setData(Data(), forType: marker)
    lastChange = pasteboard.changeCount
    return ok
}

Thread {
    while let line = readLine() {
        if line.hasPrefix("copy ") {
            let path = String(line.dropFirst(5))
            let ok = DispatchQueue.main.sync { copy(path) }
            print(ok ? "copied" : "error")
        }
    }
    exit(0)
}.start()

Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { _ in check() }
print("ready")
RunLoop.main.run()
