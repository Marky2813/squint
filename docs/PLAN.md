# Squint v1 design plan

Screenshot → OCR → regex candidates → local Gemma judgement → user review → redacted export.

## Performance budget

**Target ~2 s** (soft; slightly over is acceptable) from the screenshot file appearing to the review data being ready (full pipeline, all verdicts final). Measured by a benchmark script over `eval/`, not in pytest.

| Stage | Estimate / measured |
|---|---|
| File settle debounce | ~0.1 s |
| Vision OCR (accurate) | 0.2–0.4 s (measured; ~60 s once, on first-ever use per machine) |
| Regex | ~0 |
| Gemma, warm with primed prefix (gemma3:4b) | 1 cand 0.36 s, 2 cand 0.78 s, 4 cand 1.32 s (measured, M1 Pro) |
| Gemma warm-up from cold | ~5.7 s (measured), done at launch |

## Pipeline

### Trigger
- `squint watch`: polls the screenshot folder (`defaults read com.apple.screencapture location`, default `~/Desktop`). A file is processed once its size is unchanged across two polls (~100 ms).
- `squint check <file>`: the same pipeline for a single file.

### OCR (`platforms/macos/`)
- A Swift helper using Vision `VNRecognizeTextRequest` (accurate) prints JSON: lines with text plus per-word boxes (`boundingBox(for: range)`).
- `platforms/base.py`: `OcrEngine.recognize(image_path) -> list[OcrLine]`, where `OcrLine` holds `text` and `words: [(char_start, char_end, bbox)]`.
- Core maps a regex match's char span to the union of overlapping word boxes, plus padding. Pure and tested with fake OCR output.

### Candidates (regex tiers)

| Category | Tier |
|---|---|
| Private keys (`-----BEGIN … PRIVATE KEY-----`) | sensitive |
| Vendor-prefixed tokens (`AKIA`, `ghp_`, `github_pat_`, `sk_live_`, `xox[bp]-`, `AIza`) | sensitive |
| JWTs (3 base64url segments, header decodes to JSON) | sensitive |
| Credit cards (Luhn-valid only) | sensitive |
| Credentials in URLs (`scheme://user:pass@`) | sensitive |
| Generic high-entropy strings ≥20 chars | ambiguous → Gemma |
| `password=` / `secret:` / `token=` assignments | ambiguous → Gemma |
| Email addresses | ambiguous → Gemma |
| Phone numbers | ambiguous → Gemma |
| `Authorization: Bearer …` values | sensitive |
| Known placeholders (`xxxx`, `<your-key>`, `changeme`, …) | benign (dropped) |
| Generic/reserved emails (`noreply@`, `no-reply@`, `support@`, `info@`, `example.com/.org/.net`) | benign (dropped) |
| UUIDs, 40-hex after `commit`/`Merge`, `sha256:` digests | benign (dropped) |
| IP addresses | out of scope for v1 |

### Classification (Gemma via Ollama)
- HTTP to Ollama, **host locked to `127.0.0.1`**. Model **`gemma3:4b`** (`gemma3:1b` scored 43% on a 14-case smoke test). Kept warm (`keep_alive`, warm-up at launch).
- Ollama must run with **`OLLAMA_NUM_PARALLEL` ≥ 4**; without it, parallel calls are serialised.
- **One call per ambiguous candidate, run in parallel, max 4 per screenshot.** Overflow is flagged without asking Gemma.
- Prompt: fixed instructions + ~8 few-shot examples + one candidate (`id`, matched value, regex rule, ±1 line of OCR context ≤200 chars). Without the examples, single-candidate calls flag almost everything.
- Output: JSON schema `{"sensitive": boolean}`, key required. `temperature: 0`, low `num_predict`. No category/confidence/reason: they cost ~2.5 s of generation, and the category comes from the regex rule.
- **Fail-safe:** a missing id, unparseable reply, timeout, or unreachable server means **flagged**.
- Gemma only judges candidates. It never locates text or touches files.

- **Prefix caching:** requests use `raw` mode with a hand-written Gemma chat template so all calls share a byte-identical prefix. Gemma 3's sliding-window attention means llama.cpp only reuses cache from checkpoints, which sit at the end of earlier prompts; `warm_up()` therefore sends the prefix alone to every slot. This cut a new candidate from ~1.4 s to ~0.36 s.
- Smoke test (14 synthetic cases, regex tiers + Gemma): 14/14, with 5 of 14 reaching Gemma.

