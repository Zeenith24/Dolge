"""
Video rendering engine used by the web app.

Pipeline: Edge TTS (with word timings) -> background clips (cover-cropped to 9:16)
-> transparent caption clips synced to the spoken words -> optional music -> mp4.
"""
import asyncio
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import edge_tts
import imageio_ffmpeg
from moviepy import (AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip,
                     VideoFileClip, afx, concatenate_videoclips, vfx)
from proglog import ProgressBarLogger

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


# --------------------------------------------------------------------------- background
def _cover(clip, W, H):
    """Scale + center-crop to fill WxH without distortion."""
    scale = max(W / clip.w, H / clip.h)
    clip = clip.resized(scale)
    x1 = (clip.w - W) / 2
    y1 = (clip.h - H) / 2
    return clip.cropped(x1=x1, y1=y1, x2=x1 + W, y2=y1 + H)


def build_background(paths, duration, W, H):
    """Cycle through the chosen clips (in order) until `duration` is covered."""
    sources = []
    for p in paths:
        try:
            c = VideoFileClip(p, audio=False)
            if c.duration and c.duration > 0:
                sources.append(c)
        except Exception as exc:  # unreadable file: skip it
            print(f"skipping unreadable clip {p}: {exc}")
    if not sources:
        raise RuntimeError("None of the selected background clips could be read.")

    parts, total, i = [], 0.0, 0
    while total < duration:
        src = sources[i % len(sources)]
        take = min(src.duration, duration - total)
        if take < 0.05:
            break
        parts.append(_cover(src.subclipped(0, take), W, H))
        total += take
        i += 1
    bg = parts[0] if len(parts) == 1 else concatenate_videoclips(parts)
    return bg.with_duration(duration), sources


# --------------------------------------------------------------------------- render
class _Progress(ProgressBarLogger):
    def __init__(self, cb, lo, hi):
        super().__init__()
        self.cb, self.lo, self.hi = cb, lo, hi

    def bars_callback(self, bar, attr, value, old_value=None):
        if bar == "frame_index" and attr == "index":
            total = self.bars[bar].get("total") or 0
            if total:
                self.cb(self.lo + (self.hi - self.lo) * value / total, "Rendering video")

    def callback(self, **kw):
        pass


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
    opened = []
    try:
        progress(5, "Synthesizing voiceover")
        words = synthesize(text, voice_edge, speed_to_rate(speed), pitch_to_hz(pitch), audio_path)

        voice = AudioFileClip(audio_path)
        opened.append(voice)
        duration = voice.duration
        truncated = False
        if duration > S.MAX_DURATION:
            duration, truncated = S.MAX_DURATION, True
            voice = voice.subclipped(0, duration)

        progress(20, "Preparing footage")
        bg, sources = build_background(clip_paths, duration, W, H)
        opened.extend(sources)

        progress(35, "Setting captions")
        chunks = [c for c in build_chunks(text, words, duration + 0.0) if c[0] < duration]
        fade = 0.08
        caption_clips = []
        for start, end, chunk_text in chunks:
            end = min(end, duration)
            frame = render_caption(chunk_text, caption_style)
            clip = ImageClip(frame, transparent=True).with_start(start).with_duration(end - start)
            if end - start > 4 * fade:
                clip = clip.with_effects([vfx.CrossFadeIn(fade)])
            caption_clips.append(clip)

        final = CompositeVideoClip([bg] + caption_clips, size=(W, H)).with_duration(duration)

        tracks = [voice]
        if music_path and os.path.exists(music_path):
            music = AudioFileClip(music_path)
            opened.append(music)
            music = music.with_effects([afx.AudioLoop(duration=duration)]).with_volume_scaled(0.12)
            tracks.append(music)
        final = final.with_audio(CompositeAudioClip(tracks).with_duration(duration))

        progress(45, "Rendering video")
        final.write_videofile(out_path, fps=FPS, codec="libx264", audio_codec="aac",
                              bitrate="6000k", audio_bitrate="192k", preset="veryfast",
                              threads=4, logger=_Progress(progress, 45, 98),
                              ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"])
        final.close()
        return duration, truncated
    finally:
        for c in opened:
            try:
                c.close()
            except Exception:
                pass
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass
