---
title: "Squint: a local Gemma hides the API keys in my screenshots before I can paste them"
published: false
tags: devchallenge, hf26challenge, gemma, opensource
cover_image: https://mysquint.tech/post/cover.png
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

I do almost everything with AI now. A bug, an email, a form, a weird error in a dashboard: I take a screenshot and paste it into a chat. It's the laziest, fastest way to explain anything.

It's also how I keep leaking things. An email address in the corner of a page. A phone number in a form. An API key sitting in a terminal I didn't bother to crop. By the time I notice, the screenshot is already on someone else's server.

So I built **Squint**: a small macOS menu bar app that checks every screenshot *before* it goes anywhere, using Gemma running on my own Mac.

## What I Built

Take a screenshot the way you always do. If it contains a password, key, token, email, phone number or card number, a banner slides in:

> **Hid 3 things in your screenshot**
> The redacted copy is on your clipboard

That's the whole interaction. The clipboard already holds the safe version, so **⌘V just works**. No dialog, no export button, no new habit.

![Three steps: press ⌃⇧⌘4, Squint's banner says "Hid 5 things in your screenshot", then paste the redacted copy into a chat](https://mysquint.tech/post/flow.png)

Here's a real run on a fake `.env` file. Rules caught three secrets, Gemma judged two more, and everything harmless stayed readable:

![Before and after: the same .env screenshot. Settings, a support@ address and a placeholder key stay visible; the database login, AWS key, Stripe key, session secret and personal email are pixelated](https://mysquint.tech/post/before-after.png)

If you want to check what Squint did, click the banner. You see the screenshot exactly as it will be pasted. Click anything to show or hide it, or drag a box over something it missed.

![The review window: a dashed outline marks an email that was clicked to reveal, a solid box covers a URL drawn by hand, and the status line reads "Click an item to hide or show it · Drag to cover anything else"](https://mysquint.tech/post/review.png)

Everything happens on your Mac: reading the text, deciding what's private, and redacting it. The deciding is done by **Gemma 3 (4B)**, running locally through Ollama.

### Why this fits "Slow and Steady"

The laziest privacy tool is the one you never think about. You don't open Squint, you don't drag files into it, and you don't change how you take screenshots. It squints at every screenshot so you don't have to.

It's lazy on the inside too. Gemma is the sloth of the pipeline. Fast pattern rules catch the obvious cases (a Stripe live key is always a Stripe live key), and Gemma only wakes up for the genuinely ambiguous ones, like "is `jane@company.com` private here, or is it a `support@` address?"

## Demo

[[TODO: upload the demo to YouTube (unlisted is fine) and replace this line with: {% embed https://www.youtube.com/watch?v=YOUR_VIDEO_ID %} — a direct .mp4 link may not embed on DEV.]]

🌐 **[mysquint.tech](https://mysquint.tech)**: download for macOS (Apple Silicon and Intel, macOS 14+)

Try it:

1. Copy a screenshot of a `.env` file with ⌃⇧⌘4.
2. About 1.5 seconds later, the banner appears.
3. Paste into ChatGPT. The keys are pixelated; the variable names are still readable.

## Code

{% github Marky2813/squint %}

## How I Built It

![Pipeline inside "Your Mac": Screenshot, Vision OCR, 14 rules, Gemma 3 4B, Redact, Clipboard. Measured timing: OCR 0.41 s, rules plus Gemma 0.75 s, redact 0.06 s, 1.22 s in total](https://mysquint.tech/post/pipeline.png)

### Catching the screenshot

Squint watches two places: the screenshot folder (⇧⌘4) and the clipboard (⌃⇧⌘4).

macOS's floating thumbnail delays saving the file by a few seconds, so Squint turns it off while it runs and restores your setting when it quits. It does that even if the app is force-killed: the engine notices its parent process is gone and cleans up.

### Reading it

A small Swift helper runs Apple's Vision OCR and returns every line with per-word boxes. It runs on device and takes about 0.3–0.4 s.

![Apple Vision's real OCR output drawn onto the .env screenshot: a blue box around every word. A whole line like STRIPE_SECRET_KEY=sk_live_… is a single "word"](https://mysquint.tech/post/ocr.png)

### Finding candidates

Regex rules sort every match into three tiers:

- **Sensitive:** AWS, Stripe, GitHub, Slack and Google keys, JWTs, private keys, credentials in URLs, bearer tokens, and card numbers that pass the Luhn check. These are hidden immediately.
- **Ambiguous:** emails, phone numbers, `password = …` assignments, high-entropy strings. These go to Gemma.
- **Benign:** placeholders like `<YOUR_API_KEY>`, UUIDs, commit SHAs, dates, `noreply@`. These are dropped.

![Three columns of examples. Sensitive, hidden immediately: AWS, Stripe, GitHub, Slack, Google keys, JWTs, private keys, URL passwords, bearer tokens, Luhn-valid cards. Ambiguous, Gemma decides: emails, phones, password assignments, random strings. Benign, dropped: placeholders, UUIDs, commit hashes, dates, noreply and support addresses](https://mysquint.tech/post/tiers.png)

### Regex decides where. Gemma decides whether.

Each ambiguous candidate goes to `gemma3:4b` with only the matched text and about one line of context, never the image. The output is constrained by a JSON schema to `{"sensitive": true|false}`.

![Where: the OCR line SESSION_SECRET=q8Zr2… with a blue pixel box around the value. Whether: the JSON candidate Gemma receives, and its answer {"sensitive": true}](https://mysquint.tech/post/where-whether.png)

Two design rules made this safe:

- **Gemma never locates text.** OCR and regex decide *where*; Gemma only decides *whether*. A small model can't put a box in the wrong place if it never draws boxes.
- **Failure means hidden.** If Gemma is slow, offline, or returns garbage, the item is treated as sensitive. The worst case is over-redaction, never a leak.

[[TODO, optional but recommended: one honest sentence on why Gemma 3 and not Gemma 4. Most entries this month use Gemma 4, so judges will notice. Only write it if it's true, e.g. "I tested gemma4:e4b too, and …". If you didn't test it, say that it's next.]]

### Making Gemma fast

My first version took 3 seconds per screenshot. Here's what fixed it:

- **One call per candidate, run in parallel** (4 slots), instead of one big batch.
- **Few-shot examples in the prompt**, which fixed accuracy. Gemma 3 **1B** flagged nearly everything: it scored 43% on a 14-case smoke test. **4B** was the sweet spot.
- **Prompt-prefix caching.** Gemma 3 uses sliding-window attention, so llama.cpp could only reuse its prompt cache from checkpoints, and every call was re-reading the instructions. I switched Ollama to `raw` mode with Gemma's chat template written by hand, and warm every slot with the shared prefix at startup. Now only the candidate itself is new work.

![Four parallel slots, each a long cached bar ("Instructions + 8 examples") followed by a short fresh piece for the candidate. 3 s became 1.5 s per screenshot; 0.36 s per candidate](https://mysquint.tech/post/fast.png)

Result: **about 0.36 s per candidate**, and about **1.5 s from screenshot to safe clipboard**. That kind of tuning is only possible because the weights and the runtime are open: I could change the template and the cache behaviour, not just the prompt.

### Redacting so it can't be undone

Pixelation and blur can sometimes be reversed. Squint first replaces every hidden region with random noise tinted from the surrounding pixels, *then* pixelates it, so nothing of the original survives. A property test checks that two different secrets produce identical redacted pixels.

![Real crops: a Stripe key, the same box replaced by tinted noise, then pixelated. Below, two different keys produce redacted images with 0 pixels different](https://mysquint.tech/post/irreversible.png)

### Hiding only what matters

OCR gives one box per word, and `STRIPE_KEY=sk_live_…` is one "word". Squint works out where the value sits inside that word, so the variable name stays readable and only the value is hidden. You can still tell *what* was there, just not *what it was*.

![Top: Vision returns one dashed box around the whole STRIPE_SECRET_KEY=sk_live_… line. Bottom: Squint's real output covers only the value](https://mysquint.tech/post/value-only.png)

### Measuring it

I built an eval set of 24 generated screenshots: `.env` files, YAML, terminals, chat, git logs, dashboards and READMEs, in three fonts, light and dark themes, all with fake secrets. Because I render them myself, I know the exact pixel box of every secret. So the eval checks whether each secret is **fully covered**, not just detected. Five screenshots are held out and never tuned against.

![All 24 eval screenshots in a grid, five outlined in blue as held out, with headline numbers: 100% hidden and 100% fully covered on the tuning set, 92% hidden on held-out, 100% of variable names left readable](https://mysquint.tech/post/eval.png)

| | Tuning set (19) | Held-out (5) |
|---|---|---|
| Secrets hidden | **100%** (39/39) | 92% (11/12) |
| Fully covered, no visible edges | **100%** | 92% |
| Variable names left readable | 100% | 100% |
| Hidden items that were really secrets | 98% | 79% |

The eval earned its keep. It caught two bugs where part of a secret stayed visible:

- OCR misread one character in the middle of a key, the regex stopped there, and the tail stayed visible. Boxes now always run to the end of the token.
- OCR read the `.` in a JWT as a space, so only half of it was hidden. Squint now joins the pieces.

Recall on the tuning set went from 74% to 100%. The held-out miss is a JWT in a proportional font that was 95% covered. That's next on the list.

### What Gemma adds

With Gemma switched off, Squint has to hide every ambiguous match. Across all 24 screenshots:

![Bar chart of false alarms: regex only 10, regex plus Gemma 4. Secrets hidden stay at 50 of 51 either way; Gemma adds about 1 s](https://mysquint.tech/post/gemma-adds.png)

| | Regex only | Regex + Gemma |
|---|---|---|
| False alarms | 10 | **4** |
| Secrets hidden | 50 / 51 | 50 / 51 |
| Extra time | — | about 1 s |

Same recall, less than half the false alarms. Real screenshots are messier than my synthetic ones, and that's exactly where context matters most: `support@` versus a colleague's personal address.

### Shipping it

I didn't want "clone the repo and run a script". Squint is a signed and notarized universal `.app`:

- A SwiftUI menu bar app that runs a bundled Python engine.
- A first-run window that checks for Ollama and downloads Gemma with a progress bar.
- Open at login, and a review window designed to feel like Quick Look.

![The real first-run window: Ollama ready, Gemma 3 downloading at 64%, "Open Squint at login" checked. Beside it, spctl reports "accepted, source=Notarized Developer ID" and lipo lists x86_64 and arm64](https://mysquint.tech/post/shipping.png)

I built it with Claude Code: 199 tests and 55 small commits.

![Build stats: 55 commits, 199 tests passing, 1,560 lines of Python, 1,275 lines of Swift. Commits by type, led by 28 feat; commits per day, with 41 on October 25](https://mysquint.tech/post/built-with-claude.png)

## What it can't do yet

- **macOS only.** The core is platform-independent; only OCR and clipboard access are Mac-specific. Windows and Linux are next.
- **My eval set is synthetic.** I generated those screenshots, so they reflect what I thought to test. Real screenshots are messier.
- **It only knows text.** Faces, photos of documents, and anything OCR can't read go straight through.
- **Setup isn't tiny.** It needs Ollama and a roughly 3 GB model download on first run.
- **One known miss:** that JWT in a proportional font.

## Why Does Open Innovation Matter?

![Everything inside "Your Mac": Squint.app, the engine, Apple Vision OCR, Gemma 3 4B on Ollama at 127.0.0.1:11434, the review API on 127.0.0.1, the clipboard. In once at setup: Ollama and the Gemma weights. Out: never, except the redacted image when you paste it](https://mysquint.tech/post/local-only.png)

**Because the screenshot is the secret.** A cloud model would be a better OCR engine and a smarter classifier, and it would be useless here. You can't upload a screenshot to someone else's server to ask whether it's safe to upload screenshots to someone else's server. The only honest design is a model that runs where the screenshot already is, and open weights make that possible.

**Because nothing leaves your Mac.** After the one-time model download, Squint makes no network calls except to Ollama on `127.0.0.1`. The review API is bound to localhost and needs a per-run token. There are no accounts, analytics or update checks; the only outside link is the Ollama download page, which the setup window opens in your browser.

**Because it works offline.** On a plane, on a locked-down work laptop, anywhere.

**Because you shouldn't need an API key to protect your API keys.** No account, no subscription, no usage bill. Set it up once and it's free forever.

**Because I could open it up and tune it.** The biggest speed win came from rewriting Gemma's chat template and changing how the prompt cache is reused. With a hosted API, the prompt is the only thing you control.

**Because you can check it.** The weights are open and the code is MIT. The one closed piece is the OCR: it's Apple's Vision framework, which runs on device and sends nothing anywhere. You don't have to trust a privacy policy, because you can read exactly what happens to your screenshot.

## My Agent Session

[[TODO: if you used Entire or DevRelay, embed or link the session here (DevRelay: embed it with the agent_session tag, as the challenge page says). Then add 2–3 lines in your own words on how you worked with Claude Code: what you decided yourself, what you delegated, and one moment you had to correct it. If you have no session recording, delete this section.]]

## The Lazy Payoff

[[TODO: real numbers from your own use this week, only if true. For example: how many screenshots Squint checked, how many it redacted something in, and one real catch ("it hid a key I hadn't noticed in …"). The template says to remove this section if nobody used it, so delete it if you don't have real numbers.]]

## Prize Categories

- **Best Use of Gemma:** Gemma 3 4B is the decision-maker. It runs locally via Ollama with schema-constrained output and prompt-prefix caching tuned for Gemma 3's sliding-window attention, and its contribution is measured against a regex-only baseline.
- **Best Use of a .tech Domain:** [mysquint.tech](https://mysquint.tech) is the landing page and download, and it hosts every image in this post.

---

*If you paste screenshots into AI all day, try Squint and tell me what it missed.*
