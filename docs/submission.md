---
title: "Squint: a local Gemma that checks my screenshots before AI sees them"
published: false
tags: hacktoberfest, devchallenge, gemma, opensource
---

*This is a submission for the Hacktoberfest 2026 "Slow and Steady" challenge.*
<!-- Replace this line with the exact opening line from the submission template. -->

## What I Built

I do almost everything with AI now. Debugging, emails, forms, a weird error in a dashboard: I take a screenshot and paste it into a chat. It's the laziest, fastest way to explain anything.

It's also how I keep leaking things. An email address in the corner of a page. A phone number in a form. An API key sitting in a terminal I didn't bother to crop. By the time I notice, the screenshot is on someone else's server.

**Squint** is a tiny macOS menu bar app that checks every screenshot *before* it goes anywhere. Take a screenshot like you always do. If it contains a password, key, token, email, phone or card number, a banner slides in:

> **Hid 3 things in your screenshot**
> The redacted copy is on your clipboard

That's it. Your clipboard already holds the safe version, so **⌘V just works**. No dialog, no export button, no new habit. If you want to check what Squint did, click the banner: you see the screenshot exactly as it will be pasted. Click anything to show or hide it, or drag a box over something it missed.

Everything (reading the text, deciding what's private, and redacting) happens on your Mac, with **Gemma 3** running locally through Ollama.

### Why this fits "Slow and Steady"

The laziest privacy tool is the one you never have to think about. You don't open Squint, you don't drag files into it, you don't change how you take screenshots. It just squints at every screenshot so you don't have to.

It's lazy on the inside too. Gemma is the sloth of the pipeline: fast pattern rules catch the obvious things (a Stripe live key is always a Stripe live key), and Gemma only wakes up for the genuinely ambiguous cases, like "is `jane@company.com` private here, or is it `support@`?"

## Demo

<!-- Embed the video: {% embed https://mysquint.tech/demo.mp4 %} or upload it to the post -->

🌐 **[mysquint.tech](https://mysquint.tech)**: download for macOS (Apple Silicon and Intel, macOS 14+)

1. Copy a screenshot of a `.env` file with ⌃⇧⌘4.
2. About 1.5 seconds later, the banner appears.
3. Paste into ChatGPT: the keys are pixelated and the variable names are still readable.

## Code

{% github Marky2813/squint %}

## How I Built It

```
Screenshot ─▶ Apple Vision OCR ─▶ regex candidates ─▶ Gemma 3 (4B) judges ─▶ redact ─▶ clipboard
              (on device)          14 rules, 3 tiers    ambiguous ones only     irreversible
```

**Catching the screenshot.** Squint watches two places: the screenshot folder (⇧⌘4) and the clipboard (⌃⇧⌘4). macOS's floating thumbnail delays saving by a few seconds, so Squint turns it off while it runs and puts your setting back when it quits. It does that even if the app is force-killed, because the engine notices its parent is gone and cleans up.

**Reading it.** A small Swift helper runs Apple's Vision OCR and returns every line with per-word boxes. On-device and about 0.3 s.

**Finding candidates.** Regex rules sort matches into three tiers:
- **sensitive:** AWS, Stripe, GitHub, Slack and Google keys, JWTs, private keys, credentials in URLs, bearer tokens, cards that pass the Luhn check. These are hidden immediately.
- **ambiguous:** emails, phone numbers, `password = …` assignments, high-entropy strings. These go to Gemma.
- **benign:** placeholders like `<YOUR_API_KEY>`, UUIDs, commit SHAs, dates, `noreply@`. These are dropped.

**Gemma decides.** Each ambiguous candidate goes to `gemma3:4b` with only the matched text and about one line of context, never the image. The output is constrained by a JSON schema to `{"sensitive": true|false}`. Two design rules made this safe:
- **Gemma never locates text.** OCR and regex decide *where*; Gemma only decides *whether*. A small model can't hallucinate a box in the wrong place.
- **Failure means hidden.** If Gemma is slow, offline or returns garbage, the item is treated as sensitive. The worst case is over-redaction, never a leak.

**Making Gemma fast.** My first version took 3 seconds per screenshot. The fixes:
- One call per candidate, run in parallel (4 slots), instead of one big batch.
- Few-shot examples in the prompt, which fixed accuracy (Gemma 3 **1B** flagged nearly everything: 43%. **4B** was the sweet spot).
- **Prompt-prefix caching.** Gemma 3 uses sliding-window attention, so llama.cpp could only reuse its prompt cache from checkpoints, and every call was re-reading the instructions. I switched Ollama to `raw` mode with Gemma's chat template written by hand, and warm every slot with the shared prefix at startup. Only the candidate itself is new work.

Result: **about 0.36 s per candidate**, and about 1.5 s from screenshot to safe clipboard. That kind of tuning is only possible because the weights and the runtime are open: I could change the template and the cache behaviour, not just the prompt.

**Redacting so it can't be undone.** Pixelation and blur can sometimes be reversed. Squint first replaces every hidden region with random noise tinted from the surrounding pixels, *then* pixelates it, so nothing of the original survives. A property test checks that two different secrets produce identical redacted pixels.

**Hiding only what matters.** OCR gives one box per word, and `STRIPE_KEY=sk_live_…` is one "word". Squint works out the value's position inside the word, so the variable name stays readable and only the value is hidden. You can still tell what was there, just not what it was.

**Measuring it.** I built an eval set of 24 generated screenshots: `.env` files, YAML, terminals, chat, git logs, dashboards and READMEs, in three fonts with light and dark themes, all with fake secrets. Because I render them, I know the exact pixel box of every secret, so the eval checks whether each one is *fully covered*, not just detected. Five screenshots are held out and never tuned against.

| | Tuning set (19) | Held-out (5) |
|---|---|---|
| Secrets hidden | **100%** (39/39) | 92% (11/12) |
| Fully covered, no visible edges | **100%** | 92% |
| Variable names left readable | 100% | 100% |
| Hidden items that were really secrets | 98% | 79% |

The eval earned its keep. It caught two bugs where part of a secret stayed visible:
- OCR misread one character in the middle of a key, the regex stopped there, and the tail stayed visible. Boxes now always run to the end of the token.
- OCR read the `.` in a JWT as a space, so only half of it was hidden. Squint now joins the pieces.

Recall on the tuning set went from 74% to 100%. The held-out miss is a JWT in a proportional font that was 95% covered; that's next on the list.

**What Gemma adds.** With Gemma switched off, Squint has to hide every ambiguous match. Across all 24 screenshots, **Gemma cut false alarms from 10 to 4 with no loss in recall**, at about a second of extra time. Real screenshots are messier than my synthetic ones, and that's exactly where context matters most: `support@` versus a colleague's personal address.

**Shipping it.** I didn't want "clone the repo and run a script". Squint is a signed, universal `.app`:
- A SwiftUI menu bar app that runs a bundled Python engine.
- A first-run window that checks Ollama and downloads Gemma with a progress bar.
- Open at login, and a review window designed to feel like Quick Look.

Built with Claude Code over one long session: about 200 tests, 30 small commits.

## Why open innovation matters here

**Because the screenshot is the secret.** A cloud model would be a better OCR engine and a smarter classifier, and it would be useless here. You can't upload a screenshot to someone else's server to ask whether it's safe to upload screenshots to someone else's server. The only honest design is a model that runs where the screenshot already is. Open weights make that possible.

- **Nothing leaves your Mac.** Squint makes no network calls except to Ollama on `127.0.0.1`. The review API is bound to localhost and needs a per-run token.
- **It works offline.** On a plane, on a locked-down work laptop, anywhere.
- **No API key to protect your API keys.** No account, no subscription, no usage bill. Set it up once and it's free forever.
- **You can check it.** Open weights, open code (MIT). You don't have to trust a privacy policy, because you can read exactly what happens to your screenshot.

## What's next

- Use Apple's on-device Foundation Models on newer Macs, so setup needs no 3 GB download.
- An eval set built from real screenshots, and a fix for that last JWT edge.
- Windows and Linux: the core is platform-independent, and only OCR and clipboard access are macOS-specific.

## Prize Categories

- **Best Use of Gemma:** Gemma 3 4B is the decision-maker. It runs locally via Ollama with schema-constrained output and prompt-prefix caching tuned for Gemma 3's sliding-window attention, and its contribution is measured against a regex-only baseline.
- **Best Use of a .tech Domain:** [mysquint.tech](https://mysquint.tech) is the landing page and download.
