"""Build the film's timeline from the voiceover, then compose music and effects to fit it.

    video/tts/.venv/bin/python video/scripts/make_score.py

Reads src/v2/vo.json (seconds per voice line, from tts/make_voice.py) and writes
src/v2/timeline.json (scene starts and lengths, hook shot timing, voice cues) and
public/sfx2/*.wav. The timeline is the single source of truth: the film imports it and
the music is composed against it, so voice, picture and music can't drift apart.
"""

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf

FPS = 30
RATE = 44100
BPM = 116
ROOT = Path(__file__).resolve().parent.parent
VO = ROOT / "src" / "v2" / "vo.json"
TIMELINE = ROOT / "src" / "v2" / "timeline.json"
OUT = ROOT / "public" / "sfx2"
rng = np.random.default_rng(11)

# (scene, voice line, cue frames from scene start, minimum length, tail after the voice)
SCENES = [
    ("twist", "twist", 14, 150, 24),
    ("refusal", "refusal", 6, 100, 10),
    ("mentor", "mentor", 10, 140, 10),
    ("threshold", "threshold", 10, 210, 18),
    ("reward", "reward", 40, 130, 10),
    ("close", "close", 10, 170, 40),
]
# The hook: one voice line per beat, quickening into a four-shot montage.
HOOK_LEAD = 8
HOOK_BEATS = [("open", 84, 6), ("text", 60, 6), ("dash", 60, 6)]  # (line, minimum, cue)
MONTAGE_SPLIT = [0.3, 0.26, 0.23, 0.21]
CARD_AT = 48  # frames into the close scene


def frames(seconds: float) -> int:
    return math.ceil(seconds * FPS)


def build_timeline() -> dict:
    vo = json.loads(VO.read_text())
    shots, cues, t = [], [], HOOK_LEAD
    for line, minimum, cue in HOOK_BEATS:
        length = max(minimum, cue + frames(vo[line]) + 8)
        shots.append({"start": t, "length": length})
        cues.append({"file": f"vo/{line}.wav", "at": t + cue, "length": frames(vo[line])})
        t += length
    montage = max(96, 4 + frames(vo["montage"]) + 10)
    cues.append({"file": "vo/montage.wav", "at": t + 4, "length": frames(vo["montage"])})
    for share in MONTAGE_SPLIT:
        length = round(montage * share)
        shots.append({"start": t, "length": length})
        t += length
    hook_length = t + 6
    scenes = [{"name": "hook", "start": 0, "length": hook_length, "cues": cues}]
    start = hook_length
    for name, line, cue, minimum, tail in SCENES:
        speech = frames(vo[line])
        length = max(minimum, cue + speech + tail)
        scenes.append({"name": name, "start": start, "length": length,
                       "cues": [{"file": f"vo/{line}.wav", "at": start + cue, "length": speech}]})  # fmt: skip
        start += length
    return {"fps": FPS, "total": start, "cardAt": CARD_AT, "hookShots": shots, "scenes": scenes}


# MARK: instruments (mono numpy arrays; mixed to stereo with a pan)


def env_exp(n: int, decay: float, attack: float = 0.002) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1, t / attack) * np.exp(-t / decay)


def sine(f, n, phase=0.0) -> np.ndarray:
    return np.sin(2 * np.pi * f * np.arange(n) / RATE + phase)


def freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def onepole(x: np.ndarray, cutoff: float, high: bool = False) -> np.ndarray:
    a = 1 - math.exp(-2 * math.pi * cutoff / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return x - y if high else y


def kick() -> np.ndarray:
    n = int(0.4 * RATE)
    t = np.arange(n) / RATE
    phase = 2 * np.pi * np.cumsum(48 + 110 * np.exp(-t * 35)) / RATE
    click = rng.uniform(-1, 1, n) * np.exp(-t * 400) * 0.3
    return (np.sin(phase) * np.exp(-t * 8) + click) * 0.9


def clap() -> np.ndarray:
    n = int(0.25 * RATE)
    noise = onepole(rng.uniform(-1, 1, n), 1200, high=True)
    t = np.arange(n) / RATE
    bursts = sum(np.exp(-np.maximum(0, t - d) * 60) * (t >= d) for d in (0, 0.012, 0.024))
    return noise * bursts * np.exp(-t * 14) * 0.6


def hat(open_: bool = False) -> np.ndarray:
    n = int((0.18 if open_ else 0.045) * RATE)
    noise = onepole(rng.uniform(-1, 1, n), 7000, high=True)
    return noise * env_exp(n, 0.06 if open_ else 0.012) * 0.5


def shaker() -> np.ndarray:
    n = int(0.08 * RATE)
    noise = onepole(rng.uniform(-1, 1, n), 5000, high=True)
    t = np.arange(n) / RATE
    return noise * np.sin(np.pi * t / t[-1]) ** 2 * 0.25


def pluck(midi: float, seconds: float = 0.6, bright: float = 0.5) -> np.ndarray:
    n = int(seconds * RATE)
    f = freq(midi)
    tone = sine(f, n) + bright * 0.5 * sine(2 * f, n) + bright * 0.25 * sine(3 * f, n) + 0.15 * sine(f * 1.003, n)
    return tone * env_exp(n, 0.16) * 0.5


def bass(midi: float, seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    f = freq(midi)
    tone = sine(f, n) + 0.35 * sine(2 * f, n) + 0.12 * sine(3 * f, n)
    return tone * env_exp(n, seconds * 0.7, attack=0.006) * 0.55


def pad(notes: list[int], seconds: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(seconds * RATE)
    left, right = np.zeros(n), np.zeros(n)
    swell = np.sin(np.pi * np.arange(n) / n) ** 1.5
    for note in notes:
        f = freq(note)
        left += sine(f * 0.9965, n, rng.uniform(0, 6)) + 0.3 * sine(2 * f * 0.998, n)
        right += sine(f * 1.0035, n, rng.uniform(0, 6)) + 0.3 * sine(2 * f * 1.002, n)
    return left * swell * 0.05, right * swell * 0.05


def sweep(seconds: float, lo: float, hi: float, rising: bool = True) -> np.ndarray:
    n = int(seconds * RATE)
    noise = rng.uniform(-1, 1, n)
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        x = i / n if rising else 1 - i / n
        a = 1 - math.exp(-2 * math.pi * (lo + (hi - lo) * x * x) / RATE)
        acc += a * (noise[i] - acc)
        out[i] = acc
    shape = (np.arange(n) / n) ** 2 if rising else (1 - np.arange(n) / n) ** 3
    return out * shape


# MARK: mixing


class Mix:
    def __init__(self, seconds: float):
        n = int(seconds * RATE)
        self.left, self.right = np.zeros(n), np.zeros(n)
        self.send = np.zeros(n)  # reverb send (mono)
        self.duck = np.ones(n)  # sidechain: pads and bass dip on every kick

    def add(self, at: float, x: np.ndarray, gain: float = 1.0, pan: float = 0.0, verb: float = 0.0, right=None):
        i = int(at * RATE)
        if i >= len(self.left) or i + len(x) <= 0:
            return
        j = min(len(self.left), i + len(x))
        seg = x[: j - i] * gain
        l_gain, r_gain = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        if right is None:
            self.left[i:j] += seg * l_gain * math.sqrt(2)
            self.right[i:j] += seg * r_gain * math.sqrt(2)
        else:
            self.left[i:j] += seg
            self.right[i:j] += right[: j - i] * gain
        if verb:
            self.send[i:j] += seg * verb

    def sidechain(self, at: float, depth: float = 0.45, release: float = 0.22):
        i = int(at * RATE)
        n = min(len(self.duck) - i, int(release * 2 * RATE))
        if n <= 0:
            return
        t = np.arange(n) / RATE
        self.duck[i : i + n] = np.minimum(self.duck[i : i + n], 1 - depth * np.exp(-t / (release / 3)))

    def reverb(self) -> None:
        """A small Schroeder-style room: parallel feedback delays, slightly different per side."""
        for side, offset in ((self.left, 0), (self.right, 23)):
            wet = np.zeros_like(side)
            for ms, fb in ((29.7, 0.77), (37.1, 0.74), (41.1, 0.72), (43.7, 0.70)):
                d = int((ms + offset * 0.1) * RATE / 1000)
                buf = np.copy(self.send)
                for k in range(d, len(buf)):
                    buf[k] += fb * buf[k - d]
                wet += buf
            side += onepole(wet, 6000) * 0.06


def score(timeline: dict) -> np.ndarray:
    sec = lambda f: f / FPS  # noqa: E731
    scenes = {s["name"]: s for s in timeline["scenes"]}
    end = sec(timeline["total"])
    mix = Mix(end + 3)
    beat = 60 / BPM
    bar = beat * 4

    hook_end = sec(scenes["twist"]["start"])
    mentor = sec(scenes["mentor"]["start"])
    groove_back = sec(scenes["threshold"]["start"])
    # The end card lands in the pause after "Nothing leaves your Mac." (see Film.tsx Close).
    card = sec(scenes["close"]["start"] + CARD_AT)

    hook_chords = [(45, [69, 72, 76]), (41, [69, 72, 77]), (48, [67, 72, 76]), (43, [67, 71, 74])]  # Am F C G
    lift_chords = [(48, [64, 67, 72]), (43, [62, 67, 71]), (45, [64, 69, 72]), (41, [65, 69, 72])]  # C G Am F

    def groove(start: float, stop: float, chords, intensity: float, drums: bool = True, first_bar_soft: bool = False):
        t, k = start, 0
        while t < stop - 0.01:
            root, notes = chords[(k // 4) % 4]
            beat_in_bar = k % 4
            soft = first_bar_soft and k < 4
            if drums and not soft:
                if beat_in_bar in (0, 2):
                    mix.add(t, kick(), 0.5 * intensity)
                    mix.sidechain(t)
                if beat_in_bar == 3:
                    mix.add(t + beat / 2, kick(), 0.25 * intensity)  # the push into the next bar
                if beat_in_bar in (1, 3):
                    mix.add(t, clap(), 0.7 * intensity, pan=0.05, verb=0.5)
                for s in range(4):  # 16th shakers, swung accents, gently panned
                    accent = 1.0 if s == 2 else 0.55
                    mix.add(t + s * beat / 4, shaker(), 0.8 * accent * intensity, pan=0.35 if s % 2 else -0.25)
                mix.add(t + beat / 2, hat(), 0.55 * intensity, pan=0.2)
            # Bass: eighth notes on the root, octave jump on the last eighth of the bar.
            for e in range(2):
                note = root - 12 + (12 if beat_in_bar == 3 and e == 1 else 0)
                mix.add(t + e * beat / 2, bass(note, beat / 2 * 0.95), 0.4 * intensity)
            # Plucks: an arpeggio on eighths, alternating sides, into the reverb.
            for e in range(2):
                step = beat_in_bar * 2 + e  # 8 steps, locked to the bar
                note = notes[[0, 1, 2, 1, 0, 1, 2, 1][step]] + (12 if step in (2, 6) else 0)
                mix.add(t + e * beat / 2, pluck(note), 0.42 * intensity, pan=-0.4 if e else 0.4, verb=0.6)
            if beat_in_bar == 0:
                l, r = pad(notes + [notes[0] - 12], bar * 1.25)
                mix.add(t, l, 0.9 * intensity, right=r, verb=0.3)
            t += beat
            k += 1

    # Hook: one soft bar, then the groove; a riser into the twist.
    groove(0, hook_end, hook_chords, 0.85, first_bar_soft=True)
    mix.add(hook_end - bar, sweep(bar, 300, 9000), 0.5, verb=0.3)

    # Twist and refusal: the beat drops out. An impact, then a low drone with a heartbeat.
    boom_n = int(2.4 * RATE)
    t = np.arange(boom_n) / RATE
    boom = np.sin(2 * np.pi * np.cumsum(36 + 70 * np.exp(-t * 10)) / RATE) * np.exp(-t * 1.4)
    mix.add(hook_end, boom, 0.6)
    mix.add(hook_end, sweep(1.2, 5000, 200, rising=False), 0.5, verb=0.5)
    drone_len = mentor - hook_end
    n = int(drone_len * RATE)
    shape = np.minimum(1, np.arange(n) / (0.6 * RATE)) * np.minimum(1, (n - np.arange(n)) / (0.8 * RATE))
    for f, g, pan in ((55.0, 0.08, 0), (82.4, 0.07, -0.3), (110.0, 0.07, 0.3), (116.5, 0.04, 0.1), (220.0, 0.03, -0.2)):
        mix.add(hook_end, sine(f, n) * shape * (1 + 0.25 * sine(0.5, n)), g, pan=pan)
    hb = hook_end + 0.6
    while hb < mentor - 0.6:
        mix.add(hb, kick(), 0.3)
        mix.add(hb + 0.22, kick(), 0.2)
        hb += beat * 2

    # Mentor: a riser into the reveal, then the lift chords without drums for two bars.
    mix.add(mentor - bar / 2, sweep(bar / 2, 400, 8000), 0.45)
    groove(mentor, groove_back, lift_chords, 0.75, drums=False)

    # Threshold to the end card: the full groove again, then a final chord on the card.
    groove(groove_back, card, lift_chords, 1.0)
    mix.add(card - beat, sweep(beat, 600, 9000), 0.4)
    l, r = pad([48, 60, 64, 67, 71, 74], end - card + 2.5)
    mix.add(card, l, 2.2, right=r, verb=0.6)
    mix.add(card, kick(), 0.5)
    for i, note in enumerate([72, 76, 79, 83]):
        mix.add(card + i * beat / 2, pluck(note, 1.2), 0.3, pan=-0.3 + i * 0.2, verb=0.8)

    # Sidechain the sustained parts, add the room, then master.
    mix.left *= mix.duck
    mix.right *= mix.duck
    mix.reverb()
    for _ in range(2):  # a 12 dB/octave low cut: the voice owns the low mids
        mix.left = onepole(mix.left, 110, high=True)
        mix.right = onepole(mix.right, 110, high=True)
    stereo = np.stack([mix.left, mix.right], axis=1)
    fade = int(1.2 * RATE)
    stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
    rms = np.sqrt(np.mean(stereo**2))
    stereo *= 10 ** (-16 / 20) / rms  # music bed at about -16 dBFS RMS
    return np.tanh(stereo * 1.1) / np.tanh(1.1)  # soft limiter, peaks under 0 dBFS


def effects() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    def write(name: str, x: np.ndarray, peak: float = 0.9) -> None:
        sf.write(OUT / name, x / max(1e-9, np.max(np.abs(x))) * peak, RATE)

    n = int(0.22 * RATE)
    t = np.arange(n) / RATE
    thunk = np.sin(2 * np.pi * np.cumsum(90 + 120 * np.exp(-t * 40)) / RATE) * np.exp(-t * 22)
    write("paste.wav", thunk + 0.2 * onepole(rng.uniform(-1, 1, n), 3000) * np.exp(-t * 60))
    write("ring.wav", pluck(88, 0.7, 0.3))
    write("key.wav", hat() * 1.5 + 0.3 * onepole(rng.uniform(-1, 1, int(0.045 * RATE)), 2000) * env_exp(int(0.045 * RATE), 0.008))
    shutter = np.concatenate([hat(), np.zeros(int(0.04 * RATE)), hat()])
    write("shutter.wav", shutter)
    write("whoosh.wav", sweep(0.6, 300, 6000))
    chime = np.zeros(int(1.8 * RATE))
    for i, note in enumerate((76, 83)):
        x = pluck(note, 1.6, 0.25)
        k = int(i * 0.09 * RATE)
        chime[k : k + len(x)] += x[: len(chime) - k]
    write("chime.wav", chime)
    write("strike.wav", onepole(rng.uniform(-1, 1, int(0.18 * RATE)), 3000) * np.linspace(1, 0, int(0.18 * RATE)) ** 2)


if __name__ == "__main__":
    timeline = build_timeline()
    TIMELINE.write_text(json.dumps(timeline, indent=2) + "\n")
    speech = sum(c["length"] for s in timeline["scenes"] for c in s["cues"])
    for s in timeline["scenes"]:
        print(f"{s['name']:<10} {s['start'] / FPS:5.1f}s  +{s['length'] / FPS:4.1f}s")
    print(f"total {timeline['total'] / FPS:.1f}s, speech {speech / timeline['total']:.0%}")
    effects()
    sf.write(OUT / "music.wav", score(timeline), RATE)
    print("wrote music and effects to", OUT)
