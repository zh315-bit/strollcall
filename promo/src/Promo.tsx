import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { useT, prog, C, FB } from "./lib";
import script from "./script.json";
import caps from "./captions.json";
import { S1, S2 } from "./scenes/open";
import { S3 } from "./scenes/solo";
import { S4 } from "./scenes/friend";
import { S5, S6, S7 } from "./scenes/close";

const SCENES: Record<string, React.FC> = { s1: S1, s2: S2, s3: S3, s4: S4, s5: S5, s6: S6, s7: S7 };
const Fade: React.FC<{ children: any }> = ({ children }) => { const t = useT(); return <AbsoluteFill style={{ opacity: prog(t, 0, .35) }}>{children}</AbsoluteFill>; };
const Captions = () => {
  const t = useT(); const c = (caps as any[]).find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  return <div style={{ position: "absolute", left: 0, right: 0, bottom: 36, display: "flex", justifyContent: "center" }}>
    <div style={{ maxWidth: 1400, background: "rgba(43,35,64,.74)", color: "#fff", fontFamily: FB, fontWeight: 800, fontSize: 40, lineHeight: 1.25, padding: "10px 28px", borderRadius: 16, textAlign: "center" }}>{c.text}</div>
  </div>;
};
export const Promo: React.FC<{ captions: boolean }> = ({ captions }) => (
  <AbsoluteFill style={{ background: C.cream }}>
    {script.map((s) => { const Sc = SCENES[s.id]; return <Sequence key={s.id} from={s.start * 30} durationInFrames={(s.end - s.start) * 30} layout="none"><Fade><Sc /></Fade></Sequence>; })}
    {captions && <Captions />}
  </AbsoluteFill>
);
