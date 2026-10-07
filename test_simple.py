import os
from moviepy import *
import numpy as np

# Test simple video creation with text overlay
print("Creating simple test video...")

# Create a simple color background
background = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=3)

# Create simple text clip (using default font)
txt_clip = TextClip(text="Hello World", font_size=70, color='white')
txt_clip = txt_clip.with_duration(3).with_position('center')

# Combine
final_video = CompositeVideoClip([background, txt_clip])
final_video = final_video.with_audio(AudioClip(lambda t: 0, duration=3))  # Silent audio

# Write video
print("Writing video...")
final_video.write_videofile("output/test_simple.mp4", fps=24, codec="libx264", audio_codec="aac")
print("Done!")

# Clean up
final_video.close()
background.close()
txt_clip.close()
