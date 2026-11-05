import React from "react";
import { OffthreadVideo, Sequence, staticFile } from "remotion";
import { useT, Abs, Phone, Screen, Sky, Step, Tap, Pulse, Pill, OsmCredit, Blue, C, FH, wordT, prog, pop, easeIO, clamp } from "../lib";
import plan from "../../public/ui/s3_plan.json";

const Clip: React.FC<{ src: string; from: number; }> = ({ src, from }) => (
  <Sequence from={Math.round(from * 30)} layout="none"><OffthreadVideo src={staticFile(`ui/${src}`)} muted style={{ position: "absolute", left: 0, top: 0, width: 390, height: 844 }} /></Sequence>
);
export const S3 = () => {
  const t = useT();
  const say = wordT("s3", "just say"), tPlan = wordT("s3", "StrollCall"), tOut = wordT("s3", "and you");
  const clipAt = tPlan - 7.2;           // the clip runs at real speed; its transcript lands just before step 2
  const startAt = tOut - .3;            // the real tap on Start walking lands just after "out the door"
  const showClip = t >= clipAt && t < tPlan, showPlan = t >= tPlan && t < startAt, showStart = t >= startAt;
  const draw = easeIO(prog(t, tPlan + .2, 1.9));
  const r = (plan as any).routes[0]; const d = "M" + r.pts.map((p: number[]) => p.join(" ")).join("L");
  const on1 = t < tPlan ? 1 : 0, on2 = t >= tPlan && t < startAt + .2 ? 1 : 0, on3 = t >= startAt + .2 ? 1 : 0;
  const walk = prog(t, startAt + 1.5, 2.4);
  const zoom = 1 + .16 * easeIO(prog(t, .4, 2)) * (1 - easeIO(prog(t, tPlan - .5, .5)));   // onto the wish box, then back
  const wish = "“20 minutes, quiet streets, coffee at the end”", tw = wordT("s3", "twenty");
  const typed = wish.slice(0, Math.round(wish.length * prog(t, tw, 2.6)));
  return <Abs w={1920} h={1080}><Sky />
    <Phone x={210} y={22}>
      <div style={{ position: "absolute", left: 0, top: 0, width: 390, height: 844, transform: `scale(${zoom})`, transformOrigin: "50% 42%" }}>
      {t < clipAt && <Screen src="s3_new.png" />}
      {t >= clipAt && t < tPlan + .1 && <Clip src="s3_speak.mp4" from={clipAt} />}
      {showPlan && <>
        <Screen src="s3_plan_noroute.png" />
        <svg width="390" height="844" style={{ position: "absolute", left: 0, top: 0 }}><path d={d} fill="none" stroke={r.color} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} opacity=".9" /></svg>
        <div style={{ position: "absolute", left: 46, top: 641, width: 100, height: 19, background: "#fff" }} />
      </>}
      {showStart && <Clip src="s3_start.mp4" from={startAt} />}
      {showStart && t < startAt + 1.3 && <div style={{ position: "absolute", left: 46, top: 240, width: 100, height: 19, background: "#fff" }} />}
      <Pulse x={89} y={473} t={t} a={clipAt + 1} b={clipAt + 5.3} r={52} />
      <Tap x={89} y={473} t={t} at={clipAt + 1} />
      <Tap x={195} y={586} t={t} at={startAt + 1.2} />
      </div>
    </Phone>
    <OsmCredit x={660} y={886} />
    <Abs x={740} y={120} w={1080}>
      <Step n={1} title="Type or speak a wish" sub={typed || " "} on={on1} done={t >= tPlan} />
      <Step n={2} title="Your route draws itself" sub={t > tPlan + 1.9 ? "19 min walk, ending at a cafe" : " "} on={on2} done={t >= startAt} />
      <Step n={3} title="Tap Start and go" on={on3} />
    </Abs>
    {t > startAt + 1 && <Abs x={1080} y={560} w={640} h={330} style={{ opacity: prog(t, startAt + 1, .3) }}>
      <div style={{ position: "absolute", left: 40, bottom: 0, width: 170, height: 290, background: "#7A4B2B", borderRadius: "16px 16px 0 0", border: `6px solid ${C.ink}` }}>
        <div style={{ position: "absolute", inset: 10, background: "#FFE7A8" }} />
      </div>
      <div style={{ position: "absolute", left: 16, bottom: -4, width: 560, height: 10, background: C.ink, borderRadius: 5 }} />
      <div style={{ position: "absolute", left: 40 + walk * 340, bottom: 2 }}><Blue size={140} expr="happy" bounce={Math.abs(Math.sin(t * 7)) * 12 * clamp(walk * 8)} /></div>
    </Abs>}
  </Abs>;
};
