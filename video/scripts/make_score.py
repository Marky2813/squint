"""Build the film's timeline from the voiceover, then compose music and effects to fit it.

    python3 video/scripts/make_score.py

Reads src/v2/vo.json (seconds per voice line, from tts/make_voice.py), writes
src/v2/timeline.json (scene starts and lengths, voice cue frames), public/sfx2/*.wav.
The timeline is the single source of truth: the film imports it, the music follows it.
"""

import json
import math
import random
import struct
import wave
from pathlib import Path

FPS = 30
RATE = 44100
ROOT = Path(__file__).resolve().parent.parent
VO = ROOT / "src" / "v2" / "vo.json"
TIMELINE = ROOT / "src" / "v2" / "timeline.json"
OUT = ROOT / "public" / "sfx2"
rng = random.Random(11)

# (scene, voice line, voice cue in frames from scene start, minimum length, tail after voice)
SCENES = [
    ("hook", "open", 6, 350, 0),
    ("twist", "twist", 26, 190, 36),
    ("refusal", "refusal", 8, 110, 14),
    ("mentor", "mentor", 12, 140, 12),
    ("threshold", "threshold", 14, 230, 30),
    ("reward", "reward", 46, 130, 16),
    ("close", "close", 12, 170, 50),
]


def build_timeline() -> dict:
    vo = json.loads(VO.read_text())
    start, scenes = 0, []
    for name, line, cue, minimum, tail in SCENES:
        speech = math.ceil(vo[line] * FPS)
        length = max(minimum, cue + speech + tail)
        scenes.append({"name": name, "start": start, "length": length,
                       "vo": {"file": f"vo/{line}.wav", "at": start + cue, "length": speech}})  # fmt: skip
        start += length
    return {"fps": FPS, "total": start, "scenes": scenes}


# MARK: synthesis helpers


def write(name: str, samples: list[float], peak: float = 0.89) -> None:
    top = max(1e-9, max(abs(s) for s in samples))
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / name), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(b"".join(struct.pack("<h", int(s / top * peak * 32767)) for s in samples))


def freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(buf: list[float], at: float, samples: list[float], gain: float = 1.0) -> None:
    i0 = int(at * RATE)
    for k, s in enumerate(samples):
        if 0 <= i0 + k < len(buf):
            buf[i0 + k] += s * gain


def lowpass(samples: list[float], cutoff: float) -> list[float]:
    a = 1 - math.exp(-2 * math.pi * cutoff / RATE)
    out, y = [], 0.0
    for s in samples:
        y += a * (s - y)
        out.append(y)
    return out


def tone(f: float, seconds: float, decay: float, harmonics=(1.0, 0.3), attack=0.004) -> list[float]:
    n = int(seconds * RATE)
    return [
        math.exp(-t / decay) * min(1, t / attack)
        * sum(h * math.sin(2 * math.pi * f * (k + 1) * t) for k, h in enumerate(harmonics))
        for t in (i / RATE for i in range(n))
    ]  # fmt: skip


def pad_chord(notes: list[int], seconds: float, gain: float = 0.03) -> list[float]:
    n = int(seconds * RATE)
    out = [0.0] * n
    for note in notes:
        for detune in (-0.07, 0.0, 0.06):
            f, phase = freq(note + detune), rng.random() * 6.28
            for i in range(n):
                t = i / RATE
                out[i] += gain * math.sin(math.pi * t / seconds) ** 2 * math.sin(2 * math.pi * f * t + phase)
    return out


def kick() -> list[float]:
    n = int(0.35 * RATE)
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        phase += 2 * math.pi * (45 + 90 * math.exp(-t * 30)) / RATE
        out.append(math.sin(phase) * math.exp(-t * 9))
    return out


def hat() -> list[float]:
    n = int(0.05 * RATE)
    raw = [rng.uniform(-1, 1) * math.exp(-i / (RATE * 0.008)) for i in range(n)]
    return [a - b for a, b in zip(raw, lowpass(raw, 7000))]  # crude high-pass


def noise_sweep(seconds: float, lo: float, hi: float, shape) -> list[float]:
    n = int(seconds * RATE)
    out, y = [], 0.0
    for i in range(n):
        t = i / n
        a = 1 - math.exp(-2 * math.pi * (lo + (hi - lo) * t) / RATE)
        y += a * (rng.uniform(-1, 1) - y)
        out.append(y * shape(t))
    return out


# MARK: the score


