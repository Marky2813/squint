# Squint

Squint checks every screenshot you take on your Mac for passwords, API keys, tokens and
personal details, and puts a redacted copy on your clipboard. Nothing leaves your Mac:
text is read with Apple's Vision framework, and Gemma 3 runs locally through Ollama.

## Install

1. Open `Squint.dmg` and drag Squint into Applications.
2. Open Squint. The app is not notarized yet, so the first time macOS blocks it: open
   **System Settings → Privacy & Security** and click **Open Anyway**.
3. The welcome window installs what Squint needs:
   - **Ollama** (click Download if you don't have it), and
   - **Gemma 3** (3.3 GB, downloaded once with a progress bar).
4. Click **Start Squint**. Look for the narrowed eye in the menu bar.

When macOS asks whether Squint may access your Desktop, allow it: that's where
screenshots are saved.

## Use

Take a screenshot as usual (⇧⌘4 to save a file, ⌃⇧⌘4 to copy it). If it contains
something private, a banner says what Squint hid, and **the clipboard already holds
the redacted image**, so ⌘V is safe. Click the banner to review:

- **Click** a hidden item to show it again; click it again to hide it.
- **Drag** across anything Squint missed to cover it with an opaque box. Click the box to
  remove it.
- **Right-click** to switch between pixelate, blur and solid.
- **Esc** or **Space** closes the window.

Every change updates the clipboard immediately. The original screenshot file is never
modified; the redacted one is saved next to it as `<name>.redacted.png`.

While Squint runs, macOS's floating screenshot thumbnail is turned off, so files are
saved straight away. Your setting comes back when you quit Squint.

## Build from source

Requires macOS 14+, Xcode command line tools, and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest                        # tests
uv run python scripts/build_app.py   # → dist/Squint.app and dist/Squint.dmg (universal)
uv run python eval/run_eval.py       # accuracy on the synthetic eval set
```

A release build anyone can open needs a Developer ID Application certificate and a
notarytool profile (see the top of `scripts/build_app.py`):

```sh
uv run python scripts/build_app.py --sign "Developer ID Application: …" --notarize squint-notary
```

For development you can also run the engine from a terminal (it opens the same review
window):

```sh
uv run squint watch     # needs `ollama serve` running with gemma3:4b pulled
uv run squint check path/to/screenshot.png
```

Logs: `~/Library/Logs/Squint/squint.log` (menu bar → Show Log).
