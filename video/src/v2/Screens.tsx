// The "screenshots" people paste into AI, drawn at 1600x1000. Every name, number and key
// here is fake. <Leak> marks the private bits so the twist can ring them in red.
import React, { createContext, useContext } from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, MONO } from "../ui";

export const SHOT_W = 1600;
export const SHOT_H = 1000;

export const PHONE = "+1 415 555 0142";
export const EMAIL = "aiko.fakeworth@outlook.com";

type Reveal = { at: number | null; ring: number };
const RevealContext = createContext<Reveal>({ at: null, ring: 6 });

/** Inside it, every <Leak> lights up from frame `at` (null: stays hidden). */
export const Reveal: React.FC<{ at: number | null; ring?: number; children: React.ReactNode }> = ({
  at,
  ring = 6,
  children,
}) => <RevealContext.Provider value={{ at, ring }}>{children}</RevealContext.Provider>;

export const Leak: React.FC<{ children: React.ReactNode; order?: number; style?: React.CSSProperties }> = ({
  children,
  order = 0,
  style,
}) => {
  const { at, ring } = useContext(RevealContext);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = at === null ? 0 : spring({ frame: frame - at - order * 5, fps, config: { damping: 12, stiffness: 160 } });
  return (
    <span
      style={{
        borderRadius: 8,
        boxShadow: `0 0 0 ${ring * s}px ${C.danger}, 0 0 ${ring * 6 * s}px rgba(255,59,48,${0.55 * s})`,
        background: `rgba(255,59,48,${0.16 * s})`,
        ...style,
      }}
    >
      {children}
    </span>
  );
};

const Shot: React.FC<{ bg: string; children: React.ReactNode }> = ({ bg, children }) => (
  <div style={{ width: SHOT_W, height: SHOT_H, background: bg, position: "relative", overflow: "hidden", fontFamily: FONT }}>
    {children}
  </div>
);

