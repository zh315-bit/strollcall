import React from "react";
import { OffthreadVideo, staticFile } from "remotion";
import { useT, Abs, Pic, Phone, Sky, Pulse, Pill, Buddy, Blue, Orange, OsmCredit, C, FH, FB, wordT, voEnd, prog, pop, Tap } from "../lib";
import ev from "../../public/ui/s5_buddy.json";
import log from "../../public/ui/record_log.json";
import cfg from "../config.json";
import { Logo } from "./open";

export const S5 = () => {
  const t = useT(); const e: any = ev.events; const OFF = .3;
  const hold = e[0].t - OFF, go = e[1].t - OFF, reply = e[2].t - OFF;
  const mic = (log as any).buddy.mic;
  const state = t < hold ? "walking" : t < go ? "listening" : t < reply ? "thinking" : t < 10.9 ? "speaking" : "arrived";
  const STATES = ["walking", "listening", "thinking", "speaking", "arrived"];
  const asks = [["a coffee stop", wordT("s5", "a coffee")], ["a shorter route", wordT("s5", "a shorter")], ["what’s nearby", wordT("s5", "what")]] as any[];
  return <Abs w={1920} h={1080}><Sky />
    <Phone x={210} y={22}>
      <OffthreadVideo src={staticFile("ui/s5_buddy.mp4")} trimBefore={Math.round(OFF * 30)} muted style={{ position: "absolute", left: 0, top: 0, width: 390, height: 844 }} />
      <Pulse x={mic[0]} y={mic[1]} t={t} a={hold} b={go} r={50} />
      {t > hold - .2 && t < go + .1 && <div style={{ position: "absolute", left: mic[0] - 24, top: mic[1] - 24, width: 48, height: 48, borderRadius: 24, background: "rgba(43,35,64,.3)", border: "3px solid #fff" }} />}
    </Phone>
    <OsmCredit x={660} y={886} />
    <Abs x={760} y={70} w={1060}>
      <div style={{ fontFamily: FH, fontWeight: 600, fontSize: 60, color: C.ink }}>Your walking buddy</div>
      <div style={{ display: "flex", alignItems: "center", gap: 36, marginTop: 30, height: 230 }}>
        <Buddy state={state} size={210} />
        {t > hold && t < reply && <div style={{ background: "#fff", borderRadius: 30, padding: "20px 30px", fontFamily: FB, fontWeight: 800, fontSize: 36, color: C.ink, transform: `scale(${pop(t, hold)})`, boxShadow: "0 8px 22px rgba(43,35,64,.16)" }}>“Can we stop for a coffee?”</div>}
        {t >= reply && <div style={{ background: C.yellow, borderRadius: 30, padding: "20px 30px", fontFamily: FB, fontWeight: 800, fontSize: 36, color: C.ink, transform: `scale(${pop(t, reply)})`, boxShadow: "0 8px 22px rgba(43,35,64,.16)" }}>Coffee stop added.<br />It’s on your way.</div>}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 40, flexWrap: "wrap", height: 84 }}>{asks.map(([s, at]) => t >= at && <div key={s} style={{ transform: `scale(${pop(t, at, .35)})` }}><Pill size={34}>{s}</Pill></div>)}</div>
      <div style={{ display: "flex", gap: 12, marginTop: 44 }}>{STATES.map((s) => <div key={s} style={{ width: 192, textAlign: "center", padding: "14px 0 10px", borderRadius: 24, background: s === state ? "#fff" : "rgba(255,255,255,.45)", boxShadow: s === state ? `0 0 0 5px ${C.yellow}` : "none" }}>
        <div style={{ display: "flex", justifyContent: "center" }}><Buddy state={s} size={92} /></div>
        <div style={{ fontFamily: FB, fontWeight: 800, fontSize: 25, color: C.ink, marginTop: 4 }}>{s}</div></div>)}</div>
    </Abs>
  </Abs>;
};
const Card: React.FC<{ at: number; t: number; title: any; children: any }> = ({ at, t, title, children }) => (
  <div style={{ width: 530, height: 560, background: "#fff", borderRadius: 44, boxShadow: "0 18px 46px rgba(43,35,64,.2)", transform: `scale(${pop(t, at)}) translateY(${Math.sin(t * 2 + at) * 4}px)`, display: "flex", flexDirection: "column", alignItems: "center", padding: 30, boxSizing: "border-box" }}>
    <div style={{ height: 290, display: "flex", alignItems: "flex-end", justifyContent: "center", position: "relative", width: "100%" }}>{children}</div>
    <div style={{ fontFamily: FH, fontWeight: 600, fontSize: 42, color: C.ink, textAlign: "center", lineHeight: 1.15, marginTop: 26 }}>{title}</div>
  </div>
);
export const S6 = () => {
  const t = useT(); const a = wordT("s6", "homebodies"), b = wordT("s6", "busy"), c = wordT("s6", "friends");
  const hop = (p: number) => Math.abs(Math.sin(t * 3 + p)) * 9;
  return <Abs w={1920} h={1080}><Sky />
    <Abs x={0} y={200} w={1920} style={{ display: "flex", justifyContent: "center", gap: 44 }}>
      <Card at={a - .1} t={t} title="Homebodies">
        <div style={{ position: "absolute", bottom: 0, width: 340, height: 110, borderRadius: "40px 40px 16px 16px", background: "#B7A6D9", border: `5px solid ${C.ink}` }} />
        <div style={{ position: "relative", marginBottom: 58 }}><Orange size={170} expr="happy" bounce={hop(0) * .5} /></div>
      </Card>
      <Card at={b - .1} t={t} title="Busy students between classes">
        <div style={{ position: "absolute", left: 60, bottom: 30, width: 92, height: 120, background: C.yellow, border: `5px solid ${C.ink}`, borderRadius: 12 }}><div style={{ margin: "26px 14px", height: 8, background: C.ink, borderRadius: 4, boxShadow: `0 22px 0 ${C.ink}` }} /></div>
        <Blue size={175} expr="happy" bounce={hop(1)} />
        <svg width="96" height="96" viewBox="0 0 96 96" style={{ position: "absolute", right: 56, bottom: 150 }}><circle cx="48" cy="48" r="42" fill="#fff" stroke={C.ink} strokeWidth="6" /><path d="M48 24v26l17 11" fill="none" stroke={C.ink} strokeWidth="6" strokeLinecap="round" /></svg>
      </Card>
      <Card at={c - .1} t={t} title={<>Friends who keep saying<br />“we should hang out”</>}>
        <Blue size={150} expr="happy" bounce={hop(2)} /><Orange size={145} expr="happy" bounce={hop(3)} />
      </Card>
    </Abs>
  </Abs>;
};
export const S7 = () => {
  const t = useT(); const placeholder = cfg.shortLink === "[SHORT_LINK]";
  const q = pop(t, .5), last = voEnd("s7");
  return <Abs w={1920} h={1080}><Sky veil={.55} />
    <Abs x={250} y={170} w={540} h={690} style={{ background: "#fff", borderRadius: 48, boxShadow: "0 18px 46px rgba(43,35,64,.22)", transform: `scale(${q})`, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 40, boxSizing: "border-box" }}>
      <div style={{ position: "relative", width: 440, height: 440 }}>
        <Pic src="qr.png" style={{ width: 440, height: 440 }} />
        {placeholder && <div style={{ position: "absolute", left: 90, top: 190, width: 260, textAlign: "center", background: C.yellow, fontFamily: FB, fontWeight: 800, fontSize: 26, color: C.ink, padding: "8px 0", borderRadius: 12 }}>QR placeholder</div>}
      </div>
      <div style={{ fontFamily: FH, fontWeight: 600, fontSize: 46, color: C.ink, marginTop: 34 }}>{cfg.shortLink}</div>
      <div style={{ fontFamily: FB, fontWeight: 700, fontSize: 30, color: C.sub, marginTop: 8 }}>Scan to start</div>
    </Abs>
    <Abs x={860} y={190} w={860} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <Logo t={t} at={.2} s={.95} />
      <div style={{ marginTop: 24, background: C.yellow, color: C.ink, fontFamily: FH, fontWeight: 600, fontSize: 52, padding: "10px 34px", borderRadius: 60, transform: `scale(${pop(t, .9)})` }}>Less planning. More walking.</div>
      <div style={{ marginTop: 44, fontFamily: FB, fontWeight: 700, fontSize: 26, color: C.ink, opacity: prog(t, 1.2, .5) }}>A student project, not affiliated with NYU.</div>
    </Abs>
  </Abs>;
};
