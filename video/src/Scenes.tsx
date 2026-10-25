import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  AppIcon,
  C,
  Caption,
  Chapter,
  Eye,
  FONT,
  KeyCap,
  MONO,
  Toast,
  Window,
  Words,
  ease,
  useEnter,
  useExit,
} from "./ui";

// The real eval screenshot (1700x448) and the real boxes of its fake secrets.
const ENV_W = 1700;
const ENV_H = 448;
const SECRETS = [
  { label: "database password", box: [488, 91, 272, 25] },
  { label: "Stripe live key", box: [328, 137, 512, 25] },
  { label: "JWT secret", box: [344, 183, 288, 20] },
  { label: "session token", box: [264, 229, 768, 20] },
];

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const EnvShot: React.FC<{ width: number; redacted?: boolean; style?: React.CSSProperties }> = ({
  width,
  redacted,
  style,
}) => (
  <Img
    src={staticFile(redacted ? "env-redacted.png" : "env.png")}
    style={{ width, height: (width * ENV_H) / ENV_W, display: "block", ...style }}
  />
);

// MARK: - Chat (scenes 1 and 7)

type Message = {
  from: "me" | "ai";
  at: number;
  text?: string;
  image?: React.ReactNode;
  typed?: boolean;
};

const Bubble: React.FC<{ m: Message }> = ({ m }) => {
  const frame = useCurrentFrame();
  const style = useEnter(m.at, 30);
  const me = m.from === "me";
  const shown = m.typed
    ? m.text!.slice(0, Math.max(0, Math.floor((frame - m.at - 8) * 1.6)))
    : m.text;
  return (
    <div style={{ display: "flex", justifyContent: me ? "flex-end" : "flex-start", ...style }}>
      <div
        style={{
          maxWidth: 760,
          display: "flex",
          flexDirection: "column",
          alignItems: me ? "flex-end" : "flex-start",
          gap: 10,
        }}
      >
        {m.image && (
          <div
            style={{
              borderRadius: 18,
              overflow: "hidden",
              boxShadow: "0 0 0 1px rgba(0,0,0,0.08)",
            }}
          >
            {m.image}
          </div>
        )}
        {m.text && (
          <div
            style={{
              fontFamily: FONT,
              fontSize: 26,
              lineHeight: 1.4,
              padding: "14px 22px",
              borderRadius: 24,
              background: me ? C.accent : "#f0f0f2",
              color: me ? "white" : C.ink,
            }}
          >
            {shown}
          </div>
        )}
      </div>
    </div>
  );
};

const Chat: React.FC<{
  messages: Message[];
  scrollAt?: number[];
  height?: number;
  style?: React.CSSProperties;
}> = ({ messages, scrollAt = [], height = 760, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scroll = scrollAt.reduce(
    (sum, at) => sum + spring({ frame: frame - at, fps, config: { damping: 200 } }) * 330,
    0,
  );
  return (
    <Window width={1240} height={height} title="Your AI assistant" style={style}>
      <div style={{ position: "absolute", inset: 0, overflow: "hidden", padding: "36px 44px" }}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 26,
            transform: `translateY(${-scroll}px)`,
          }}
        >
          {messages.map((m, i) => (
            <Bubble key={i} m={m} />
          ))}
        </div>
      </div>
    </Window>
  );
};

const MiniChart = () => (
  <div style={{ width: 360, height: 200, background: "#fff", padding: 22, display: "flex", gap: 14, alignItems: "flex-end" }}>
    {[0.3, 0.55, 0.42, 0.8, 0.0, 0.0, 0.0].map((h, i) => (
      <div key={i} style={{ flex: 1, height: `${Math.max(h * 100, 3)}%`, background: h ? "#5e5ce6" : "#e5e5ea", borderRadius: 6 }} />
    ))}
  </div>
);

const MiniForm = () => (
  <div style={{ width: 360, height: 200, background: "#fff", padding: 22, fontFamily: FONT, fontSize: 16, color: C.ink }}>
    {[
      ["Name", "Aiko Fakeworth"],
      ["Email", "aiko.fakeworth@outlook.com"],
      ["Phone", "+1 415 555 0142"],
    ].map(([k, v]) => (
      <div key={k} style={{ marginBottom: 14 }}>
        <div style={{ color: C.muted, fontSize: 13 }}>{k}</div>
        <div style={{ borderBottom: "1px solid #e5e5ea", paddingBottom: 4 }}>{v}</div>
      </div>
    ))}
  </div>
);

