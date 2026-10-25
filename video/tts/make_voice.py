"""Generate the voiceover with Kokoro, an open-weight TTS model, running locally.

    video/tts/.venv/bin/python video/tts/make_voice.py [voice]

Writes one WAV per line to video/public/vo/ and their durations to src/v2/vo.json, so
the film's timing follows the real speech.
"""

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "vo"
TIMING = HERE.parent / "src" / "v2" / "vo.json"

# (text, speed). " | " splits a line into phrases joined by real silence (PAUSE seconds):
# the twist, the tagline and the sign-off need a beat that punctuation alone doesn't give.
PAUSE = 0.30
PAUSES = {"montage": 0.22}  # a quicker rhythm for the montage
LINES = {
    "open": ("Every day, you paste your screen into AI.", 0.97),
    "text": ("A text pops up, with your phone number in it.", 1.0),
    "dash": ("Your dashboard, signed in as you.", 1.0),
    "montage": ("Keys. | Passwords. | Cards.", 1.0),
    "twist": ("You checked the bug. | But did you check the corners?", 0.88),
    "refusal": ("Nobody checks every corner. Honestly? We're all a little lazy.", 0.95),
    "mentor": ("So stay lazy. | Meet Squint. | It does the squinting, so you don't have to.", 0.92),
    "threshold": ("Take a screenshot, like always. Gemma, running right on your Mac, spots what's private, and hides it before you paste.", 0.97),
    "reward": ("Your AI still sees the bug. Nobody sees your number.", 0.95),
    "close": ("Nothing leaves your Mac. | That's Squint. Free, at my squint dot tech.", 0.92),
}


def main() -> int:
    voice = sys.argv[1] if len(sys.argv) > 1 else "af_heart"
    kokoro = Kokoro(str(HERE / "kokoro-v1.0.onnx"), str(HERE / "voices-v1.0.bin"))
    OUT.mkdir(parents=True, exist_ok=True)
    timing = {}
    for name, (text, speed) in LINES.items():
        parts = []
        for phrase in text.split(" | "):
            audio, rate = kokoro.create(phrase, voice=voice, speed=speed, lang="en-us")
            parts += [audio, np.zeros(int(PAUSES.get(name, PAUSE) * rate), dtype=audio.dtype)]
        samples = np.concatenate(parts[:-1])
        samples = samples / max(1e-6, float(np.max(np.abs(samples)))) * 0.95  # consistent level
        sf.write(OUT / f"{name}.wav", samples, rate)
        timing[name] = round(len(samples) / rate, 3)
        print(f"{name:<10} {timing[name]:5.2f}s  {text.replace(' | ', ' ')}")
    TIMING.write_text(json.dumps(timing, indent=2) + "\n")
    print(f"total speech {sum(timing.values()):.1f}s, voice {voice}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