def score(timeline: dict) -> list[float]:
    scenes = {s["name"]: s for s in timeline["scenes"]}
    sec = lambda frames: frames / FPS  # noqa: E731
    total = sec(timeline["total"]) + 2.5
    buf = [0.0] * int(total * RATE)

    # Hook: a light, quickening pulse (everyday, busy, a little careless).
    hook_end = sec(scenes["twist"]["start"])
    bpm, t, beat_no = 112, 0.0, 0
    prog = [(57, [69, 72, 76]), (53, [69, 72, 77]), (48, [67, 72, 76]), (55, [67, 71, 74])]
    while t < hook_end - 0.05:
        beat = 60 / bpm
        bass, chord = prog[(beat_no // 4) % 4]
        lift = min(1.0, 0.45 + t / hook_end)
        add(buf, t, kick(), 0.55 * lift)
        add(buf, t + beat / 2, hat(), 0.18 * lift)
        add(buf, t, tone(freq(bass - 12), beat * 0.95, 0.35, (1.0, 0.15)), 0.22 * lift)
        add(buf, t + beat / 2, tone(freq(chord[beat_no % 3]), 0.5, 0.18, (1.0, 0.35, 0.1)), 0.12 * lift)
        t += beat
        beat_no += 1

    # Twist: hard stop, a low impact, then an uneasy drone under the question.
    twist = sec(scenes["twist"]["start"])
    add(buf, twist, [s * math.exp(-i / (RATE * 0.9)) for i, s in enumerate(tone(41.2, 2.5, 1.2, (1.0, 0.5, 0.25)))], 0.9)
    add(buf, twist, noise_sweep(1.2, 2000, 200, lambda x: (1 - x) ** 3), 0.35)
    drone_len = sec(scenes["mentor"]["start"]) - twist
    for f, g in ((55.0, 0.10), (82.4, 0.06), (116.5, 0.035)):  # A1, E2, a sour B♭2
        n = int(drone_len * RATE)
        add(buf, twist, [g * math.sin(math.pi * min(1, i / n * 1.1)) * math.sin(2 * math.pi * f * i / RATE)
                         * (1 + 0.3 * math.sin(2 * math.pi * 0.5 * i / RATE)) for i in range(n)])  # fmt: skip

    # Mentor onwards: warm and resolved; a riser into the reveal, then pads and plucks.
    mentor = sec(scenes["mentor"]["start"])
    add(buf, mentor - 1.2, noise_sweep(1.2, 300, 5000, lambda x: x**2), 0.25)
    warm = [(48, [60, 64, 67, 71]), (45, [57, 60, 64, 67]), (41, [57, 60, 64, 65]), (43, [55, 59, 62, 69])]
    end = sec(timeline["total"])
    beat, t, k = 60 / 92, mentor, 0
    while t < end:
        bass, notes = warm[k % 4]
        span = beat * 8
        add(buf, t, pad_chord(notes, span * 1.3))
        add(buf, t, tone(freq(bass - 12), span, 2.5, (1.0, 0.2), attack=0.3), 0.16)
        if t >= sec(scenes["threshold"]["start"]) - 0.1:  # motion once Squint is at work
            for j, idx in enumerate([0, 2, 1, 3, 2, 1, 3, 2]):
                add(buf, t + j * beat, tone(freq(notes[idx] + 12), 0.9, 0.22, (1.0, 0.3)), 0.07)
        t += span
        k += 1
    # Final chord rings out under the end card.
    add(buf, end - 2.2, pad_chord([60, 64, 67, 71, 74], 4.5, 0.04))

    fade = int(1.5 * RATE)
    for i in range(fade):
        buf[-fade + i] *= 1 - i / fade
    return lowpass(buf, 9000)


def effects() -> None:
    write("paste.wav", lowpass([s * math.exp(-i / (RATE * 0.03)) for i, s in enumerate(tone(140, 0.25, 0.05, (1.0, 0.4)))], 3000))
    write("tick.wav", hat())
    write("ring.wav", tone(freq(88), 0.7, 0.18, (1.0, 0.25, 0.1)))  # bright "found one"
    write("shutter.wav", hat() + [0.0] * int(0.04 * RATE) + hat())
    write("key.wav", lowpass([rng.uniform(-1, 1) * math.exp(-i / (RATE * 0.006)) for i in range(int(0.05 * RATE))], 6000))
    write("whoosh.wav", noise_sweep(0.6, 300, 4500, lambda x: math.sin(math.pi * x) ** 2))
    chime = tone(freq(76), 1.6, 0.5, (1.0, 0.35, 0.12))
    add(chime, 0.09, tone(freq(83), 1.5, 0.5, (1.0, 0.35, 0.12)))
    write("chime.wav", chime)
    write("strike.wav", noise_sweep(0.18, 6000, 1000, lambda x: (1 - x) ** 2))


if __name__ == "__main__":
    timeline = build_timeline()
    TIMELINE.write_text(json.dumps(timeline, indent=2) + "\n")
    for s in timeline["scenes"]:
        print(f"{s['name']:<10} {s['start'] / FPS:5.1f}s  +{s['length'] / FPS:4.1f}s")
    print(f"total {timeline['total'] / FPS:.1f}s")
    effects()
    write("music.wav", score(timeline), peak=0.7)
    print("wrote music and effects to", OUT)
