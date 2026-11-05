import React from "react";
import { useT, Abs, Pic, Orange, Blue, C, FH, FB, pop, prog, wordT, easeOut, Sky } from "../lib";
const blink = (t: number, p = 2.7) => t % p < .12;
export const S1 = () => {
  const t = useT(); const a = wordT("s1", "and then"), same = wordT("s1", "Same");
  const say = pop(t, wordT("s1", "I should") - .1, .35), zoom = 1 + t * .006;
  const breath = Math.sin(t * 2) * .012;
  const droop = prog(t, same, .6);
  const bubbleOut = 1 - prog(t, a + .2, .4);
  return <Abs w={1920} h={1080} style={{ overflow: "hidden" }}>
    <Abs w={1920} h={1080} style={{ transform: `scale(${zoom})`, transformOrigin: "50% 45%" }}>
      <Pic src="art/s2_room.png" style={{ width: 1920, height: 1080 }} />
      <Abs x={1130} y={515}><Orange size={230} expr={t > a ? "sleepy" : "plain"} blink={blink(t)} sy={1 + breath - droop * .05} rot={droop * -4} /></Abs>
    </Abs>
    {say > 0 && <Abs x={500} y={130} style={{ transform: `scale(${say * (bubbleOut > 0 ? 1 : 0)})`, opacity: bubbleOut, transformOrigin: "85% 110%" }}>
      <div style={{ background: "#fff", border: `5px solid ${C.ink}`, borderRadius: 40, padding: "26px 44px", fontFamily: FH, fontWeight: 600, fontSize: 62, color: C.ink, whiteSpace: "nowrap", boxShadow: `10px 12px 0 ${C.yellow}` }}>I should go outside…</div>
    </Abs>}
    {t > same + .1 && <Abs x={1370} y={540} style={{ opacity: prog(t, same + .1, .3), fontFamily: FH, fontWeight: 600, fontSize: 54, color: "#fff", textShadow: `0 3px 10px ${C.ink}` }}>z z z</Abs>}
  </Abs>;
};
export const Logo: React.FC<{ s?: number; t: number; at?: number }> = ({ s = 1, t, at = 0 }) => {
  const a = pop(t, at, .55), b = pop(t, at + .16, .55), w = easeOut(prog(t, at + .3, .4));
  const hop = Math.abs(Math.sin(t * 2.6)) * 8 * s;
  return <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8 * s, height: 250 * s }}>
      <div style={{ transform: `scale(${a})`, transformOrigin: "50% 100%" }}><Blue size={190 * s} expr="happy" bounce={hop} /></div>
      <div style={{ transform: `scale(${b})`, transformOrigin: "50% 100%" }}><Orange size={180 * s} expr="happy" bounce={Math.abs(Math.sin(t * 2.6 + 1.2)) * 8 * s} /></div>
    </div>
    <div style={{ fontFamily: FH, fontWeight: 700, fontSize: 150 * s, color: C.ink, opacity: w, transform: `translateY(${(1 - w) * 30}px)`, lineHeight: 1.1, WebkitTextStroke: "0" }}>StrollCall</div>
  </div>;
};
export const S2 = () => {
  const t = useT(); const less = wordT("s2", "Less"), more = wordT("s2", "More");
  return <Abs w={1920} h={1080}><Sky veil={.5} />
    <Abs x={0} y={190} w={1920} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <Logo t={t} at={.1} />
      <div style={{ display: "flex", gap: 26, marginTop: 26 }}>
        {[["Less planning.", less], ["More walking.", more]].map(([s, at]: any) => <div key={s} style={{ transform: `scale(${pop(t, at, .4)})`, background: C.yellow, color: C.ink, fontFamily: FH, fontWeight: 600, fontSize: 58, padding: "12px 34px", borderRadius: 60 }}>{s}</div>)}
      </div>
    </Abs>
  </Abs>;
};
