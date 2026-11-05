import React from "react";
import { useT, Abs, Pic, Phone, Screen, Sky, Tap, Pulse, Pill, Blue, Orange, OsmCredit, C, FH, FB, wordT, prog, pop, easeIO, easeOut, lerp } from "../lib";
import m from "../../public/ui/s4_map.json";
import log from "../../public/ui/record_log.json";

const W = 1081, H = 880, MX = 420, MY = 22, K = W / 860;
const along = (pts: number[][], f: number) => {
  const seg = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1])); const tot = seg.reduce((a, b) => a + b, 0);
  let d = f * tot; for (let i = 0; i < seg.length; i++) { if (d <= seg[i]) { const q = seg[i] ? d / seg[i] : 0; return [lerp(pts[i][0], pts[i + 1][0], q), lerp(pts[i][1], pts[i + 1][1], q)]; } d -= seg[i]; }
  return pts[pts.length - 1];
};
const Line: React.FC<{ pts: number[][]; c: string; f: number }> = ({ pts, c, f }) => <path d={"M" + pts.map((p) => p.join(" ")).join("L")} fill="none" stroke={c} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - f} />;
const Dot: React.FC<{ p: number[]; c: string; r?: number }> = ({ p, c, r = 13 }) => <circle cx={p[0]} cy={p[1]} r={r} fill={c} stroke="#fff" strokeWidth="5" />;

export const S4 = () => {
  const t = useT(); const log_: any = log;
  const send = wordT("s4", "Send"), friend = wordT("s4", "Your friend"), inn = wordT("s4", "no app"), finds = wordT("s4", "StrollCall"), then = wordT("s4", "then plans");
  const [tapInvite, fly, tapIn] = [send - .1, send + .35, inn - .25];
  const sw = easeIO(prog(t, finds - .3, .45));          // phones out, map in
  const w0 = finds + .3, w1 = then - .35;                // the two walks
  const fa = (log_.pair.a / log_.pair.b), fw = prog(t, w0, w1 - w0);
  const pa = along(m.a, Math.min(1, fw / fa)), pb = along(m.b, fw), meet = m.a[m.a.length - 1];
  const fs = easeIO(prog(t, then + .05, 2.3)), ps = along(m.shared, fs), arrived = t >= w1;
  const fly_ = easeIO(prog(t, fly, .7));
  const ix = log_.invite_btn, ib = log_.im_in_btn;
  const K2 = .98;
  return <Abs w={1920} h={1080}><Sky />
    {sw < 1 && <>
      <Phone x={lerp(170, -520, sw)} y={36} k={K2} color={C.blue}>
        {t < send + .15 ? <Screen src="s4_a_form.png" /> : <>
          <Screen src="s4_a_link.png" />
          <div style={{ position: "absolute", left: 36, top: 247, width: 318, height: 78, backdropFilter: "blur(9px)", background: "rgba(255,250,235,.55)", borderRadius: 14 }} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 702, height: 80, background: "#fff" }} />
        </>}
        <Tap x={ix[0] + ix[2] / 2} y={ix[1] + ix[3] / 2} t={t} at={tapInvite} />
      </Phone>
      <Phone x={lerp(1330, 2010, sw)} y={36} k={K2} color={C.orange}>
        {t < fly + .55 ? <Abs w={390} h={844} style={{ background: "#FFF6E6", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FH, fontWeight: 500, fontSize: 30, color: C.sub }}>your friend’s phone</Abs> : <Screen src={t < friend + .45 ? "s4_b_join.png" : "s4_b_ready.png"} />}
        <Pulse x={ib[0] + ib[2] / 2} y={ib[1] + ib[3] / 2} t={t} a={friend + .45} b={tapIn} r={46} />
        <Tap x={ib[0] + ib[2] / 2} y={ib[1] + ib[3] / 2} t={t} at={tapIn} />
      </Phone>
      <OsmCredit x={820} y={850} o={1 - sw} />
      <Abs x={700} y={150} w={520} style={{ textAlign: "center", opacity: 1 - sw }}>
        <div style={{ fontFamily: FH, fontWeight: 600, fontSize: 56, color: C.ink, lineHeight: 1.1, transform: `scale(${pop(t, .2)})` }}>Walk with<br />a friend</div>
        <div style={{ marginTop: 300, height: 90, transform: `scale(${pop(t, inn)})` }}><Pill bg={C.yellow} size={36}>No app needed</Pill></div>
      </Abs>
      {t > fly && t < fly + .8 && <Abs x={lerp(590, 1230, fly_)} y={430 - Math.sin(fly_ * Math.PI) * 170} style={{ transform: `rotate(${lerp(-8, 8, fly_)}deg)` }}><Pill bg={C.ink} color="#fff" size={34}>🔗 one link</Pill></Abs>}
    </>}
    {sw > 0 && <Abs style={{ opacity: sw }} w={1920} h={1080}>
      <Abs x={MX} y={MY} w={W} h={H} style={{ borderRadius: 32, overflow: "hidden", boxShadow: "0 24px 60px rgba(43,35,64,.3)", border: `6px solid #fff`, boxSizing: "content-box" }}>
        <Pic src="ui/s4_map.png" style={{ width: W, height: H }} />
        <svg viewBox="0 0 860 700" width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
          <Line pts={m.a} c={C.blue} f={Math.min(1, fw / fa)} /><Line pts={m.b} c={C.orange} f={fw} /><Line pts={m.shared} c={C.green} f={fs} />
          {arrived && <circle cx={meet[0]} cy={meet[1]} r={lerp(14, 60, prog(t, w1, .9))} fill="none" stroke={C.yellow} strokeWidth="7" opacity={1 - prog(t, w1, .9)} />}
          {!arrived ? <><Dot p={pa} c={C.blue} /><Dot p={pb} c={C.orange} /></> : fs > 0 ? <Dot p={ps} c={C.green} r={15} /> : <><Dot p={[meet[0] - 9, meet[1]]} c={C.blue} /><Dot p={[meet[0] + 9, meet[1]]} c={C.orange} /></>}
        </svg>
      </Abs>
      <Abs x={70} y={170} w={320} style={{ textAlign: "center" }}><Blue size={130} expr="happy" bounce={fw > 0 && fw < 1 ? Math.abs(Math.sin(t * 6)) * 8 : 0} /><div style={{ marginTop: 16 }}><Pill size={32} bg="#fff">You: 6 min</Pill></div></Abs>
      <Abs x={1530} y={190} w={320} style={{ textAlign: "center" }}><Orange size={130} expr="happy" bounce={fw > 0 && fw < 1 ? Math.abs(Math.sin(t * 6 + 1)) * 8 : 0} /><div style={{ marginTop: 16 }}><Pill size={32} bg="#fff">Friend: 6 min</Pill></div></Abs>
      {t > w1 && <Abs x={60} y={520} w={340} style={{ transform: `scale(${pop(t, w1)})`, textAlign: "center" }}><Pill bg={C.yellow} size={30} style={{ whiteSpace: "normal", lineHeight: 1.15, borderRadius: 30 }}>Meet at<br />{log_.pair.meet}</Pill></Abs>}
      {t > then + .3 && <Abs x={1530} y={520} w={320} style={{ transform: `scale(${pop(t, then + .3)})`, textAlign: "center" }}><Pill bg={C.green} color="#fff" size={30} style={{ whiteSpace: "normal", lineHeight: 1.15, borderRadius: 30 }}>{Math.round(log_.pair.shared)} min together<br />to {log_.pair.dest}</Pill></Abs>}
    </Abs>}
  </Abs>;
};