/** A macOS notification banner, as it appears inside a screenshot. */
export const Notification: React.FC<{ app: string; title: string; body: React.ReactNode; style?: React.CSSProperties }> = ({
  app,
  title,
  body,
  style,
}) => (
  <div
    style={{
      position: "absolute",
      top: 22,
      right: 22,
      width: 520,
      borderRadius: 26,
      padding: "18px 22px",
      background: "rgba(244,244,246,0.96)",
      boxShadow: "0 16px 40px rgba(0,0,0,0.22), 0 0 0 1px rgba(0,0,0,0.08)",
      display: "flex",
      gap: 16,
      alignItems: "center",
      fontFamily: FONT,
      ...style,
    }}
  >
    <div style={{ width: 52, height: 52, borderRadius: 13, background: "linear-gradient(#5ff777, #0fbf3d)", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: 30 }}>
      💬
    </div>
    <div style={{ fontSize: 22, lineHeight: 1.3, color: C.ink, flex: 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <b>{title}</b>
        <span style={{ color: C.muted, fontSize: 18 }}>now</span>
      </div>
      <div>{body}</div>
      <div style={{ display: "none" }}>{app}</div>
    </div>
  </div>
);

/** Shot 1: the CSS bug (a checkout button sitting on top of the order summary). */
export const BugShot: React.FC<{ notification?: boolean; notificationAt?: number }> = ({ notification }) => (
  <Shot bg="#ffffff">
    <div style={{ height: 76, background: "#ececef", display: "flex", alignItems: "center", gap: 14, padding: "0 26px", borderBottom: "1px solid #ddd" }}>
      {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
        <span key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c }} />
      ))}
      <div style={{ marginLeft: 26, flex: 1, height: 44, borderRadius: 12, background: "white", display: "flex", alignItems: "center", padding: "0 20px", fontSize: 22, color: "#444" }}>
        🔒 cartly.test/checkout
      </div>
    </div>
    <div style={{ padding: "60px 120px", color: C.ink }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontSize: 56, fontWeight: 700, letterSpacing: -1 }}>Checkout</div>
        <div style={{ fontSize: 24, color: C.muted }}>
          Signed in as <Leak order={0}>{EMAIL}</Leak>
        </div>
      </div>
      <div style={{ marginTop: 40, display: "flex", gap: 60 }}>
        <div style={{ flex: 1.3, fontSize: 26, color: C.muted, lineHeight: 2.1 }}>
          <div>Shipping · Standard (3–5 days)</div>
          <div>Payment · Card ending 4242</div>
          <div>Promo code · none</div>
        </div>
        <div style={{ flex: 1, position: "relative", background: "#f5f5f7", borderRadius: 20, padding: 36, height: 420 }}>
          <div style={{ fontSize: 30, fontWeight: 600 }}>Order summary</div>
          <div style={{ fontSize: 24, color: C.muted, marginTop: 20, lineHeight: 2 }}>
            <div>Wireless keyboard · $39.00</div>
            <div>Shipping · $10.00</div>
            <div style={{ color: C.ink, fontWeight: 600 }}>Total · $49.00</div>
          </div>
          {/* the bug: an absolutely positioned button that escaped its container */}
          <div style={{ position: "absolute", left: -90, top: 150, width: 420, height: 92, borderRadius: 18, background: C.accent, color: "white", fontSize: 30, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", transform: "rotate(-4deg)", boxShadow: "0 10px 30px rgba(0,113,227,0.35)" }}>
            Pay $49.00
          </div>
        </div>
      </div>
    </div>
    {notification && (
      <Notification
        app="Messages"
        title="Priya"
        body={
          <>
            call me back on <Leak order={1}>{PHONE}</Leak>
          </>
        }
      />
    )}
  </Shot>
);

/** Shot 2: an editor, with a text message arriving in the corner. */
export const EditorShot: React.FC = () => (
  <Shot bg="#1e1e1e">
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ width: 260, background: "#252526", padding: 28, fontFamily: MONO, fontSize: 20, color: "#9d9d9d", lineHeight: 2 }}>
        <div>▾ src</div>
        <div>&nbsp;&nbsp;Checkout.tsx</div>
        <div>&nbsp;&nbsp;Summary.tsx</div>
        <div>&nbsp;&nbsp;styles.css</div>
      </div>
      <div style={{ flex: 1, padding: "70px 50px", fontFamily: MONO, fontSize: 26, lineHeight: 1.9, color: "#d4d4d4" }}>
        <div><span style={{ color: "#d7ba7d" }}>.pay-button</span> {"{"}</div>
        <div>&nbsp;&nbsp;<span style={{ color: "#9cdcfe" }}>position</span>: <span style={{ color: "#ce9178" }}>absolute</span>;</div>
        <div>&nbsp;&nbsp;<span style={{ color: "#9cdcfe" }}>left</span>: <span style={{ color: "#b5cea8" }}>-90px</span>;</div>
        <div>&nbsp;&nbsp;<span style={{ color: "#9cdcfe" }}>transform</span>: rotate(<span style={{ color: "#b5cea8" }}>-4deg</span>);</div>
        <div>{"}"}</div>
        <div style={{ color: "#6a9955", marginTop: 20 }}>{"// why does this escape the card??"}</div>
      </div>
    </div>
    <Notification
      app="Messages"
      title="Priya"
      body={
        <>
          is this still your number? <Leak>{PHONE}</Leak>
        </>
      }
    />
  </Shot>
);

