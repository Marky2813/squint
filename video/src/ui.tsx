import React from "react";
import {
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const FONT =
  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif';
export const MONO = '"SF Mono", Menlo, monospace';
export const C = {
  bg: "#f5f5f7",
  ink: "#1d1d1f",
  muted: "#6e6e73",
  accent: "#0071e3",
  danger: "#ff3b30",
  safe: "#34c759",
  night: "#0b0b0c",
};

/** Opacity + rise + unblur, starting at `start` frames. */
export const useEnter = (start: number, distance = 24) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - start, fps, config: { damping: 200 }, durationInFrames: 22 });
  return {
    opacity: s,
    transform: `translateY(${(1 - s) * distance}px)`,
    filter: `blur(${(1 - s) * 6}px)`,
  } as React.CSSProperties;
};

/** Fade out between two frames. */
export const useExit = (start: number, length = 12) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [start, start + length], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

/** Words rise in one after another, like Apple keynote titles. */
export const Words: React.FC<{
  text: string;
  start?: number;
  size?: number;
  weight?: number;
  color?: string;
  stagger?: number;
  style?: React.CSSProperties;
}> = ({ text, start = 0, size = 96, weight = 700, color = C.ink, stagger = 4, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        fontFamily: FONT,
        fontSize: size,
        fontWeight: weight,
        color,
        letterSpacing: -size * 0.025,
        lineHeight: 1.08,
        textAlign: "center",
        ...style,
      }}
    >
      {text.split(" ").map((word, i) => {
        const s = spring({
          frame: frame - start - i * stagger,
          fps,
          config: { damping: 200 },
          durationInFrames: 20,
        });
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              marginRight: size * 0.26,
              opacity: s,
              transform: `translateY(${(1 - s) * size * 0.35}px)`,
              filter: `blur(${(1 - s) * 8}px)`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Small "IV · THE MENTOR" label: the hero's journey, chapter by chapter. */
export const Chapter: React.FC<{ n: string; title: string; dark?: boolean }> = ({
  n,
  title,
  dark,
}) => {
  const style = useEnter(4, 10);
  return (
    <div
      style={{
        position: "absolute",
        top: 64,
        left: 80,
        display: "flex",
        alignItems: "center",
        gap: 14,
        fontFamily: FONT,
        fontSize: 20,
        fontWeight: 600,
        letterSpacing: 3,
        color: dark ? "rgba(255,255,255,0.55)" : C.muted,
        ...style,
      }}
    >
      <span>{n}</span>
      <span style={{ width: 28, height: 1.5, background: "currentColor", opacity: 0.6 }} />
      <span>{title.toUpperCase()}</span>
    </div>
  );
};

export const Caption: React.FC<{
  children: React.ReactNode;
  start: number;
  end?: number;
  dark?: boolean;
  bottom?: number;
}> = ({ children, start, end, dark, bottom = 90 }) => {
  const enter = useEnter(start, 16);
  const exit = useExit(end ?? 100000);
  return (
    <div
      style={{
        position: "absolute",
        bottom,
        left: 0,
        right: 0,
        textAlign: "center",
        fontFamily: FONT,
        fontSize: 44,
        fontWeight: 600,
        letterSpacing: -0.8,
        color: dark ? "#f5f5f7" : C.ink,
        ...enter,
        opacity: (enter.opacity as number) * exit,
      }}
    >
      {children}
    </div>
  );
};

/** A macOS window: traffic lights, title bar, soft shadow. */
export const Window: React.FC<{
  width: number;
  height: number;
  title?: string;
  dark?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ width, height, title, dark, children, style }) => (
  <div
    style={{
      width,
      height,
      borderRadius: 16,
      overflow: "hidden",
      background: dark ? "#1e1e1e" : "#ffffff",
      boxShadow: "0 40px 100px rgba(0,0,0,0.28), 0 0 0 1px rgba(0,0,0,0.08)",
      display: "flex",
      flexDirection: "column",
      ...style,
    }}
  >
    <div
      style={{
        height: 44,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        padding: "0 18px",
        gap: 9,
        background: dark ? "#2a2a2a" : "#f6f6f6",
        borderBottom: `1px solid ${dark ? "#000" : "#e5e5e5"}`,
        position: "relative",
      }}
    >
      {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
        <span key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />
      ))}
      {title && (
        <span
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            textAlign: "center",
            fontFamily: FONT,
            fontSize: 15,
            fontWeight: 600,
            color: dark ? "#bbb" : "#555",
            pointerEvents: "none",
          }}
        >
          {title}
        </span>
      )}
    </div>
    <div style={{ flex: 1, position: "relative" }}>{children}</div>
  </div>
);