### Redaction (`core/`, Pillow)
- Approved findings → `RedactionPlan` (padded rects, pure data) → `render(image, plan, style)`.
- **Irreversible styles:** every style first replaces the box with random noise tinted to the box's mean foreground/background colours, then applies `pixelate` (default), `blur`, or `solid`.
- Property test: with a fixed seed, two images with different synthetic secrets in the same spot produce identical pixels inside the box.

### Export
- Write `<name>.redacted.png` with metadata removed. Never overwrite or move the original.
- Copy the redacted image to the clipboard.
- The review UI notes that the original is still on disk.

### Review UI
- A Python JSON API on `127.0.0.1` with a random URL token: `GET /findings`, `POST /findings/{id}/toggle`, `POST /export {style}`, `GET /image`. Review state lives in `core/`.
- **Primary:** a native SwiftUI app (Swift package, `swift run`) showing the image with box overlays, click to toggle, a style picker, and Export. Launched with `--url`.
- **Fallback:** a single HTML page served by the same API.

### Watch-mode behaviour

| Result | Behaviour |
|---|---|
| No findings | Silent for clipboard images; optional "✓ clean" notification for saved files (off with `--quiet`) |
| Findings | Redacted copy goes to the clipboard and a toast appears; click it to review |
| Gemma offline or timed out | Flag all ambiguous candidates and show a "classifier offline" banner |
| OCR failed | "Couldn't scan" notification, no window |

### Zero-click flow (decided 2026-10-25 after first user test)
- **Inputs:** saved screenshots (folder watch) **and every new image on the clipboard** (covers ⌃⇧⌘4). A Swift helper polls `NSPasteboard`; Squint's own writes carry a private `dev.squint.redacted` type so they are never rescanned. Clipboard images live in a 0700 temp dir; clean ones are deleted immediately.
- **Clipboard:** as soon as a scan flags anything, the redacted image (default `pixelate`) replaces the clipboard. Every toggle or style change in review re-exports and re-copies (`ReviewServer(live=True)`).
- **Floating thumbnail:** `squint watch` turns it off at start (it delays the file ~5 s) and restores the original value on exit, including on SIGTERM/SIGHUP. The original is saved to `~/.cache/squint/thumbnail-original.json` first, so a crashed run still restores the true value next time.
- **Alert:** native background app (`LSUIElement`, built with `swiftc`, no Xcode). A non-activating toast at the top right ("N sensitive items hidden · click to review") hides after 6 s. Clicking opens a small review window (screenshot with clickable boxes, list, style picker). The web page remains the fallback if the app can't launch.
- Measured: copy screenshot → redacted copy on clipboard **1.56 s**; startup 2.6 s once helpers are compiled.

### Squint's own leak rules
- Never log OCR text, candidate values, or prompts.
- Temp files go in a `0700` directory and are removed on exit.

## Eval
- `eval/make_fixtures.py` (seeded) writes about 8 content files of synthetic, deliberately invalid secrets: `.env`, `config.yaml`, terminal log, `curl` with bearer token, Slack-style HTML, git log, README with placeholders, dashboard HTML.
- About 25 real screenshots (VS Code, Terminal, browser; light and dark), with **5 held out** from tuning.
- About 60 sensitive items, about 40 hard negatives (SHAs, UUIDs, `sk_test_xxx`, `<YOUR_API_KEY>`, `noreply@`, versions, dates), and about 3 clean screenshots.
- Labels match by text: `{"value", "category", "sensitive"}` per screenshot, compared after normalising whitespace.
- Targets: **recall ≥ 95%** on sensitive items, **precision ≥ 70%**.
- `eval/labels.json` is created once by the fixture script, then read-only.

## Schedule (6 h)

| Hours | Work |
|---|---|
| 0–0.5 | Scaffolding, `platforms/base.py`, warm Gemma and time a cold call |
| 0.5–1.5 | Swift OCR helper, span → box mapping and tests |
| 1.5–2.5 | Eval fixtures; regex tiers; Gemma batch classifier with fail-safe and tests |
| 2.5–3.25 | Redaction styles and property test |
| 3.25–4 | JSON API, HTML page, watch mode → **demoable end to end** |
| 4–5.25 | SwiftUI app, time-boxed. **Hard stop at 5:15**: if not working, demo the web UI |
| 5.25–6 | Benchmark against the 2 s budget, fixes, README, demo rehearsal |

**Stretch:** drag to draw manual redaction boxes in the review UI.

## Future (v2)
- Let Gemma *suggest strings*, accepted only if they exactly match OCR text and located by the existing span → box code. Run it as a second pass after the review window opens.
- IP addresses, names, and addresses.
