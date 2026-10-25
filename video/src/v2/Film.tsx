// Squint, the 45-second cut: a hook of careless pastes, the twist ("did you check the
// corners?"), and Squint as the lazy hero's mentor. Timing comes from timeline.json,
// which make_score.py builds from the real voiceover.
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import timeline from "./timeline.json";
import { AppIcon, C, Eye, FONT, KeyCap, Toast, Window, Words, ease, useEnter } from "../ui";
import { HOOK_SHOTS, Reveal, SHOT_H, SHOT_W } from "./Screens";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const scene = (name: string) => timeline.scenes.find((s) => s.name === name)!;

/** Fade a scene in from the previous one. */
const FadeIn: React.FC<{ children: React.ReactNode; frames?: number; bg?: string }> = ({
  children,
  frames = 8,
  bg = C.bg,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: bg, opacity: interpolate(frame, [0, frames], [0, 1], clamp) }}>
      {children}
    </AbsoluteFill>
  );
};

/** A screenshot component drawn at its native 1600x1000, scaled to `width`. */
const Scaled: React.FC<{ width: number; children: React.ReactNode; radius?: number; shadow?: boolean }> = ({
  width,
  children,
  radius = 14,
  shadow = true,
}) => {
  const k = width / SHOT_W;
  return (
    <div
      style={{
        width,
        height: SHOT_H * k,
        borderRadius: radius,
        overflow: "hidden",
        boxShadow: shadow ? "0 24px 70px rgba(0,0,0,0.22), 0 0 0 1px rgba(0,0,0,0.08)" : undefined,
        position: "relative",
      }}
    >
      <div style={{ width: SHOT_W, height: SHOT_H, transform: `scale(${k})`, transformOrigin: "top left" }}>
        {children}
      </div>
    </div>
  );
};

// MARK: - Hook: paste, paste, paste…

// When each screenshot is on screen (frames): one voice line per beat, then a montage.
const HOOK_STARTS = timeline.hookShots.map((s) => s.start);
const HOOK_LENGTHS = timeline.hookShots.map((s) => s.length);
const PASTE_AT = HOOK_STARTS.map((s, i) => s + Math.round(HOOK_LENGTHS[i] * 0.62));
const SCREEN = { x: 96, y: 200, w: 1040 };
const CHAT = { x: 1220, y: 96, w: 600, h: 890 };
const THUMB = 300;
// Thumbnails show the top of each screenshot, where its content is.
const THUMB_CROP = 0.6;
const THUMB_H = ((THUMB * SHOT_H) / SHOT_W) * THUMB_CROP;
const GAP = 18;

const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const current = Math.max(0, HOOK_STARTS.filter((s) => frame >= s).length - 1);
  const Shot = HOOK_SHOTS[current];
  const shotIn = spring({ frame: frame - HOOK_STARTS[current], fps, config: { damping: 200 }, durationInFrames: 10 });
  const visibleRows = Math.floor((CHAT.h - 90) / (THUMB_H + GAP));
  const scroll = PASTE_AT.slice(visibleRows).reduce(
    (sum, p) => sum + spring({ frame: frame - p, fps, config: { damping: 200 }, durationInFrames: 12 }) * (THUMB_H + GAP),
    0,
  );
  const title = useEnter(4, 20);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <div
        style={{
          position: "absolute",
          left: SCREEN.x,
          top: 92,
          fontFamily: FONT,
          fontSize: 54,
          fontWeight: 700,
          letterSpacing: -1.2,
          color: C.ink,
          ...title,
        }}
      >
        Every day, you paste your screen into AI.
      </div>
      <div
        style={{
          position: "absolute",
          left: SCREEN.x,
          top: SCREEN.y,
          opacity: shotIn,
          transform: `scale(${0.96 + 0.04 * shotIn})`,
          transformOrigin: "center",
        }}
      >
        <Scaled width={SCREEN.w}>
          <Reveal at={null}>
            <Shot />
          </Reveal>
        </Scaled>
      </div>

      {/* The AI chat, collecting everything you paste. */}
      <div
        style={{
          position: "absolute",
          left: CHAT.x,
          top: CHAT.y,
          width: CHAT.w,
          height: CHAT.h,
          borderRadius: 24,
          background: "white",
          boxShadow: "0 24px 70px rgba(0,0,0,0.14), 0 0 0 1px rgba(0,0,0,0.06)",
          overflow: "hidden",
        }}
      >
        <div style={{ position: "relative", zIndex: 2, background: "white", height: 70, display: "flex", alignItems: "center", gap: 12, padding: "0 26px", borderBottom: "1px solid #eee", fontFamily: FONT, fontSize: 22, fontWeight: 600, color: C.ink }}>
          <span style={{ fontSize: 26 }}>✦</span> AI Assistant
        </div>
        <div style={{ position: "absolute", top: 90, right: 26, transform: `translateY(${-scroll}px)`, transition: "none" }}>
          {PASTE_AT.map((p, i) => {
            const s = spring({ frame: frame - p, fps, config: { damping: 16, stiffness: 140 } });
            if (frame < p) return null;
            const Thumb = HOOK_SHOTS[i];
            return (
              <div key={i} style={{ marginBottom: GAP, height: THUMB_H, overflow: "hidden", borderRadius: 12, boxShadow: "0 0 0 1px rgba(0,0,0,0.08)", opacity: s, transform: `translateX(${(1 - s) * -420}px) scale(${0.7 + 0.3 * s})`, transformOrigin: "right center" }}>
                <Scaled width={THUMB} radius={0} shadow={false}>
                  <Thumb />
                </Scaled>
              </div>
            );
          })}
        </div>
      </div>

      {/* ⌘V on every paste */}
      {PASTE_AT.map((p, i) => {
        const o = interpolate(frame, [p - 6, p - 2, p + 8, p + 13], [0, 1, 1, 0], clamp);
        return o > 0 ? (
          <div key={i} style={{ position: "absolute", left: SCREEN.x + SCREEN.w - 190, top: SCREEN.y + 680, display: "flex", gap: 10, opacity: o }}>
            <KeyCap label="⌘" pressAt={p} size={70} />
            <KeyCap label="V" pressAt={p} size={70} />
          </div>
        ) : null;
      })}
    </AbsoluteFill>
  );
};

