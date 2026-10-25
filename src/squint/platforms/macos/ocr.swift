// Squint OCR helper: runs Apple Vision text recognition on one image and prints JSON.
//
// Output: {"width": W, "height": H, "lines": [{"text": "...", "words": [
//            {"start": s, "end": e, "x": x, "y": y, "w": w, "h": h}]}]}
// Boxes are in image pixels with a top-left origin. start/end are Unicode
// scalar offsets into "text" (matching Python str indexing). A "word" is a
// run of non-whitespace characters, so tokens like sk_live_abc stay whole.

import AppKit
import Foundation
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

guard CommandLine.arguments.count == 2 else { fail("usage: squint-ocr <image>") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: url),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
else { fail("cannot read image") }

let width = Double(cgImage.width)
let height = Double(cgImage.height)

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false  // correction "fixes" keys and tokens into words

do {
    try VNImageRequestHandler(cgImage: cgImage).perform([request])
} catch {
    fail("vision failed: \(error)")
}

func pixelBox(_ normalized: CGRect) -> [String: Double] {
    // Vision boxes are normalised with a bottom-left origin.
    return [
        "x": normalized.minX * width,
        "y": (1 - normalized.maxY) * height,
        "w": normalized.width * width,
        "h": normalized.height * height,
    ]
}

var lines: [[String: Any]] = []
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first else { continue }
    let text = candidate.string
    var words: [[String: Any]] = []
    var index = text.startIndex
    while index < text.endIndex {
        guard !text[index].isWhitespace else {
            index = text.index(after: index)
            continue
        }
        var end = index
        while end < text.endIndex && !text[end].isWhitespace {
            end = text.index(after: end)
        }
        if let box = try? candidate.boundingBox(for: index..<end) {
            var word = pixelBox(box.boundingBox)
            word["start"] = Double(text.unicodeScalars.distance(from: text.startIndex, to: index))
            word["end"] = Double(text.unicodeScalars.distance(from: text.startIndex, to: end))
            words.append(word)
        }
        index = end
    }
    lines.append(["text": text, "words": words])
}

let output: [String: Any] = ["width": width, "height": height, "lines": lines]
let data = try! JSONSerialization.data(withJSONObject: output)
FileHandle.standardOutput.write(data)
