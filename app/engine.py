"""
Video rendering engine used by the web app.

Pipeline: Edge TTS (with word timings) -> caption PNGs synced to the spoken words
-> one ffmpeg run that crops the footage to 9:16, overlays captions, mixes audio -> mp4.
"""
import asyncio
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import edge_tts
import imageio_ffmpeg

from . import settings as S

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


# --------------------------------------------------------------------------- media helpers
def probe_duration(path: str) -> float:
    """Duration in seconds, parsed from `ffmpeg -i` output (0.0 if unknown)."""
    proc = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def make_thumbnail(video_path: str, thumb_path: str, at: float = 1.0) -> bool:
    """Grab one frame, scaled to 270px wide."""
    for t in (at, 0.0):
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
                        "-frames:v", "1", "-vf", "scale=270:-2", thumb_path],
                       capture_output=True)
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return True
    return False


# --------------------------------------------------------------------------- text to speech
def speed_to_rate(speed: float) -> str:
    return f"{round((speed - 1.0) * 100):+d}%"


def pitch_to_hz(semitones: int) -> str:
    return f"{int(semitones) * 10:+d}Hz"


async def _synthesize(text, voice, rate, pitch, out_path, want_words=True):
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary" and want_words:
                start = chunk["offset"] / 1e7
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def synthesize(text, voice, rate, pitch, out_path, want_words=True):
    """Returns list of (start, end, word) timings (may be empty)."""
    return asyncio.run(_synthesize(text, voice, rate, pitch, out_path, want_words))


def clean_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", text)          # drop [stage directions] from tone stamps
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --------------------------------------------------------------------------- captions
def build_chunks(text, words, audio_duration, max_words=4):
    """
    Group the story into short phrases with (start, end, text).
    Uses real word timings when available, otherwise spreads phrases by length.
    """
    tokens = text.split()
    if not tokens:
        return []

    # group tokens into phrases, breaking after punctuation
    groups, cur = [], []
    for tok in tokens:
        cur.append(tok)
        if len(cur) >= max_words or re.search(r"[.!?,;:]$", tok):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    chunks = []
    if words:
        nb, nt = len(words), len(tokens)
        idx = 0
        for g in groups:
            first = min(int(idx * nb / nt), nb - 1)
            chunks.append([words[first][0], 0.0, " ".join(g)])
            idx += len(g)
        for i, c in enumerate(chunks):
            c[1] = chunks[i + 1][0] if i + 1 < len(chunks) else audio_duration
        chunks[0][0] = 0.0
    else:
        total = sum(len(" ".join(g)) for g in groups)
        t = 0.0
        for g in groups:
            s = " ".join(g)
            d = audio_duration * len(s) / total
            chunks.append([t, t + d, s])
            t += d
    return [tuple(c) for c in chunks if c[1] - c[0] > 0.05]