// MARK: - Twist: did you check the corners?

const Twist: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const w = 430;
  const h = (w * SHOT_H) / SHOT_W;
  const ringAt = (i: number) => 22 + i * 6;
  return (
    <AbsoluteFill style={{ background: "#0b0b0c" }}>
      <div style={{ position: "absolute", top: 70, width: "100%", textAlign: "center" }}>
        <Words text="You checked the bug." start={12} size={64} color="rgba(245,245,247,0.75)" weight={600} />
      </div>
      <div style={{ position: "absolute", top: 180, left: 0, right: 0, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 24, padding: "0 40px" }}>
        {HOOK_SHOTS.map((Shot, i) => {
          const s = spring({ frame: frame - i * 2, fps, config: { damping: 200 }, durationInFrames: 14 });
          return (
            <div key={i} style={{ opacity: s, transform: `scale(${0.85 + 0.15 * s})` }}>
              <Scaled width={w} radius={12}>
                <Reveal at={ringAt(i)} ring={16}>
                  <Shot />
                </Reveal>
              </Scaled>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", bottom: 70, width: "100%", textAlign: "center" }}>
        <Words text="Did you check the corners?" start={58} size={92} color="#f5f5f7" />
      </div>
    </AbsoluteFill>
  );
};

// MARK: - Refusal

const Refusal: React.FC = () => {
  const frame = useCurrentFrame();
  const strike = interpolate(frame, [26, 36], [0, 100], { ...clamp, easing: ease });
  const swap = interpolate(frame, [42, 50], [0, 1], clamp);
  return (
    <FadeIn>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ position: "relative", ...useEnter(2), opacity: 1 - swap }}>
          <span style={{ fontFamily: FONT, fontSize: 96, fontWeight: 700, letterSpacing: -2.5, color: C.ink }}>
            Check every corner?
          </span>
          <div style={{ position: "absolute", left: -10, top: "54%", height: 9, width: `calc(${strike}% + 20px)`, background: C.danger, borderRadius: 5 }} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <Words text="We're all a little lazy. 🦥" start={52} size={96} />
      </AbsoluteFill>
    </FadeIn>
  );
};

// MARK: - Mentor

const Mentor: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 4, fps, config: { damping: 14, stiffness: 100 } });
  const squint = interpolate(frame, [40, 58], [0, 1], { ...clamp, easing: ease });
  const glow = interpolate(frame, [46, 100], [0, 1], clamp);
  return (
    <FadeIn bg={C.night}>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 40 }}>
        <div style={{ width: 260, height: 260, borderRadius: 60, background: "linear-gradient(#41434a, #17171b)", display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${pop})`, boxShadow: `0 0 ${150 * glow}px rgba(0,113,227,${0.5 * glow}), 0 30px 80px rgba(0,0,0,0.6)` }}>
          <Eye size={170} squint={squint} />
        </div>
        <Words text="Stay lazy. Meet Squint." start={14} size={110} color="#f5f5f7" />
        <Words text="It does the squinting, so you don't have to." start={80} size={52} weight={500} color="rgba(245,245,247,0.7)" stagger={3} />
      </AbsoluteFill>
    </FadeIn>
  );
};

// MARK: - Threshold: the same bug, screenshotted with Squint running

const HERO_W = 1300;
const HERO_H = (HERO_W * SHOT_H) / SHOT_W;

const Threshold: React.FC = () => {
  const frame = useCurrentFrame();
  const keys = interpolate(frame, [4, 10, 52, 60], [0, 1, 1, 0], clamp);
  const sel = interpolate(frame, [40, 64], [0, 1], { ...clamp, easing: ease });
  const flash = interpolate(frame, [66, 69, 82], [0, 0.8, 0], clamp);
  const wipe = interpolate(frame, [96, 126], [0, 100], { ...clamp, easing: ease });
  const timer = interpolate(frame, [66, 103], [0, 1.2], clamp);
  return (
    <FadeIn bg="#e9ecf5">
      <AbsoluteFill style={{ background: "radial-gradient(circle at 25% 15%, #d4e6ff 0%, #ebe6ff 45%, #f7e9f2 100%)" }} />
      <AbsoluteFill>
        <div style={{ position: "absolute", left: 90, top: 236, width: HERO_W, height: HERO_H, borderRadius: 18, overflow: "hidden", boxShadow: "0 40px 100px rgba(0,0,0,0.25)" }}>
          <Img src={staticFile("hero.png")} style={{ width: HERO_W, height: HERO_H, position: "absolute" }} />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${100 - wipe}% 0 0)` }}>
            <Img src={staticFile("hero-redacted.png")} style={{ width: HERO_W, height: HERO_H }} />
          </div>
          {frame >= 94 && frame < 128 && (
            <div style={{ position: "absolute", left: `${wipe}%`, top: 0, bottom: 0, width: 4, background: C.accent, boxShadow: `0 0 26px 8px ${C.accent}` }} />
          )}
          {frame >= 38 && frame < 66 && (
            <div style={{ position: "absolute", left: 0, top: 0, width: HERO_W * sel, height: HERO_H * sel, border: "3px dashed rgba(0,0,0,0.55)", background: "rgba(0,113,227,0.08)" }} />
          )}
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", bottom: 56, width: "100%", display: "flex", justifyContent: "center", gap: 14, opacity: keys }}>
        <KeyCap label="⌃" pressAt={22} />
        <KeyCap label="⇧" pressAt={24} />
        <KeyCap label="⌘" pressAt={26} />
        <KeyCap label="4" pressAt={28} />
      </div>
      <AbsoluteFill style={{ background: "white", opacity: flash }} />
      <Toast start={100} title="Hid 2 things in your screenshot" subtitle="The redacted copy is on your clipboard" />
      {frame >= 66 && (
        <div style={{ position: "absolute", top: 200, right: 40, fontFamily: '"SF Mono", Menlo, monospace', fontSize: 26, color: C.ink, background: "rgba(255,255,255,0.8)", padding: "8px 16px", borderRadius: 12 }}>
          ⏱ {timer.toFixed(1)} s
        </div>
      )}
    </FadeIn>
  );
};

