"""Synthesize the video's music bed and sound effects (no samples, no licences).

    python3 video/scripts/make_audio.py
"""

import math
import random
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "public" / "sfx"
rng = random.Random(7)


def write(name: str, samples: list[float], peak: float = 0.89) -> None:
    top = max(1e-9, max(abs(s) for s in samples))
    data = b"".join(struct.pack("<h", int(s / top * peak * 32767)) for s in samples)
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / name), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(data)


def freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def lowpass(samples: list[float], cutoff: float) -> list[float]:
    a = 1 - math.exp(-2 * math.pi * cutoff / RATE)
    out, y = [], 0.0
    for s in samples:
        y += a * (s - y)
        out.append(y)
    return out


# MARK: music: a warm pad, a soft bass and a gentle plucked arpeggio

CHORDS = [  # (bass, pad notes) in MIDI; calm major, a darker turn, then home
    (48, [60, 64, 67, 71]),  # Cmaj7
    (45, [57, 60, 64, 67]),  # Am7
    (41, [57, 60, 64, 65]),  # Fmaj7
    (43, [55, 59, 62, 69]),  # G6/9
]


def music(seconds: float, bpm: float = 84) -> list[float]:
    beat = 60 / bpm
    chord_len = beat * 8
    n = int(seconds * RATE)
    out = [0.0] * n
    count = int(seconds / chord_len) + 2
    for c in range(count):
        bass, notes = CHORDS[c % len(CHORDS)]
        start = c * chord_len
        # Pad: detuned sines with a slow swell that overlaps the next chord.
        span = chord_len * 1.35
        s0, s1 = int(start * RATE), min(n, int((start + span) * RATE))
        for note in notes:
            for detune in (-0.06, 0.0, 0.07):
                f = freq(note + detune)
                phase = rng.random() * 6.28
                for i in range(s0, s1):
                    t = (i - s0) / RATE
                    env = math.sin(math.pi * t / span) ** 2
                    out[i] += 0.035 * env * math.sin(2 * math.pi * f * t + phase)
        # Bass: a soft sine on the root.
        fb = freq(bass)
        for i in range(s0, min(n, int((start + chord_len) * RATE))):
            t = (i - s0) / RATE
            env = min(1, t / 0.4) * math.exp(-t / (chord_len * 0.9))
            out[i] += 0.16 * env * math.sin(2 * math.pi * fb * t)
        # Arpeggio: plucked chord tones on eighth notes, an octave up.
        pattern = [0, 2, 1, 3, 2, 1, 3, 2] * 2
        for k, idx in enumerate(pattern):
            at = start + k * beat / 2
            f = freq(notes[idx] + 12)
            a0 = int(at * RATE)
            for i in range(a0, min(n, a0 + int(1.2 * RATE))):
                t = (i - a0) / RATE
                env = math.exp(-t * 5.5) * min(1, t / 0.004)
                out[i] += 0.05 * env * (math.sin(2 * math.pi * f * t) + 0.3 * math.sin(4 * math.pi * f * t))
    return lowpass(out, 5000)


# MARK: sound effects


def noise(seconds: float) -> list[float]:
    return [rng.uniform(-1, 1) for _ in range(int(seconds * RATE))]


def key() -> list[float]:
    n = noise(0.05)
    click = [s * math.exp(-i / (RATE * 0.006)) for i, s in enumerate(n)]
    tick = [0.4 * math.sin(2 * math.pi * 1800 * i / RATE) * math.exp(-i / (RATE * 0.01)) for i in range(len(n))]
    return lowpass([a + b for a, b in zip(click, tick)], 6000)


def shutter() -> list[float]:
    one = key() + [0.0] * int(0.05 * RATE)
    return one + [s * 0.8 for s in key()]


def whoosh() -> list[float]:
    n = noise(0.7)
    out, y = [], 0.0
    for i, s in enumerate(n):
        t = i / len(n)
        cutoff = 300 + 4000 * math.sin(math.pi * t)
        a = 1 - math.exp(-2 * math.pi * cutoff / RATE)
        y += a * (s - y)
        out.append(y * math.sin(math.pi * t) ** 2)
    return out


def strike() -> list[float]:
    n = noise(0.18)
    out, y = [], 0.0
    for i, s in enumerate(n):
        t = i / len(n)
        a = 1 - math.exp(-2 * math.pi * (6000 - 5000 * t) / RATE)
        y += a * (s - y)
        out.append(y * (1 - t) ** 2)
    return out


def bell(notes: list[int], gap: float = 0.09, length: float = 1.6) -> list[float]:
    out = [0.0] * int((length + gap * len(notes)) * RATE)
    for k, note in enumerate(notes):
        f = freq(note)
        a0 = int(k * gap * RATE)
        for i in range(a0, len(out)):
            t = (i - a0) / RATE
            env = math.exp(-t * 3) * min(1, t / 0.003)
            out[i] += env * (
                math.sin(2 * math.pi * f * t)
                + 0.35 * math.sin(2 * math.pi * f * 2.01 * t)
                + 0.12 * math.sin(2 * math.pi * f * 3.02 * t)
            )
    return out


def alert() -> list[float]:
    out = [0.0] * int(0.6 * RATE)
    for f in (233.0, 247.0):  # a soft, slightly uneasy beat
        for i in range(len(out)):
            t = i / RATE
            out[i] += math.exp(-t * 6) * math.sin(2 * math.pi * f * t)
    return out


if __name__ == "__main__":
    write("music.wav", music(80), peak=0.7)
    write("key.wav", key())
    write("shutter.wav", shutter())
    write("whoosh.wav", whoosh())
    write("strike.wav", strike())
    write("chime.wav", bell([76, 83]))  # E6 then B6: Squint's "done" sound
    write("alert.wav", alert())
    print(f"wrote {sorted(p.name for p in OUT.iterdir())}")