def _load_font(size, mono=False):
    names = (["courbd.ttf", "C:/Windows/Fonts/courbd.ttf", "DejaVuSansMono-Bold.ttf"] if mono
             else ["arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width, stroke=0):
    lines, cur = [], []
    for word in text.split():
        trial = " ".join(cur + [word])
        b = draw.textbbox((0, 0), trial, font=font, stroke_width=stroke)
        if b[2] - b[0] <= max_width or not cur:
            cur.append(word)
        else:
            lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines


def render_caption(text, style, size=(S.OUT_W, S.OUT_H)):
    """One caption as a transparent RGBA frame (numpy array)."""
    W, H = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    pad_x, pad_y = 28, 14
    max_w = W - 220

    if style == "typewriter":
        font = _load_font(62, mono=True)
    elif style == "marker":
        text = text.upper()
        font = _load_font(88)
    elif style == "neon":
        font = _load_font(78)
    else:  # cut_paper
        text = text.upper()
        font = _load_font(70)

    stroke = 8 if style == "marker" else 0
    lines = _wrap(draw, text, font, max_w - 2 * pad_x, stroke)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    gap = 18
    boxed = style in ("cut_paper", "typewriter")
    per_h = line_h + (2 * pad_y if boxed else 0)
    total_h = len(lines) * per_h + (len(lines) - 1) * gap
    top = int(H * 0.5 - total_h / 2)

    # neon glow is drawn on its own layer and blurred
    glow = Image.new("RGBA", size, (0, 0, 0, 0)) if style == "neon" else None
    gdraw = ImageDraw.Draw(glow) if glow else None

    y = top
    for i, line in enumerate(lines):
        b = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        tw = b[2] - b[0]
        x = (W - tw) // 2 - b[0]

        if style == "cut_paper":
            # paper strip drawn on its own layer so it can be tilted
            bw, bh = tw + 2 * pad_x, line_h + 2 * pad_y
            layer = Image.new("RGBA", (bw + 20, bh + 20), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            fill = (249, 226, 135, 255) if i % 2 == 0 else (255, 255, 255, 255)
            ld.rounded_rectangle((10 + 6, 10 + 6, 10 + bw + 6, 10 + bh + 6), 8, fill=(30, 27, 25, 255))
            ld.rounded_rectangle((10, 10, 10 + bw, 10 + bh), 8, fill=fill, outline=(30, 27, 25, 255), width=4)
            ld.text((10 + pad_x - b[0], 10 + pad_y), line, font=font, fill=(30, 27, 25, 255))
            layer = layer.rotate(-1.6 if i % 2 == 0 else 1.6, resample=Image.BICUBIC, expand=True)
            canvas.alpha_composite(layer, ((W - layer.width) // 2, y - 10 - (layer.height - bh - 20) // 2))
        elif style == "typewriter":
            bw, bh = tw + 2 * pad_x, line_h + 2 * pad_y
            draw.rounded_rectangle(((W - bw) // 2, y, (W + bw) // 2, y + bh), 6, fill=(15, 15, 15, 215))
            draw.text((x, y + pad_y), line, font=font, fill=(255, 255, 255, 255))
        elif style == "neon":
            gdraw.text((x, y + pad_y), line, font=font, fill=(0, 229, 255, 255), stroke_width=6,
                       stroke_fill=(0, 229, 255, 255))
            draw.text((x, y + pad_y), line, font=font, fill=(235, 255, 255, 255), stroke_width=2,
                      stroke_fill=(0, 200, 255, 255))
        else:  # marker
            draw.text((x, y + pad_y), line, font=font, fill=(255, 221, 0, 255), stroke_width=stroke,
                      stroke_fill=(0, 0, 0, 255))
        y += per_h + gap

    if glow is not None:
        blurred = glow.filter(ImageFilter.GaussianBlur(14))
        base = Image.new("RGBA", size, (0, 0, 0, 0))
        base.alpha_composite(blurred)
        base.alpha_composite(blurred)
        base.alpha_composite(canvas)
        canvas = base
    return np.array(canvas)


# --------------------------------------------------------------------------- render (pure ffmpeg)
#
# Frames are streamed through one ffmpeg process instead of being held in Python memory,
# so a render needs a few hundred MB at most (moviepy needed several times that).

def _plan_segments(paths, duration):
    """Cycle through the clips in order until `duration` is covered -> [(path, seconds)]."""
    usable = [(p, d) for p in paths if (d := probe_duration(p)) > 0.1]
    if not usable:
        raise RuntimeError("None of the selected background clips could be read.")
    segs, total, i = [], 0.0, 0
    while total < duration - 0.01:
        path, dur = usable[i % len(usable)]
        take = min(dur, duration - total)
        segs.append((path, take))
        total += take
        i += 1
        if len(segs) > 400:
            break
    return segs


def _normalize_clip(src, dst, seconds):
    """Re-encode one clip to 1080x1920 / 30fps H.264 (fast, single thread) so clips can be joined."""
    W, H, FPS = S.OUT_W, S.OUT_H, S.OUT_FPS
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1",
           "-t", f"{seconds:.3f}", "-i", src, "-an",
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-threads", "1",
           "-x264-params", "rc-lookahead=0:sync-lookahead=0:bframes=0:threads=1", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"Could not prepare clip {os.path.basename(src)}: {proc.stderr.strip()[-200:]}")


def _write_background_list(segments, duration, workdir, job_id, bg_files, progress):
    """
    ffmpeg concat list for the background: the chosen clips cycled until `duration` is covered.
    With several different clips, each is normalized first so they share one codec/size
    (the concat demuxer needs that, and it avoids ffmpeg buffering several decoders at once).
    """
    distinct = list(dict.fromkeys(p for p, _ in segments))
    source = {p: p for p in distinct}
    if len(distinct) > 1:
        for n, p in enumerate(distinct):
            dst = os.path.join(workdir, f"{job_id}_bg{n}.mp4")
            bg_files.append(dst)
            need = max(t for q, t in segments if q == p)
            _normalize_clip(p, dst, need)
            source[p] = dst
            progress(15 + 25 * (n + 1) / len(distinct), "Preparing footage")

    lines = []
    for path, take in segments:
        posix = source[path].replace(os.sep, "/")
        lines.append(f"file '{posix}'")
        full = probe_duration(source[path])
        if take < full - 0.05:
            lines.append(f"outpoint {take:.3f}")
    list_path = os.path.join(workdir, f"{job_id}_bg.txt")
    with open(list_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return list_path


def _write_caption_sequence(chunks, duration, style, cap_dir):
    """
    Save each caption as a full-canvas transparent PNG and write an ffmpeg concat list that
    shows them back to back (blank PNG in any gaps). Streaming one image sequence keeps
    ffmpeg's memory flat no matter how many captions there are.
    """
    W, H = S.OUT_W, S.OUT_H
    blank = os.path.join(cap_dir, "blank.png")
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)

    entries, t = [], 0.0          # (png, seconds)
    for n, (start, end, chunk_text) in enumerate(chunks):
        if start >= duration:
            break
        end = min(end, duration)
        if start > t + 0.01:
            entries.append((blank, start - t))
        png = os.path.join(cap_dir, f"{n:03d}.png")
        Image.fromarray(render_caption(chunk_text, style)).save(png)
        entries.append((png, end - max(start, t)))
        t = end
    if t < duration - 0.01:
        entries.append((blank, duration - t))
    if not entries:
        entries.append((blank, duration))

    list_path = os.path.join(cap_dir, "list.txt")
    with open(list_path, "w") as f:
        for png, secs in entries:
            posix = png.replace(os.sep, "/")
            f.write(f"file '{posix}'\nduration {max(secs, 0.04):.3f}\n")
        f.write("file '{}'\n".format(entries[-1][0].replace(os.sep, "/")))  # concat quirk: repeat last file
    return list_path


def render_video(*, text, out_path, voice_edge, speed, pitch, clip_paths, caption_style,
                 music_path=None, progress=lambda pct, stage: None, workdir=S.TEMP_DIR,
                 job_id="job"):
    """
    Build the final reel. Returns (duration_seconds, truncated_flag).
    `progress(pct, stage)` is called as the job advances.
    """
    W, H, FPS = S.OUT_W, S.OUT_H, S.OUT_FPS
    text = clean_text(text)
    if not text:
        raise ValueError("The story is empty.")

    audio_path = os.path.join(workdir, f"{job_id}.mp3")
    cap_dir = os.path.join(workdir, f"{job_id}_caps")
    log_path = os.path.join(workdir, f"{job_id}_ffmpeg.log")
    bg_files = []   # normalized temp clips to delete afterwards
    try:
        progress(5, "Synthesizing voiceover")
        words = synthesize(text, voice_edge, speed_to_rate(speed), pitch_to_hz(pitch), audio_path)
        duration = probe_duration(audio_path)
        if duration <= 0:
            raise RuntimeError("The voice service returned no audio.")
        truncated = duration > S.MAX_DURATION
        if truncated:
            duration = float(S.MAX_DURATION)

        progress(15, "Preparing footage")
        segments = _plan_segments(clip_paths, duration)
        bg_list = _write_background_list(segments, duration, workdir, job_id, bg_files, progress)

        progress(40, "Setting captions")
        os.makedirs(cap_dir, exist_ok=True)
        list_path = _write_caption_sequence(build_chunks(text, words, duration), duration,
                                            caption_style, cap_dir)

        # ---- inputs (footage and captions are each ONE sequential input: low memory)
        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin"]
        cmd += ["-threads", "1", "-an", "-f", "concat", "-safe", "0", "-i", bg_list]
        cap_idx = 1
        cmd += ["-threads", "1", "-f", "concat", "-safe", "0", "-i", list_path]
        voice_idx = 2
        cmd += ["-i", audio_path]
        music_idx = None
        if music_path and os.path.exists(music_path):
            music_idx = 3
            cmd += ["-stream_loop", "-1", "-i", music_path]

        # ---- filter graph
        f = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"setsar=1,fps={FPS},format=yuv420p[bg]",
             f"[{cap_idx}:v]fps={FPS},format=rgba[caps]",
             "[bg][caps]overlay=0:0:format=auto,format=yuv420p[vout]"]
        if music_idx is not None:
            f.append(f"[{music_idx}:a]volume=0.12[mus]")
            f.append(f"[{voice_idx}:a][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
        else:
            f.append(f"[{voice_idx}:a]anull[aout]")

        cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]",
                "-t", f"{duration:.3f}", "-r", str(FPS),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
                # low-memory encoder settings (no lookahead / B-frames, single thread)
                "-x264-params", "rc-lookahead=0:sync-lookahead=0:bframes=0:threads=1",
                "-threads", "1", "-filter_threads", "1", "-filter_complex_threads", "1",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats", out_path]

        progress(45, "Rendering video")
        with open(log_path, "w") as log:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True)
            for line in proc.stdout:
                if line.startswith("out_time_us="):
                    try:
                        done = int(line.split("=")[1]) / 1e6
                    except ValueError:
                        continue
                    progress(45 + 53 * min(done / duration, 1.0), "Rendering video")
            code = proc.wait()
        if code != 0:
            with open(log_path) as log:
                tail = "".join(log.readlines()[-8:]).strip()
            raise RuntimeError(f"Video encoding failed: {tail or 'ffmpeg exited with ' + str(code)}")
        return duration, truncated
    finally:
        for p in (audio_path, log_path, os.path.join(workdir, f"{job_id}_bg.txt"), *bg_files):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if os.path.isdir(cap_dir):
            for fn in os.listdir(cap_dir):
                try:
                    os.remove(os.path.join(cap_dir, fn))
                except OSError:
                    pass
            try:
                os.rmdir(cap_dir)
            except OSError:
                pass
