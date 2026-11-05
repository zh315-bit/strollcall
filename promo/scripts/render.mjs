// One command: captions + QR, audio mix, both videos, stills.   npm run render
import { execFileSync } from "node:child_process"; import fs from "node:fs"; import path from "node:path";
const P = path.resolve(import.meta.dirname, ".."); process.chdir(P);
const run = (c, a) => execFileSync(c, a, { stdio: ["ignore", "inherit", "inherit"] });
const cap = (c, a) => execFileSync(c, a, { stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" });
run("node", ["scripts/build.mjs"]);
fs.mkdirSync("out", { recursive: true }); fs.mkdirSync("stills", { recursive: true });

// Mix: each scene's VO at its time, music ducked under it, then two-pass loudness to -14 LUFS with peaks under -1 dBTP.
const S = JSON.parse(fs.readFileSync("src/script.json")); const TOTAL = S.at(-1).end;
const A = JSON.parse(fs.readFileSync("public/audio/vo_align.json"));
const at = (id, w, plus = 0) => { const s = S.find((x) => x.id === id), a = A[id]; return Math.round((s.start + s.voAt + a.start[a.chars.join("").indexOf(w)] + plus) * 30); };
const endF = (id, minus) => Math.round((S.find((x) => x.id === id).end - minus) * 30);
const ins = S.flatMap((s) => ["-i", `public/audio/vo_${s.id}.mp3`]).concat(["-i", "public/audio/music.mp3"]);
const f = S.map((s, i) => { const ms = Math.round((s.start + s.voAt) * 1000); return `[${i}:a]aformat=channel_layouts=stereo:sample_rates=48000,adelay=${ms}|${ms}[v${i}]`; });
f.push(`${S.map((_, i) => `[v${i}]`).join("")}amix=inputs=${S.length}:normalize=0,apad=whole_dur=${TOTAL + 1},asplit=2[vk][vm]`);
f.push(`[${S.length}:a]aformat=channel_layouts=stereo:sample_rates=48000,volume=0.16[m0]`);
f.push(`[m0][vk]sidechaincompress=threshold=0.02:ratio=7:attack=30:release=420:makeup=1[m1]`);
f.push(`[vm][m1]amix=inputs=2:normalize=0,atrim=0:${TOTAL},afade=t=out:st=${TOTAL - 1.4}:d=1.4[o]`);
run("ffmpeg", ["-loglevel", "error", "-y", ...ins, "-filter_complex", f.join(";"), "-map", "[o]", "-ar", "48000", "out/raw_mix.wav"]);
const LN = "loudnorm=I=-14:TP=-1.6:LRA=11";
const m = execFileSync("sh", ["-c", `ffmpeg -hide_banner -nostats -i out/raw_mix.wav -af ${LN}:print_format=json -f null - 2>&1`], { encoding: "utf8" });
const j = JSON.parse(m.slice(m.lastIndexOf("{"), m.lastIndexOf("}") + 1));
run("ffmpeg", ["-loglevel", "error", "-y", "-i", "out/raw_mix.wav", "-af", `${LN}:measured_I=${j.input_i}:measured_TP=${j.input_tp}:measured_LRA=${j.input_lra}:measured_thresh=${j.input_thresh}:offset=${j.target_offset}:linear=true,aresample=48000`, "-ar", "48000", "out/mix.wav"]);

const entry = "src/index.ts";
for (const [name, on] of [["strollcall_promo_16x9", true], ["strollcall_promo_16x9_no_captions", false]]) {
  run("npx", ["remotion", "render", entry, "Promo", `out/${name}.silent.mp4`, `--props=${JSON.stringify({ captions: on })}`, "--codec=h264", "--crf=17", "--concurrency=8", "--color-space=bt709", "--log=error"]);
  run("ffmpeg", ["-loglevel", "error", "-y", "-i", `out/${name}.silent.mp4`, "-i", "out/mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", `${name}.mp4`]);
}
const STILLS = { s1: at("s1", "outside"), s2: endF("s2", .3), s3: at("s3", "StrollCall", 1.7), s4: at("s4", "so nobody"), s5: endF("s5", 1.4), s6: endF("s6", .4), s7: endF("s7", .2) };
for (const [id, fr] of Object.entries(STILLS)) run("npx", ["remotion", "still", entry, "Promo", `stills/${id}.png`, `--frame=${fr}`, "--log=error"]);
console.log("done");