const PasteKey: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at - 10, at - 4, at + 14, at + 22], [0, 1, 1, 0], clamp);
  return (
    <div style={{ position: "absolute", bottom: 70, right: 120, display: "flex", gap: 12, opacity: o }}>
      <KeyCap label="⌘" pressAt={at} size={74} />
      <KeyCap label="V" pressAt={at} size={74} />
    </div>
  );
};

// MARK: - I. The ordinary world

export const Ordinary: React.FC = () => {
  const frame = useCurrentFrame();
  const titleUp = interpolate(frame, [60, 85], [0, 1], { ...clamp, easing: ease });
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Chapter n="I" title="The ordinary world" />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          transform: `translateY(${-titleUp * 410}px) scale(${1 - titleUp * 0.45})`,
        }}
      >
        <Words text="You do everything with AI." start={8} size={110} />
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingTop: 150 }}>
        <div style={{ ...useEnter(78, 60) }}>
          <Chat
            scrollAt={[205]}
            messages={[
              { from: "me", at: 100, image: <MiniChart />, text: "why is this chart empty after Thursday?" },
              { from: "ai", at: 135, text: "Your date filter excludes the last three days…", typed: true },
              { from: "me", at: 175, image: <MiniForm />, text: "can you fill this out for me" },
              { from: "me", at: 228, image: <EnvShot width={620} />, text: "why won't my app start?" },
            ]}
          />
        </div>
      </AbsoluteFill>
      <PasteKey at={100} />
      <PasteKey at={175} />
      <PasteKey at={228} />
    </AbsoluteFill>
  );
};

// MARK: - II. The call

const Ring: React.FC<{ box: number[]; scale: number; at: number; label: string }> = ({
  box,
  scale,
  at,
  label,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at, fps, config: { damping: 12, stiffness: 140 } });
  const pulse = 1 + Math.sin((frame - at) / 6) * 0.04 * (frame > at ? 1 : 0);
  const [x, y, w, h] = box;
  return (
    <div
      style={{
        position: "absolute",
        left: x * scale - 10,
        top: y * scale - 8,
        width: w * scale + 20,
        height: h * scale + 16,
        borderRadius: 10,
        border: `4px solid ${C.danger}`,
        background: "rgba(255,59,48,0.12)",
        opacity: s,
        transform: `scale(${(0.6 + 0.4 * s) * pulse})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "100%",
          marginLeft: 14,
          transform: "translateY(-50%)",
          fontFamily: FONT,
          fontSize: 20,
          fontWeight: 700,
          color: "white",
          background: C.danger,
          padding: "4px 12px",
          borderRadius: 8,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </div>
    </div>
  );
};

export const Call: React.FC = () => {
  const frame = useCurrentFrame();
  const width = 1500;
  const scale = width / ENV_W;
  const fly = interpolate(frame, [200, 250], [0, 1], { ...clamp, easing: ease });
  const cloud = interpolate(frame, [205, 225], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Chapter n="II" title="The call" />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div
          style={{
            transform: `translateY(${-fly * 520}px) scale(${1 - fly * 0.82})`,
            opacity: 1 - interpolate(frame, [238, 252], [0, 1], clamp),
          }}
        >
          <Window width={width} height={width * (ENV_H / ENV_W) + 44} title=".env.production — zsh" dark>
            <EnvShot width={width} />
            {SECRETS.map((s, i) => (
              <Ring key={i} box={s.box} scale={scale} at={30 + i * 14} label={s.label} />
            ))}
          </Window>
        </div>
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          top: 120,
          left: "50%",
          transform: `translateX(-50%) scale(${0.8 + cloud * 0.2})`,
          opacity: cloud,
          fontSize: 120,
        }}
      >
        ☁️
      </div>
      <Caption start={40} end={190}>
        Every screenshot carries more than you meant to share.
      </Caption>
      <Caption start={250}>And once it's sent, it isn't yours anymore.</Caption>
    </AbsoluteFill>
  );
};

// MARK: - III. The refusal

const Strike: React.FC<{ text: string; at: number; strikeAt: number }> = ({ text, at, strikeAt }) => {
  const frame = useCurrentFrame();
  const w = interpolate(frame, [strikeAt, strikeAt + 10], [0, 100], { ...clamp, easing: ease });
  return (
    <div style={{ position: "relative", ...useEnter(at) }}>
      <span style={{ fontFamily: FONT, fontSize: 84, fontWeight: 700, color: C.ink, letterSpacing: -2 }}>
        {text}
      </span>
      <div
        style={{
          position: "absolute",
          left: -10,
          top: "54%",
          height: 8,
          width: `calc(${w}% + 20px)`,
          background: C.danger,
          borderRadius: 4,
        }}
      />
    </div>
  );
};

export const Refusal: React.FC = () => {
  const out = useExit(118, 10);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Chapter n="III" title="The refusal" />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 18, opacity: out }}>
        <Strike text="Crop every screenshot." at={8} strikeAt={70} />
        <Strike text="Check every pixel." at={24} strikeAt={82} />
        <Strike text="Every single time." at={40} strikeAt={94} />
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26 }}>
        <Words text="Nobody does that." start={128} size={130} />
        <div style={{ ...useEnter(160), fontFamily: FONT, fontSize: 36, color: C.muted }}>
          Deep down, we're all a little bit sloth. 🦥
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// MARK: - IV. The mentor

export const Mentor: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 10, fps, config: { damping: 14, stiffness: 90 } });
  const squint = interpolate(frame, [52, 74], [0, 1], { ...clamp, easing: ease });
  const glow = interpolate(frame, [60, 120], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ background: C.night }}>
      <Chapter n="IV" title="The mentor" dark />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 44 }}>
        <div
          style={{
            width: 280,
            height: 280,
            borderRadius: 64,
            background: "linear-gradient(#41434a, #17171b)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transform: `scale(${pop})`,
            boxShadow: `0 0 ${140 * glow}px rgba(0,113,227,${0.45 * glow}), 0 30px 80px rgba(0,0,0,0.6)`,
          }}
        >
          <Eye size={180} squint={squint} />
        </div>
        <Words text="Meet Squint." start={80} size={120} color="#f5f5f7" />
        <Words
          text="It squints, so you don't have to."
          start={110}
          size={56}
          weight={500}
          color="rgba(245,245,247,0.7)"
          stagger={3}
        />
        <div
          style={{
            ...useEnter(150),
            fontFamily: FONT,
            fontSize: 26,
            letterSpacing: 2,
            color: "rgba(245,245,247,0.5)",
            marginTop: 10,
          }}
        >
          POWERED BY GEMMA 3 · RUNNING ON YOUR MAC
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// MARK: - V. Crossing the threshold

export const Threshold: React.FC = () => {
  const frame = useCurrentFrame();
  const width = 1340;
  const height = width * (ENV_H / ENV_W) + 44;
  const sel = interpolate(frame, [70, 108], [0, 1], { ...clamp, easing: ease });
  const selecting = frame >= 62 && frame < 116;
  const flash = interpolate(frame, [116, 119, 132], [0, 0.85, 0], clamp);
  const timer = interpolate(frame, [116, 160], [0, 1.4], clamp);
  const keys = interpolate(frame, [4, 12, 100, 112], [0, 1, 1, 0], clamp);
  return (
    <AbsoluteFill
      style={{ background: "radial-gradient(circle at 30% 20%, #cfe3ff 0%, #e9e4ff 45%, #f6e8f1 100%)" }}
    >
      <Chapter n="V" title="Crossing the threshold" />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ position: "relative" }}>
          <Window width={width} height={height} title=".env.production — zsh" dark>
            <EnvShot width={width} />
          </Window>
          {selecting && (
            <div
              style={{
                position: "absolute",
                left: -20,
                top: -20,
                width: (width + 40) * sel,
                height: (height + 40) * sel,
                border: "2px dashed rgba(255,255,255,0.95)",
                background: "rgba(255,255,255,0.12)",
                boxShadow: "0 0 0 9999px rgba(0,0,0,0.25)",
              }}
            />
          )}
        </div>
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          bottom: 190,
          width: "100%",
          display: "flex",
          justifyContent: "center",
          gap: 16,
          opacity: keys,
        }}
      >
        <KeyCap label="⌃" pressAt={40} />
        <KeyCap label="⇧" pressAt={42} />
        <KeyCap label="⌘" pressAt={44} />
        <KeyCap label="4" pressAt={46} />
      </div>
      <AbsoluteFill style={{ background: "white", opacity: flash }} />
      <Toast start={150} title="Hid 4 things in your screenshot" subtitle="The redacted copy is on your clipboard" />
      {frame >= 116 && (
        <div
          style={{
            position: "absolute",
            top: 210,
            right: 40,
            fontFamily: MONO,
            fontSize: 26,
            color: C.ink,
            background: "rgba(255,255,255,0.75)",
            padding: "8px 16px",
            borderRadius: 12,
            opacity: interpolate(frame, [116, 124], [0, 1], clamp),
          }}
        >
          ⏱ {timer.toFixed(1)} s
        </div>
      )}
      <Caption start={8} end={110}>
        Take a screenshot, the way you always do.
      </Caption>
      <Caption start={170}>That's it. Your clipboard is already safe.</Caption>
    </AbsoluteFill>
  );
};

// MARK: - VI. The trials (how it works)

const STEPS = [
  { title: "Read", detail: "Apple Vision OCR" },
  { title: "Find", detail: "14 secret patterns" },
  { title: "Judge", detail: "Gemma 3 · 4B, local" },
  { title: "Hide", detail: "irreversibly" },
];

const Verdict: React.FC<{ at: number; text: string; verdict: string; bad: boolean }> = ({
  at,
  text,
  verdict,
  bad,
}) => {
  const frame = useCurrentFrame();
  const shown = text.slice(0, Math.max(0, Math.floor((frame - at) * 1.8)));
  const decided = frame > at + text.length / 1.8 + 8;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, ...useEnter(at, 14) }}>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 24,
          background: "#f0f0f2",
          padding: "10px 16px",
          borderRadius: 10,
          minWidth: 520,
          color: C.ink,
        }}
      >
        {shown}
      </div>
      <div
        style={{
          fontFamily: FONT,
          fontSize: 24,
          fontWeight: 700,
          color: bad ? C.danger : C.safe,
          opacity: decided ? 1 : 0,
          transform: `scale(${decided ? 1 : 0.6})`,
          transition: "none",
        }}
      >
        {verdict}
      </div>
    </div>
  );
};

export const Trials: React.FC = () => {
  const frame = useCurrentFrame();
  const width = 1180;
  const scan = interpolate(frame, [20, 80], [0, 1], { ...clamp, easing: ease });
  const wipe = interpolate(frame, [250, 300], [0, 100], { ...clamp, easing: ease });
  const active = frame < 85 ? 0 : frame < 135 ? 1 : frame < 250 ? 2 : 3;
  const imgH = (width * ENV_H) / ENV_W;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Chapter n="VI" title="The trials" />
      <div style={{ position: "absolute", top: 140, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 18 }}>
        {STEPS.map((s, i) => (
          <div
            key={s.title}
            style={{
              ...useEnter(6 + i * 6, 16),
              width: 300,
              padding: "18px 24px",
              borderRadius: 18,
              fontFamily: FONT,
              background: i === active ? C.ink : "white",
              color: i === active ? "white" : C.ink,
              boxShadow: "0 8px 30px rgba(0,0,0,0.08)",
              transform: `scale(${i === active ? 1.05 : 1})`,
            }}
          >
            <div style={{ fontSize: 34, fontWeight: 700 }}>
              {i + 1}. {s.title}
            </div>
            <div style={{ fontSize: 22, opacity: 0.65 }}>{s.detail}</div>
          </div>
        ))}
      </div>

      <div style={{ position: "absolute", top: 330, left: "50%", transform: "translateX(-50%)" }}>
        <Window width={width} height={imgH + 44} dark>
          <div style={{ position: "relative" }}>
            <EnvShot width={width} />
            <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${100 - wipe}% 0 0)` }}>
              <EnvShot width={width} redacted />
            </div>
            {frame >= 20 && frame < 85 && (
              <div
                style={{
                  position: "absolute",
                  top: scan * imgH,
                  left: 0,
                  right: 0,
                  height: 4,
                  background: C.accent,
                  boxShadow: `0 0 24px 6px ${C.accent}`,
                }}
              />
            )}
            {frame >= 248 && frame < 302 && (
              <div
                style={{
                  position: "absolute",
                  left: `${wipe}%`,
                  top: 0,
                  bottom: 0,
                  width: 4,
                  background: "white",
                  boxShadow: "0 0 24px 6px white",
                }}
              />
            )}
          </div>
        </Window>
      </div>

      {frame >= 140 && frame < 250 && (
        <div
          style={{
            position: "absolute",
            bottom: 170,
            left: "50%",
            transform: "translateX(-50%)",
            background: "white",
            borderRadius: 22,
            padding: "26px 32px",
            boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            opacity: interpolate(frame, [238, 250], [1, 0], clamp),
          }}
        >
          <div style={{ fontFamily: FONT, fontSize: 22, fontWeight: 600, color: C.muted, letterSpacing: 2 }}>
            GEMMA 3, ON YOUR MAC, ASKED: IS THIS PRIVATE?
          </div>
          <Verdict at={148} text={'JWT_ACCESS_SECRET="harbor-Velvet6394!"'} verdict="private → hide" bad />
          <Verdict at={185} text={'API_KEY="<YOUR_API_KEY>"'} verdict="placeholder → keep" bad={false} />
        </div>
      )}

      <Caption start={20} end={130}>
        It reads the screenshot on your Mac…
      </Caption>
      <Caption start={140} end={240} bottom={60}>
        Gemma only sees a few words around each match. Never your image.
      </Caption>
      <Caption start={258}>…and destroys the pixels, so it can't be undone.</Caption>
    </AbsoluteFill>
  );
};