// MARK: - Reward

const ANSWER =
  "The Pay button is position: absolute with left: -90px, so it escapes the card. Add position: relative to .summary and drop the rotate.";

const Reward: React.FC = () => {
  const frame = useCurrentFrame();
  const typed = ANSWER.slice(0, Math.max(0, Math.floor((frame - 34) * 2.4)));
  return (
    <FadeIn>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={useEnter(0, 30)}>
          <Window width={1300} height={740} title="AI Assistant">
            <div style={{ padding: "34px 44px", display: "flex", flexDirection: "column", gap: 22 }}>
              <div style={{ alignSelf: "flex-end", ...useEnter(12, 30) }}>
                <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: "0 0 0 1px rgba(0,0,0,0.1)" }}>
                  <Img src={staticFile("hero-redacted.png")} style={{ width: 640, display: "block" }} />
                </div>
                <div style={{ marginTop: 10, float: "right", fontFamily: FONT, fontSize: 26, color: "white", background: C.accent, padding: "12px 20px", borderRadius: 22 }}>
                  why is the pay button floating?
                </div>
              </div>
              {frame >= 34 && (
                <div style={{ maxWidth: 820, fontFamily: FONT, fontSize: 27, lineHeight: 1.45, color: C.ink, background: "#f0f0f2", padding: "16px 24px", borderRadius: 22 }}>
                  {typed}
                </div>
              )}
            </div>
          </Window>
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", top: 20, width: "100%", display: "flex", justifyContent: "center", gap: 10, opacity: interpolate(frame, [6, 10, 22, 28], [0, 1, 1, 0], clamp) }}>
        <KeyCap label="⌘" pressAt={14} size={64} />
        <KeyCap label="V" pressAt={14} size={64} />
      </div>
    </FadeIn>
  );
};

