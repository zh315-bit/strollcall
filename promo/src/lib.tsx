import React from "react";
import { useCurrentFrame, staticFile, Img } from "remotion";
import "@fontsource/fredoka/500.css"; import "@fontsource/fredoka/600.css"; import "@fontsource/fredoka/700.css";
import "@fontsource/nunito/600.css"; import "@fontsource/nunito/700.css"; import "@fontsource/nunito/800.css";
import script from "./script.json";
import align from "../public/audio/vo_align.json";
import buddy from "./buddySvg.json";

export const C = { ink: "#2B2340", yellow: "#FFD970", blue: "#3B7BEA", orange: "#F08A4B", green: "#22A35A", pink: "#FFB3C1", blush: "#FF9EB0", cream: "#FFF8E8", sub: "#5A5270" };
export const FH = "Fredoka, sans-serif", FB = "Nunito, sans-serif";
export const useT = () => useCurrentFrame() / 30;
export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const prog = (t: number, a: number, d: number) => clamp((t - a) / d);
export const easeOut = (x: number) => 1 - (1 - x) ** 3;
export const easeIO = (x: number) => (x < .5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);
export const back = (x: number) => { const c = 1.9; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2; };
export const pop = (t: number, a: number, d = .45) => back(prog(t, a, d));
export const lerp = (a: number, b: number, x: number) => a + (b - a) * x;

/** Scene-local time a word of the voiceover starts, read from ElevenLabs' character timings. */
export function wordT(id: string, phrase: string, nth = 0) {
  const s: any = script.find((x) => x.id === id); const a: any = (align as any)[id];
  const text = a.chars.join(""); let i = -1;
  for (let k = 0; k <= nth; k++) i = text.indexOf(phrase, i + 1);
  if (i < 0) throw new Error(`no "${phrase}" in ${id}`);
  return s.voAt + a.start[i];
}
export const voEnd = (id: string) => { const s: any = script.find((x) => x.id === id); const a: any = (align as any)[id]; return s.voAt + a.end[a.end.length - 1]; };

export const Abs: React.FC<{ x?: number; y?: number; w?: number; h?: number; style?: React.CSSProperties; children?: any }> = ({ x = 0, y = 0, w, h, style, children }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, ...style }}>{children}</div>
);
export const Pic: React.FC<{ src: string; style?: React.CSSProperties }> = ({ src, style }) => <Img src={staticFile(src)} style={{ display: "block", ...style }} />;

export const Sky: React.FC<{ veil?: number }> = ({ veil = .42 }) => {
  const t = useT();
  return <Abs w={1920} h={1080} style={{ overflow: "hidden", background: "#BFE3FF" }}>
    <Pic src="art/hero-plate.jpg" style={{ position: "absolute", width: 3000, left: -1080, top: -900 - t * 3, filter: "blur(3px)" }} />
    <Abs w={1920} h={1080} style={{ background: `rgba(255,251,240,${veil})` }} />
  </Abs>;
};

export const Blue: React.FC<{ size?: number; expr?: string; blink?: boolean; rot?: number; flip?: boolean; bounce?: number; sy?: number }> = ({ size = 200, expr = "smile", blink, rot = 0, flip, bounce = 0, sy = 1 }) => {
  const eyes = expr === "happy" ? <path d="M-24 -6 q8 -9 16 0 M8 -6 q8 -9 16 0" fill="none" stroke={C.ink} strokeWidth="5" strokeLinecap="round" /> : <>
    <ellipse cx="-15" cy="-4" rx="6" ry={blink ? 1.2 : 7.5} fill={C.ink} /><ellipse cx="15" cy="-4" rx="6" ry={blink ? 1.2 : 7.5} fill={C.ink} />
    {!blink && <><circle cx="-13" cy="-7.5" r="2.4" fill="#fff" /><circle cx="17" cy="-7.5" r="2.4" fill="#fff" /></>}</>;
  return <svg viewBox="-70 -95 140 160" width={size} height={size * 160 / 140} style={{ overflow: "visible", transform: `translateY(${-bounce}px) rotate(${rot}deg) scale(${flip ? -1 : 1},${sy})`, transformOrigin: "50% 90%" }}>
    <ellipse cx="-18" cy="50" rx="13" ry="7" fill="#2E5FC0" stroke={C.ink} strokeWidth="3.5" /><ellipse cx="18" cy="50" rx="13" ry="7" fill="#2E5FC0" stroke={C.ink} strokeWidth="3.5" />
    <path d="M2 -48 q-4 -22 14 -30" fill="none" stroke={C.ink} strokeWidth="5" strokeLinecap="round" /><circle cx="17" cy="-80" r="8" fill={C.pink} stroke={C.ink} strokeWidth="3.5" />
    <ellipse cx="0" cy="0" rx="54" ry="50" fill={C.blue} stroke={C.ink} strokeWidth="5" /><ellipse cx="-22" cy="-24" rx="14" ry="8" fill="#fff" opacity=".28" transform="rotate(-30 -22 -24)" />
    <ellipse cx="-31" cy="10" rx="9" ry="5.5" fill={C.blush} opacity=".85" /><ellipse cx="31" cy="10" rx="9" ry="5.5" fill={C.blush} opacity=".85" />
    {eyes}{expr === "happy" ? <><path d="M-12 12 q12 16 24 0 z" fill={C.ink} /><ellipse cx="0" cy="18" rx="6" ry="2.6" fill="#FF7A93" /></> : <path d="M-10 12 q10 10 20 0" fill="none" stroke={C.ink} strokeWidth="4.5" strokeLinecap="round" />}
  </svg>;
};
export const Orange: React.FC<{ size?: number; expr?: string; blink?: boolean; rot?: number; bounce?: number; sy?: number }> = ({ size = 200, expr = "open", blink, rot = 0, bounce = 0, sy = 1 }) => (
  <svg viewBox="-70 -70 140 135" width={size} height={size * 135 / 140} style={{ overflow: "visible", transform: `translateY(${-bounce}px) rotate(${rot}deg) scaleY(${sy})`, transformOrigin: "50% 90%" }}>
    <ellipse cx="-17" cy="46" rx="12" ry="7" fill="#C9672F" stroke={C.ink} strokeWidth="3.5" /><ellipse cx="17" cy="46" rx="12" ry="7" fill="#C9672F" stroke={C.ink} strokeWidth="3.5" />
    <path d="M-34 -30 l-12 -24 l26 8 z M34 -30 l12 -24 l-26 8 z" fill={C.orange} stroke={C.ink} strokeWidth="5" strokeLinejoin="round" />
    <ellipse cx="0" cy="0" rx="50" ry="46" fill={C.orange} stroke={C.ink} strokeWidth="5" /><ellipse cx="-20" cy="-22" rx="13" ry="7" fill="#fff" opacity=".25" transform="rotate(-30 -20 -22)" />
    <ellipse cx="-30" cy="10" rx="9" ry="5.5" fill={C.yellow} opacity=".9" /><ellipse cx="30" cy="10" rx="9" ry="5.5" fill={C.yellow} opacity=".9" />
    {expr === "happy" ? <path d="M-24 -4 q7 -9 14 0 M10 -4 q7 -9 14 0" fill="none" stroke={C.ink} strokeWidth="5" strokeLinecap="round" /> : <>
      <ellipse cx="-15" cy="-4" rx="6" ry={blink ? 1.2 : 7.5} fill={C.ink} /><ellipse cx="15" cy="-4" rx="6" ry={blink ? 1.2 : 7.5} fill={C.ink} />
      {!blink && <><circle cx="-13" cy="-7.5" r="2.4" fill="#fff" /><circle cx="17" cy="-7.5" r="2.4" fill="#fff" /></>}</>}
    {expr === "sleepy" ? <path d="M-6 14 h12" stroke={C.ink} strokeWidth="4" strokeLinecap="round" /> : <path d="M-10 10 q10 14 20 0 z" fill={C.ink} />}
  </svg>
);

/** The app's own buddy drawing (frontend/js/buddy.js), showing one of its five states. */
export const Buddy: React.FC<{ state: string; size?: number }> = ({ state, size = 120 }) => {
  const html = buddy.svg.replace(/<g data-s="([^"]*)"/g, (m, s) => s.split(" ").includes(state) ? m : `${m} display="none"`).replace(/<path data-s="([^"]*)"/g, (m, s) => s.split(" ").includes(state) ? m : `${m} display="none"`);
  return <div style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: html.replace("<svg ", `<svg width="${size}" height="${size}" style="overflow:visible" `) }} />;
};

