// Captions (from ElevenLabs' character timings), captions.srt, script.md and the QR image. No network needed.
import fs from "node:fs"; import path from "node:path"; import QRCode from "qrcode";
const P = path.resolve(import.meta.dirname, ".."); const read = (f) => JSON.parse(fs.readFileSync(path.join(P, f)));
const S = read("src/script.json"), A = read("public/audio/vo_align.json"), cfg = read("src/config.json");
const caps = [];
for (const s of S) {
  const a = A[s.id], text = a.chars.join(""); if (text !== s.vo) throw new Error(`VO text differs in ${s.id}`);
  let i = 0;
  for (const c of s.caps) { const j = text.indexOf(c, i); if (j < 0) throw new Error(c); caps.push({ scene: s.id, text: c, start: s.start + s.voAt + a.start[j], end: s.start + s.voAt + a.end[j + c.length - 1] }); i = j + c.length; }
}
caps.forEach((c, i) => { const nx = caps[i + 1]; c.end = Math.min(c.end + .35, nx && nx.scene === c.scene ? nx.start : c.end + .35); c.start = +c.start.toFixed(3); c.end = +c.end.toFixed(3); });
fs.writeFileSync(path.join(P, "src/captions.json"), JSON.stringify(caps, null, 1));
const ts = (x) => { const ms = Math.round(x * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s = Math.floor(ms / 1000) % 60; return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`; };
fs.writeFileSync(path.join(P, "captions.srt"), caps.map((c, i) => `${i + 1}\n${ts(c.start)} --> ${ts(c.end)}\n${c.text}\n`).join("\n"));
const md = ["# StrollCall promo: final voiceover and timings", "", "Generated from `src/script.json` and the voiceover's own timings. Do not edit by hand.", "",
  ...S.flatMap((s) => { const a = A[s.id], b = s.start + s.voAt; return [`## ${s.start}–${s.end}s · ${s.title}`, "", `VO ${b.toFixed(1)}–${(b + a.end.at(-1)).toFixed(1)}s: ${s.vo}`, ""]; })];
fs.writeFileSync(path.join(P, "script.md"), md.join("\n"));
const placeholder = cfg.shortLink === "[SHORT_LINK]";
await QRCode.toFile(path.join(P, "public/qr.png"), placeholder ? "PLACEHOLDER: set shortLink in src/config.json" : cfg.shortLink, { width: 880, margin: 1, errorCorrectionLevel: "M", color: { dark: "#2B2340", light: "#FFFFFF" } });
console.log(caps.length, "captions");