/** Shot 3: an analytics dashboard, signed in, email in the corner. */
export const DashboardShot: React.FC = () => (
  <Shot bg="#f7f7f9">
    <div style={{ height: 90, background: "white", borderBottom: "1px solid #e5e5ea", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 48px" }}>
      <div style={{ fontSize: 30, fontWeight: 700, color: C.ink }}>Pulse Analytics</div>
      <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 22, color: C.muted }}>
        <Leak>{EMAIL}</Leak>
        <span style={{ width: 44, height: 44, borderRadius: 22, background: "#ff9f0a", display: "inline-block" }} />
      </div>
    </div>
    <div style={{ padding: 48, display: "flex", gap: 30 }}>
      {[["Visitors", "12,480"], ["Signups", "342"], ["Revenue", "$8,210"]].map(([k, v]) => (
        <div key={k} style={{ flex: 1, background: "white", borderRadius: 22, padding: 30, boxShadow: "0 0 0 1px #e5e5ea" }}>
          <div style={{ fontSize: 22, color: C.muted }}>{k}</div>
          <div style={{ fontSize: 50, fontWeight: 700, color: C.ink }}>{v}</div>
        </div>
      ))}
    </div>
    <div style={{ margin: "0 48px", height: 520, background: "white", borderRadius: 22, boxShadow: "0 0 0 1px #e5e5ea", display: "flex", alignItems: "flex-end", gap: 22, padding: 40 }}>
      {[0.4, 0.55, 0.5, 0.72, 0.66, 0.9, 0.04, 0.04, 0.04].map((h, i) => (
        <div key={i} style={{ flex: 1, height: `${h * 100}%`, background: h > 0.1 ? "#5e5ce6" : "#e5e5ea", borderRadius: 10 }} />
      ))}
    </div>
  </Shot>
);

export const TerminalShot: React.FC = () => (
  <Shot bg="#111214">
    <div style={{ padding: 70, fontFamily: MONO, fontSize: 32, lineHeight: 1.9, color: "#e6e6e6" }}>
      <div><span style={{ color: "#34c759" }}>~/app $</span> export OPENAI_API_KEY=<Leak>sk-proj-FAKE9qX2mVb7Lp</Leak></div>
      <div><span style={{ color: "#34c759" }}>~/app $</span> npm run dev</div>
      <div style={{ color: "#ff453a" }}>Error: connect ECONNREFUSED 127.0.0.1:5432</div>
      <div style={{ color: "#8e8e93" }}>    at TCPConnectWrap.afterConnect</div>
    </div>
  </Shot>
);

export const ChatDMShot: React.FC = () => (
  <Shot bg="#ffffff">
    <div style={{ padding: 70, fontSize: 32, lineHeight: 1.6, color: C.ink }}>
      <div style={{ fontWeight: 700 }}>Marco <span style={{ color: C.muted, fontWeight: 400, fontSize: 24 }}>10:42 AM</span></div>
      <div>can you check staging? password is <Leak>maple-Rocket4471!</Leak></div>
      <div style={{ fontWeight: 700, marginTop: 40 }}>You <span style={{ color: C.muted, fontWeight: 400, fontSize: 24 }}>10:43 AM</span></div>
      <div>on it, the login page looks broken though</div>
    </div>
  </Shot>
);

export const InvoiceShot: React.FC = () => (
  <Shot bg="#fbfbfd">
    <div style={{ padding: 80, color: C.ink }}>
      <div style={{ fontSize: 54, fontWeight: 700 }}>Invoice #2291</div>
      <div style={{ fontSize: 30, color: C.muted, marginTop: 30, lineHeight: 2 }}>
        <div>Billed to · Aiko Fakeworth</div>
        <div>Card · <Leak>4185 1822 2254 1893</Leak></div>
        <div>Amount due · $1,240.00</div>
      </div>
    </div>
  </Shot>
);

export const EnvShot: React.FC = () => (
  <Shot bg="#1e1e1e">
    <div style={{ padding: 70, fontFamily: MONO, fontSize: 32, lineHeight: 1.9, color: "#d4d4d4" }}>
      <div style={{ color: "#6a9955" }}># .env.production</div>
      <div><span style={{ color: "#569cd6" }}>STRIPE_SECRET_KEY</span>=<Leak>sk_live_FAKEtzxJ3r3JzdR6c</Leak></div>
      <div><span style={{ color: "#569cd6" }}>DATABASE_URL</span>=postgres://app:<Leak>harbor-Velvet6394!</Leak>@db</div>
      <div><span style={{ color: "#569cd6" }}>PORT</span>=3000</div>
    </div>
  </Shot>
);

/** All the screenshots of the hook, in paste order. */
export const HOOK_SHOTS = [BugShot, EditorShot, DashboardShot, TerminalShot, ChatDMShot, InvoiceShot, EnvShot];