export const PHONE_W = 390, PHONE_H = 844;
export const Phone: React.FC<{ x: number; y: number; k?: number; color?: string; children?: any; opacity?: number; scale?: number }> = ({ x, y, k = 1.04, color = C.ink, children, opacity = 1, scale = 1 }) => (
  <Abs x={x} y={y} w={PHONE_W * k + 24} h={PHONE_H * k + 24} style={{ borderRadius: 54, background: color, padding: 12, boxSizing: "border-box", boxShadow: "0 24px 60px rgba(43,35,64,.3)", opacity, transform: `scale(${scale})` }}>
    <div style={{ width: PHONE_W * k, height: PHONE_H * k, borderRadius: 42, overflow: "hidden", position: "relative", background: "#fff" }}>
      <div style={{ width: PHONE_W, height: PHONE_H, transform: `scale(${k})`, transformOrigin: "0 0", position: "absolute" }}>{children}</div>
    </div>
  </Abs>
);
export const Screen: React.FC<{ src: string; style?: React.CSSProperties }> = ({ src, style }) => <Pic src={`ui/${src}`} style={{ position: "absolute", left: 0, top: 0, width: PHONE_W, height: PHONE_H, ...style }} />;

/** A finger tap: a soft dot that presses, then a ring. Coordinates in phone CSS px. */
export const Tap: React.FC<{ x: number; y: number; t: number; at: number }> = ({ x, y, t, at }) => {
  if (t < at - .5 || t > at + .8) return null;
  const inn = easeOut(prog(t, at - .5, .4)), ring = prog(t, at, .55);
  return <>
    <div style={{ position: "absolute", left: x - 22, top: y - 22, width: 44, height: 44, borderRadius: 22, background: "rgba(43,35,64,.32)", border: "3px solid #fff", opacity: inn * (1 - prog(t, at + .3, .4)), transform: `scale(${t > at ? .86 : 1.15 - .15 * inn})` }} />
    {t >= at && <div style={{ position: "absolute", left: x - 40, top: y - 40, width: 80, height: 80, borderRadius: 40, border: `5px solid ${C.yellow}`, opacity: 1 - ring, transform: `scale(${.5 + ring})` }} />}
  </>;
};
export const Pulse: React.FC<{ x: number; y: number; t: number; a: number; b: number; r?: number }> = ({ x, y, t, a, b, r = 44 }) => {
  if (t < a || t > b) return null;
  return <>{[0, .5].map((o) => { const p = ((t - a + o) % 1); return <div key={o} style={{ position: "absolute", left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: r, border: `5px solid ${C.yellow}`, opacity: (1 - p) * .9, transform: `scale(${.7 + p * .8})` }} />; })}</>;
};
export const Pill: React.FC<{ children: any; bg?: string; color?: string; size?: number; style?: React.CSSProperties }> = ({ children, bg = "#fff", color = C.ink, size = 30, style }) => (
  <div style={{ display: "inline-block", background: bg, color, fontFamily: FH, fontWeight: 600, fontSize: size, padding: `${size * .36}px ${size * .8}px`, borderRadius: size * 2, boxShadow: "0 8px 22px rgba(43,35,64,.16)", whiteSpace: "nowrap", ...style }}>{children}</div>
);
export const OsmCredit: React.FC<{ x: number; y: number; o?: number }> = ({ x, y, o = 1 }) => (
  <Abs x={x} y={y} style={{ fontFamily: FB, fontWeight: 700, fontSize: 19, color: C.ink, background: "rgba(255,255,255,.85)", padding: "4px 12px", borderRadius: 10, opacity: o, whiteSpace: "nowrap" }}>© OpenStreetMap contributors</Abs>
);
export const Step: React.FC<{ n: number; title: string; sub?: any; on: number; done?: boolean }> = ({ n, title, sub, on, done }) => (
  <div style={{ display: "flex", gap: 24, alignItems: "flex-start", opacity: lerp(.5, 1, on), transform: `scale(${lerp(.94, 1, on)})`, transformOrigin: "0 50%", marginBottom: 34 }}>
    <div style={{ flex: "0 0 72px", height: 72, borderRadius: 36, background: on > .5 || done ? C.yellow : "#fff", color: C.ink, fontFamily: FH, fontWeight: 700, fontSize: 40, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 6px 16px rgba(43,35,64,.18)" }}>{n}</div>
    <div>
      <div style={{ fontFamily: FH, fontWeight: 600, fontSize: 46, color: C.ink, lineHeight: 1.12, paddingTop: 8 }}>{title}</div>
      {sub && on > .02 && <div style={{ fontFamily: FB, fontWeight: 700, fontSize: 30, color: C.sub, marginTop: 8, opacity: on, lineHeight: 1.25 }}>{sub}</div>}
    </div>
  </div>
);