export const KeyCap: React.FC<{ label: string; pressAt: number; size?: number }> = ({
  label,
  pressAt,
  size = 92,
}) => {
  const frame = useCurrentFrame();
  const down = interpolate(frame, [pressAt, pressAt + 3, pressAt + 9], [0, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        minWidth: size,
        height: size,
        padding: "0 22px",
        borderRadius: 18,
        background: "linear-gradient(#ffffff, #ececee)",
        boxShadow: `0 ${6 - down * 4}px 0 #c7c7cc, 0 ${12 - down * 8}px 24px rgba(0,0,0,${0.16 - down * 0.08})`,
        transform: `translateY(${down * 4}px)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: FONT,
        fontSize: size * 0.42,
        fontWeight: 500,
        color: C.ink,
      }}
    >
      {label}
    </div>
  );
};

/** The narrowed-eye glyph; `squint` 0 = open eye, 1 = Squint's narrowed eye. */
export const Eye: React.FC<{ size: number; squint: number; color?: string; stroke?: number }> = ({
  size,
  squint,
  color = "white",
  stroke = 0.045,
}) => {
  const up = 0.06 + 0.2 * squint;
  const low = 0.94 - 0.2 * squint;
  const d = `M 0.04 0.5 Q 0.5 ${up} 0.96 0.5 Q 0.5 ${low} 0.04 0.5 Z`;
  const id = `almond-${Math.round(squint * 1000)}`;
  return (
    <svg width={size} height={size} viewBox="0 0 1 1">
      <defs>
        <clipPath id={id}>
          <path d={d} />
        </clipPath>
      </defs>
      <circle cx={0.5} cy={0.5} r={0.155} fill={color} clipPath={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth={stroke} strokeLinejoin="round" />
    </svg>
  );
};

export const AppIcon: React.FC<{ size: number; style?: React.CSSProperties }> = ({ size, style }) => (
  <Img src={staticFile("icon.png")} style={{ width: size, height: size, ...style }} />
);

/** Squint's banner, matching the app (scaled up for video). */
export const Toast: React.FC<{ start: number; scale?: number; title: string; subtitle: string }> = ({
  start,
  scale = 1.7,
  title,
  subtitle,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - start, fps, config: { damping: 18, stiffness: 120 } });
  return (
    <div
      style={{
        position: "absolute",
        top: 36,
        right: 36,
        width: 356 * scale,
        transformOrigin: "top right",
        transform: `translateX(${(1 - s) * 120}px)`,
        opacity: Math.min(1, s * 1.4),
        borderRadius: 22 * scale,
        padding: `${12 * scale}px ${14 * scale}px`,
        background: "rgba(246,246,248,0.86)",
        backdropFilter: "blur(30px) saturate(1.6)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.25), 0 0 0 0.5px rgba(0,0,0,0.15)",
        display: "flex",
        alignItems: "center",
        gap: 10 * scale,
        fontFamily: FONT,
      }}
    >
      <AppIcon size={40 * scale} />
      <div style={{ flex: 1, lineHeight: 1.3 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 * scale }}>
          <b>Squint</b>
          <span style={{ color: C.muted, fontSize: 11 * scale }}>now</span>
        </div>
        <div style={{ fontSize: 13 * scale, color: C.ink }}>{title}</div>
        <div style={{ fontSize: 13 * scale, color: C.muted }}>{subtitle}</div>
      </div>
    </div>
  );
};

export const ease = Easing.bezier(0.25, 0.1, 0.25, 1);
