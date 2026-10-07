"""
Custom Story Video Generator
Creates YouTube Shorts by overlaying text on user-provided videos
"""

import os
from gtts import gTTS
import edge_tts
import asyncio
from moviepy import *
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from config import VIDEO_SETTINGS, PATHS
from story_processor import process_story_text, estimate_duration

# Create output folders
os.makedirs(PATHS["output_folder"], exist_ok=True)
os.makedirs(PATHS["temp_folder"], exist_ok=True)
os.makedirs(PATHS["stories_folder"], exist_ok=True)
os.makedirs(PATHS["input_videos_folder"], exist_ok=True)

def get_input_videos():
    """
    Get list of available input videos from the input_videos folder

    Returns:
        List of video file paths
    """
    videos = []
    input_folder = PATHS["input_videos_folder"]

    if not os.path.exists(input_folder):
        return videos

    for filename in os.listdir(input_folder):
        if any(filename.lower().endswith(ext) for ext in VIDEO_SETTINGS.get("supported_formats", ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv'])):
            videos.append(os.path.join(input_folder, filename))

    return videos

def get_story_files():
    """
    Get list of available story files from the stories folder

    Returns:
        List of story file paths
    """
    stories = []
    stories_folder = PATHS["stories_folder"]

    if not os.path.exists(stories_folder):
        return stories

    for filename in os.listdir(stories_folder):
        if any(filename.lower().endswith(ext) for ext in VIDEO_SETTINGS.get("supported_story_formats", ['.txt'])):
            stories.append(os.path.join(stories_folder, filename))

    return stories

async def generate_audio_edge_tts(text, output_path, voice="en-US-AriaNeural"):
    """
    Generate audio using Edge TTS (more human-like than gTTS)

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice to use (see config.py for options)
    """
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio_gtts(text, output_path, lang="en", slow=False):
    """
    Generate audio using gTTS (Google Text-to-Speech)

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        lang: Language code
        slow: Whether to speak slowly
    """
    tts = gTTS(text=text, lang=lang, slow=slow)
    tts.save(output_path)

def generate_audio(text, output_path, config=None):
    """
    Generate audio using the configured TTS engine

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        config: Configuration dictionary
    """
    if config is None:
        config = VIDEO_SETTINGS

    if config.get("use_edge_tts", True):
        # Use Edge TTS (more human-like)
        voice = config.get("tts_voice", "en-US-AriaNeural")
        try:
            asyncio.run(generate_audio_edge_tts(text, output_path, voice))
            return
        except Exception as e:
            print(f"Edge TTS failed, falling back to gTTS: {e}")

    # Fallback to gTTS
    lang = config.get("language", "en")
    slow = config.get("slow", False)
    generate_audio_gtts(text, output_path, lang, slow)

def color_to_rgb(color):
    """
    Convert color name or hex to RGB tuple

    Args:
        color: Color name (string) or hex string or RGB tuple

    Returns:
        RGB tuple (r, g, b)
    """
    if isinstance(color, tuple) and len(color) == 3:
        return color

    if isinstance(color, str):
        # Handle common color names
        color_map = {
            'white': (255, 255, 255),
            'black': (0, 0, 0),
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'yellow': (255, 255, 0),
            'cyan': (0, 255, 255),
            'magenta': (255, 0, 255),
            'gray': (128, 128, 128),
            'grey': (128, 128, 128)
        }

        if color.lower() in color_map:
            return color_map[color.lower()]

        # Handle hex colors
        if color.startswith('#'):
            hex_color = color[1:]
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (r, g, b)

    # Default to white if we can't parse the color
    return (255, 255, 255)

def create_text_clip(text, duration, fontsize=60, color="white",
                     stroke_color="black", stroke_width=2, font="Arial-Bold",
                     size=(1080, 1920), position="bottom", margin=100):
    """
    Create a text clip with proper styling and positioning

    Args:
        text: Text to display
        duration: Duration of the clip in seconds
        fontsize: Font size
        color: Text color
        stroke_color: Outline color
        stroke_width: Outline width
        font: Font name
        size: Video dimensions (width, height)
        position: Position of text ("top", "center", "bottom")
        margin: Margin from edge of screen

    Returns:
        TextClip object
    """
    # Create TextClip
    txt_clip = TextClip(
        text,
        fontsize=fontsize,
        color=color,
        font=font,
        method='caption',
        align='center',
        size=(size[0] - 2 * margin, None)  # Leave margins
    )

    # Add outline/stroke effect
    if stroke_width > 0:
        # Create outline by creating multiple copies
        txt_clip = txt_clip.margin(
            margin=stroke_width,
            opacity=0
        ).set_position(('center', 'center'))

        # Create the outline version
        outline_clip = TextClip(
            text,
            fontsize=fontsize,
            color=stroke_color,
            font=font,
            method='caption',
            align='center',
            size=(size[0] - 2 * margin, None)
        ).margin(margin=stroke_width, opacity=0)

        # Combine text and outline
        txt_clip = CompositeVideoClip([outline_clip, txt_clip.set_position((stroke_width, stroke_width))])

    # Set duration and position
    txt_clip = txt_clip.set_duration(duration)

    # Position the text
    if position == "top":
        y_pos = margin
    elif position == "center":
        y_pos = (size[1] - txt_clip.h) // 2
    else:  # bottom
        y_pos = size[1] - txt_clip.h - margin

    txt_clip = txt_clip.set_position(('center', y_pos))

    return txt_clip

def split_into_chunks(text, max_words=4):
    """Split text into short phrases (<= max_words), breaking at punctuation first."""
    import re
    chunks = []
    for part in re.split(r'(?<=[.!?,;:])\s+', text.strip()):
        words = part.split()
        for i in range(0, len(words), max_words):
            chunk = ' '.join(words[i:i + max_words])
            if chunk:
                chunks.append(chunk)
    return chunks

def render_text_image(text, fontsize, color, stroke_color, stroke_width, size, position, margin):
    """Render text onto a fully transparent RGBA canvas (so the video shows through)."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_obj = None
    for name in ("arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font_obj = ImageFont.truetype(name, fontsize)
            break
        except IOError:
            continue
    if font_obj is None:
        font_obj = ImageFont.load_default()

    # Wrap to fit width
    max_width = size[0] - 2 * margin
    lines, current = [], []
    for word in text.split():
        test = ' '.join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font_obj, stroke_width=stroke_width)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(' '.join(current))
            current = [word]
    if current:
        lines.append(' '.join(current))
    wrapped = "\n".join(lines)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_obj, align="center",
                                   stroke_width=stroke_width)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size[0] - text_w) // 2 - bbox[0]
    if position == "top":
        y = margin
    elif position == "center":
        y = (size[1] - text_h) // 2
    else:
        y = size[1] - text_h - margin
    y -= bbox[1]

    draw.multiline_text((x, y), wrapped, font=font_obj, fill=color_to_rgb(color) + (255,),
                        align="center", stroke_width=stroke_width,
                        stroke_fill=color_to_rgb(stroke_color) + (255,))
    return np.array(img)

def create_fade_text_clip(full_text, audio_duration, fps=24,
                         fontsize=60, color="white", stroke_color="black", stroke_width=2,
                         font="Arial-Bold", size=(1080, 1920), position="bottom", margin=100,
                         fade_duration=0.5, min_display_time=2.0):
    """
    Build a list of transparent text clips, one per short phrase, timed across the
    audio proportionally to phrase length. Each clip carries an alpha mask so it
    overlays on the background video instead of covering it.

    Returns:
        List of ImageClips (to be placed in a CompositeVideoClip above the background)
    """
    chunks = split_into_chunks(full_text) or [full_text]
    weights = [max(len(c), 1) for c in chunks]
    total = sum(weights)

    clips = []
    t = 0.0
    fade = min(fade_duration, 0.15)  # keep fades short for fast-paced phrases
    for chunk, w in zip(chunks, weights):
        dur = audio_duration * w / total
        frame = render_text_image(chunk, fontsize, color, stroke_color,
                                  stroke_width, size, position, margin)
        clip = (ImageClip(frame, transparent=True)
                .with_start(t)
                .with_duration(dur))
        if dur > 2 * fade:
            clip = clip.with_effects([vfx.CrossFadeIn(fade), vfx.CrossFadeOut(fade)])
        clips.append(clip)
        t += dur
    return clips


def create_background_clip_from_video(input_video_path, duration):
    """
    Create background clip from an input video file with robust error handling

    Args:
        input_video_path: Path to the input video file
        duration: Desired duration of the background clip

    Returns:
        VideoClip for background (trimmed, looped, or extended to match duration)
    """
    try:
        # Load the input video
        video_clip = VideoFileClip(input_video_path)

        # VALIDATE VIDEO CLIP PROPERLY
        if video_clip is None or video_clip.reader is None:
            raise ValueError(f"Video reader failed to initialize for {input_video_path}")

        # Get the original duration
        original_duration = video_clip.duration

        if original_duration <= 0:
            # If we can't get duration, create a black clip
            video_clip.close()
            return ColorClip(size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"]),
                           color=VIDEO_SETTINGS["background_color"], duration=duration)

        # Calculate how many times we need to loop the video to reach desired duration
        loops_needed = int(duration / original_duration) + 1

        if loops_needed == 1:
            # Video is longer than needed duration, just trim it
            background = video_clip.subclipped(0, duration)
        else:
            # Need to loop the video
            # Create a list of clips to concatenate
            clips = []
            remaining_duration = duration

            for i in range(loops_needed):
                if remaining_duration >= original_duration:
                    # Use full clip
                    clips.append(video_clip.subclipped(0, original_duration))
                    remaining_duration -= original_duration
                else:
                    # Use partial clip for the remainder
                    clips.append(video_clip.subclipped(0, remaining_duration))
                    remaining_duration = 0
                    break

            # Concatenate all clips
            if len(clips) == 1:
                background = clips[0]
            else:
                background = concatenate_videoclips(clips)

        # Resize to fit video dimensions if needed - FIXED for MoviePy version compatibility
        if background.w != VIDEO_SETTINGS["width"] or background.h != VIDEO_SETTINGS["height"]:
            background = background.resized(new_size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"]))

        # DON'T close the original video clip here to avoid reference issues
        # video_clip.close()
        # Note: The background clip should be independent now

        return background

    except Exception as e:
        print(f"Error loading input video {input_video_path}: {e}")
        print("Falling back to solid color background")
        # Fallback to solid color background
        color = VIDEO_SETTINGS["background_color"]
        return ColorClip(size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"]),
                       color=color, duration=duration)

def create_custom_story_video(story_text, output_filename, story_title=""):
    """
    Create a YouTube Shorts video by overlaying text on user-provided videos

    Args:
        story_text: The processed story text
        output_filename: Output file path
        story_title: Title of the story (for logging)

    Returns:
        Path to the generated video file
    """
    print(f"Processing story: {story_title[:50]}...")

    # Get available input videos
    input_videos = get_input_videos()

    if not input_videos:
        print("Warning: No input videos found in input_videos folder!")
        print("Please add videos (Subway Surfers gameplay, cooking videos, etc.) to the input_videos folder.")
        # Fallback to solid color background
        use_input_video = False
        selected_video = None
    else:
        # Select a random video for variety
        import random
        selected_video = random.choice(input_videos)
        use_input_video = True
        print(f"Using input video: {os.path.basename(selected_video)}")

    # Step 1: Generate Audio from text
    print("Generating audio...")
    audio_path = os.path.join(PATHS["temp_folder"], f"temp_audio_{hash(story_text)}.mp3")

    # Generate audio using selected TTS engine
    generate_audio(story_text, audio_path, VIDEO_SETTINGS)

    # Load audio to get duration
    audio = AudioFileClip(audio_path)
    audio_duration = audio.duration

    # Check if audio duration is within limits
    max_duration = VIDEO_SETTINGS["max_duration"]
    if audio_duration > max_duration:
        print(f"Warning: Audio duration ({audio_duration:.1f}s) exceeds maximum "
              f"({max_duration}s). Truncating...")
        audio = audio.subclipped(0, max_duration)
        audio_duration = max_duration
        # Note: We don't truncate the text here for simplicity
        # In a more advanced version, we could summarize the text

    # Step 2: Create background (from input video or solid color)
    print("Creating background...")
    if use_input_video and selected_video:
        background = create_background_clip_from_video(selected_video, audio_duration)
    else:
        # Fallback to solid color background
        color = VIDEO_SETTINGS["background_color"]
        background = ColorClip(size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"]),
                               color=color, duration=audio_duration)

    # Step 3: Create text display synchronized with audio
    print("Creating synchronized text display...")
    # Use fade-in/fade-out text effect
    text_clips = create_fade_text_clip(
        story_text,
        audio_duration,
        fps=VIDEO_SETTINGS["fps"],
        fontsize=VIDEO_SETTINGS["font_size"],
        color=VIDEO_SETTINGS["font_color"],
        stroke_color=VIDEO_SETTINGS["font_stroke_color"],
        stroke_width=VIDEO_SETTINGS["font_stroke_width"],
        font=VIDEO_SETTINGS["font"],
        size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"]),
        position=VIDEO_SETTINGS["text_position"],
        margin=VIDEO_SETTINGS["text_margin"],
        fade_duration=VIDEO_SETTINGS["text_fade_duration"],
        min_display_time=VIDEO_SETTINGS["text_display_min_time"]
    )

    # Step 4: Combine everything
    print("Combining elements...")
    final_video = CompositeVideoClip(
        [background] + text_clips,
        size=(VIDEO_SETTINGS["width"], VIDEO_SETTINGS["height"])
    ).with_duration(audio_duration)

    # Set audio
    final_video = final_video.with_audio(audio)

    # Step 5: Write video file
    print(f"Writing video to {output_filename}...")
    final_video.write_videofile(
        output_filename,
        fps=VIDEO_SETTINGS["fps"],
        codec=VIDEO_SETTINGS["codec"],
        audio_codec=VIDEO_SETTINGS["audio_codec"],
        bitrate=VIDEO_SETTINGS["bitrate"],
        audio_bitrate=VIDEO_SETTINGS["audio_bitrate"],
        preset=VIDEO_SETTINGS["preset"],
        threads=VIDEO_SETTINGS["threads"]
    )

    # Clean up
    audio.close()
    final_video.close()
    if os.path.exists(audio_path):
        os.remove(audio_path)

    print(f"Video successfully created: {output_filename}")
    return output_filename

def process_custom_story(story_obj, output_dir=None):
    """
    Process a CustomStory object into a video

    Args:
        story_obj: CustomStory object from story_loader.py
        output_dir: Directory to save output (optional)

    Returns:
        Path to generated video file
    """
    if output_dir is None:
        output_dir = PATHS["output_folder"]

    # Process the story text for better TTS
    processed_text = process_story_text(story_obj.full_text)

    # Create output filename
    safe_title = "".join(c for c in story_obj.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title[:50]  # Limit length

    # Add a counter to avoid filename conflicts
    counter = 1
    base_filename = f"{safe_title}_{story_obj.file_name.replace('.txt', '')}"
    output_filename = os.path.join(output_dir, f"{base_filename}.mp4")

    # If file exists, add a number
    while os.path.exists(output_filename):
        output_filename = os.path.join(output_dir, f"{base_filename}_{counter}.mp4")
        counter += 1

    # Create the video
    video_path = create_custom_story_video(
        processed_text,
        output_filename,
        story_title=story_obj.title
    )

    return video_path

# Example usage and testing
if __name__ == "__main__":
    # Test with sample text
    sample_story = """
    This is a test story for the Custom Story Video Generator.
    It demonstrates how the text processing and video creation works.
    The story should be converted to speech and displayed with fade-in/fade-out effects.
    """

    processed = process_story_text(sample_story)
    print(f"Original: {len(sample_story)} chars")
    print(f"Processed: {len(processed)} chars")
    print(f"Estimated duration: {estimate_duration(processed):.1f} seconds")

    # Create test video
    test_output = os.path.join(VIDEO_SETTINGS["output_folder"], "test_story.mp4")
    create_custom_story_video(processed, test_output, "Test Story")