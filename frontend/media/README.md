# Home hero media

- `hero-plate.jpg`: the 9:8 still (2160×1920) the Home page shows first, and under the video.
- `hero-loop.mp4`: the 5 s loop of the same plate (24 fps, 121 frames, first frame = last frame), laid over
  the still at 100% width, 112.5% height, top −6.25% (home.css). It was rendered square from the plate
  mirror-padded 120/1920 at the top and bottom.

Both came from the "Meadowbell hero" prompt the user supplied; they are served from here so the page needs no
third-party host.

The delivered loop was 960×960 and looked soft when stretched across a 1440 px page. `hero-loop.mp4` is
rebuilt from it with ffmpeg:

1. Upscale to 1920×1920 (lanczos) and sharpen lightly (`cas=strength=0.6`).
2. Over the boy and the dog, show the sharp still instead (a feathered ellipse tilted along the hill),
   because mid-loop the video redraws them more softly. The grass, flowers and clouds keep moving.

```bash
# plate_sq.png: the still mirror-padded to 2160×2160 (pad=2160:2160:0:120,fillborders=top=120:bottom=120:mode=mirror),
# scaled to plate1920.png; mask.png: the 1920² feathered ellipse (geq, centre 455,1080, radii 440×165, 0.24 rad, gblur 14)
ffmpeg -i loop.mp4 -i plate1920.png -i mask.png -filter_complex \
  "[0]scale=1920:1920:flags=lanczos,cas=strength=0.6,format=yuv444p[v];[1][2]alphamerge,format=yuva444p[p];\
   [v][p]overlay=0:0:format=yuv444,format=yuv420p[out]" -map "[out]" -frames:v 121 -r 24 \
  -c:v libx264 -preset slow -crf 22 -profile:v high -pix_fmt yuv420p -movflags +faststart -an hero-loop.mp4
```