// MARK: - Close

const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const card = spring({ frame: frame - timeline.cardAt, fps, config: { damping: 200 } });
  const first = interpolate(frame, [timeline.cardAt - 8, timeline.cardAt], [1, 0], clamp);
  return (
    <FadeIn>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: first }}>
        <Words text="Nothing leaves your Mac." start={6} size={104} />
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 24, opacity: card }}>
        <AppIcon size={200} style={{ transform: `scale(${0.85 + 0.15 * card})` }} />
        <Words text="Squint" start={timeline.cardAt + 6} size={132} />
        <div style={{ ...useEnter(timeline.cardAt + 22), fontFamily: FONT, fontSize: 62, fontWeight: 600, color: C.accent }}>mysquint.tech</div>
        <div style={{ ...useEnter(timeline.cardAt + 36), fontFamily: FONT, fontSize: 28, color: C.muted, letterSpacing: 0.5 }}>
          Free and open source · Powered by Gemma 3, on your Mac
        </div>
      </AbsoluteFill>
    </FadeIn>
  );
};

// MARK: - Sound

const Sfx: React.FC<{ at: number; file: string; volume?: number }> = ({ at, file, volume = 0.6 }) => (
  <Sequence from={at} layout="none">
    <Audio src={staticFile(`sfx2/${file}`)} volume={volume} />
  </Sequence>
);

const CUES = timeline.scenes.flatMap((s) => s.cues);

/** A steady music bed that dips a little under speech (the voice always leads). */
const musicVolume = (f: number) => {
  const speaking = CUES.some((c) => f >= c.at - 4 && f <= c.at + c.length + 4);
  return (speaking ? 0.3 : 0.42) * Math.min(1, f / 12);
};

const SCENES: Record<string, React.FC> = { hook: Hook, twist: Twist, refusal: Refusal, mentor: Mentor, threshold: Threshold, reward: Reward, close: Close };

export const Film: React.FC = () => {
  const s = (name: string) => scene(name).start;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {timeline.scenes.map((sc) => {
        const Scene = SCENES[sc.name];
        return (
          <Sequence key={sc.name} from={sc.start} durationInFrames={sc.length}>
            <Scene />
          </Sequence>
        );
      })}
      <Audio src={staticFile("sfx2/music.wav")} volume={musicVolume} />
      {CUES.map((c) => (
        <Sequence key={c.file} from={c.at} layout="none">
          <Audio src={staticFile(c.file)} volume={1} />
        </Sequence>
      ))}
      {PASTE_AT.map((p) => <Sfx key={p} at={s("hook") + p} file="paste.wav" volume={0.7} />)}
      {HOOK_SHOTS.map((_, i) => <Sfx key={i} at={s("twist") + 22 + i * 6} file="ring.wav" volume={0.22} />)}
      <Sfx at={s("refusal") + 26} file="strike.wav" volume={0.45} />
      <Sfx at={s("mentor") + 46} file="chime.wav" volume={0.45} />
      {[22, 24, 26, 28].map((f) => <Sfx key={f} at={s("threshold") + f} file="key.wav" volume={0.5} />)}
      <Sfx at={s("threshold") + 66} file="shutter.wav" volume={0.6} />
      <Sfx at={s("threshold") + 96} file="whoosh.wav" volume={0.35} />
      <Sfx at={s("threshold") + 100} file="chime.wav" volume={0.4} />
      <Sfx at={s("reward") + 14} file="paste.wav" volume={0.7} />
      <Sfx at={s("close") + timeline.cardAt} file="chime.wav" volume={0.4} />
    </AbsoluteFill>
  );
};

export const FILM_LENGTH = timeline.total;