// MARK: - VII. The reward

export const Reward: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Chapter n="VII" title="The reward" />
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingBottom: 90 }}>
      <div style={{ ...useEnter(0, 40) }}>
        <Chat
          height={600}
          messages={[
            { from: "me", at: 26, image: <EnvShot width={660} redacted />, text: "why won't my app start?" },
            {
              from: "ai",
              at: 70,
              typed: true,
              text: "Your env looks fine. The keys are set. But PORT=3000 while NODE_ENV=production; your host expects 8080…",
            },
          ]}
        />
      </div>
    </AbsoluteFill>
    <PasteKey at={26} />
    <Caption start={150} bottom={60}>
      Still useful to your AI. Useless to anyone else.
    </Caption>
  </AbsoluteFill>
);

// MARK: - VIII. The return

const Pledge: React.FC<{ icon: string; text: string; at: number }> = ({ icon, text, at }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 28, ...useEnter(at, 20) }}>
    <span style={{ fontSize: 64, width: 80, textAlign: "center" }}>{icon}</span>
    <span style={{ fontFamily: FONT, fontSize: 68, fontWeight: 700, color: C.ink, letterSpacing: -1.5 }}>
      {text}
    </span>
  </div>
);

export const Return: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const out = useExit(150, 12);
  const end = spring({ frame: frame - 165, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Chapter n="VIII" title="The return" />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "flex-start", paddingLeft: 300, gap: 30, opacity: out }}>
        <Pledge icon="🔒" text="Nothing leaves your Mac." at={10} />
        <Pledge icon="✈️" text="Works offline." at={40} />
        <Pledge icon="🔑" text="No API key to protect your API keys." at={70} />
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26, opacity: end }}>
        <AppIcon size={220} style={{ transform: `scale(${0.85 + 0.15 * end})` }} />
        <Words text="Squint" start={172} size={140} />
        <div style={{ ...useEnter(190), fontFamily: FONT, fontSize: 64, fontWeight: 600, color: C.accent }}>
          mysquint.tech
        </div>
        <div style={{ ...useEnter(205), fontFamily: FONT, fontSize: 28, color: C.muted, letterSpacing: 1 }}>
          Free and open source · Powered by Gemma 3 · Hacktoberfest 2026
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
