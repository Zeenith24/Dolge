"""
Configuration settings for the Custom Story Video Generator
"""

# Video Settings
VIDEO_SETTINGS = {
    # Output video dimensions (YouTube Shorts format)
    "width": 1080,
    "height": 1920,
    "fps": 24,

    # Video encoding settings
    "codec": "libx264",
    "audio_codec": "aac",
    "bitrate": "8000k",  # 8 Mbps for good quality
    "audio_bitrate": "128k",
    "preset": "medium",  # FFmpeg preset (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
    "threads": 4,

    # Duration limits
    "max_duration": 55,  # Maximum video duration in seconds (YouTube Shorts limit is 60s)
    "min_duration": 3,   # Minimum duration

    # Background settings (when no input video is provided or as fallback)
    "background_color": (0, 0, 0),  # Black background (R, G, B)
    "background_image": None,       # Path to background image (optional)

    # Text display settings
    "font_size": 60,
    "font_color": "white",
    "font_stroke_color": "black",
    "font_stroke_width": 3,
    "font": "Arial-Bold",
    "text_position": "center",  # Options: "top", "center", "bottom"
    "text_margin": 100,         # Margin from edge of screen
    "line_spacing": 1.5,        # Line spacing for multi-line text

    # Text appearance/disappearance settings
    "text_fade_duration": 0.5,  # Seconds for fade in/out
    "text_display_min_time": 2.0,  # Minimum time each text segment stays visible

    # TTS Settings
    "language": "en",
    "slow": False,  # Set to True for slower speech

    # Voice options for Edge TTS (more human-like than gTTS)
    # Popular voices:
    #   en-US-AriaNeural (friendly female)
    #   en-US-GuyNeural (natural male)
    #   en-GB-SoniaNeural (polite British female)
    #   en-AU-NatashaNeural (friendly Australian female)
    #   en-US-JennyNeural (cheerful female)
    #   en-US-DavisNeural (casual male)
    "tts_voice": "en-US-AriaNeural",

    # Use Edge TTS (more human-like) or fall back to gTTS
    "use_edge_tts": True,

    # Background music settings
    "background_music_folder": "assets/music",  # Folder for background music files
    "music_volume": 0.15,  # Volume of background music (0.0 to 1.0)
    "music_fade_duration": 2.0,  # Seconds for music fade in/out

    # Character sprites (for dialogue/story segments)
    "character_sprites": {
        "narrator": "assets/office.png",
        "male": "assets/man.png",
        "female": "assets/feman.png",
    },
    "sprite_scale": 0.25,  # Scale factor for character sprites
    "sprite_position": "bottom-right",  # Where to place character sprites

    # Text emphasis markup (for story files)
    # Use **bold** for emphasis, *italic* for inner thoughts, [Character] for speaker tags
    "enable_markup": True,

    # Video effects
    "enable_zoom_pan": True,  # Ken Burns effect on background video
    "zoom_intensity": 0.05,   # How much to zoom (0.0 to 0.2)
    "pan_speed": 0.001,       # Pan speed factor

    # Transition effects between text segments
    "transition_duration": 0.3,
    "transition_type": "crossfade",  # "crossfade", "slide", "fade"
}

# Folder Settings
PATHS = {
    "stories_folder": "stories",           # Folder containing story .txt files
    "input_videos_folder": "input_videos", # Folder containing raw videos (Subway Surfers, cooking, etc.)
    "output_folder": "output",             # Folder for generated videos
    "temp_folder": "temp",                 # Folder for temporary files
    "assets_folder": "assets",             # Folder for images, music, sprites
    "music_folder": "assets/music",        # Folder for background music
}

# Story File Format
# Each story should be in a .txt file in the stories folder with this format:
# Title: [Your Story Title]
#
# [Your story text goes here]
# Can be multiple paragraphs
#
# Markup support:
# **bold** - emphasized text
# *italic* - inner thoughts/whispers
# [Narrator] - speaker tag (uses narrator sprite)
# [Male] / [Female] - character dialogue (uses character sprites)
#
# Example:
# Title: Kitchen Mishap
#
# [Narrator] I was trying to make coffee this morning when disaster struck.
# [Male] "Wait, that's not sugar!" my roommate shouted.
# *I froze, spoon halfway to the bowl.*
# **It was salt. A whole spoonful of salt.**

# Reddit API Settings (optional - for fetching stories from Reddit)
# Get credentials from: https://www.reddit.com/prefs/apps
REDDIT_CONFIG = {
    "client_id": "",        # Your Reddit app client ID
    "client_secret": "",    # Your Reddit app secret
    "user_agent": "VidMaker/1.0 by YourUsername",  # Custom user agent
}

# Target subreddits for story fetching
TARGET_SUBREDDITS = [
    "tifu",           # Today I F***ed Up
    "AmItheAsshole",  # AITA
    "confessions",    # Confessions
    "TalesFromRetail", # Retail stories
    "IDontWorkHereLady", # Customer service stories
    "MaliciousCompliance", # Malicious compliance stories
    "PettyRevenge",   # Petty revenge stories
    "ProRevenge",     # Pro revenge stories
    "JustNoMIL",      # Mother-in-law stories
    "EntitledParents", # Entitled parents stories
]

# Reddit fetch settings
REDDIT_SETTINGS = {
    "posts_per_subreddit": 25,
    "time_filter": "week",  # hour, day, week, month, year, all
    "exclude_stickied": True,
    "exclude_nsfw": True,
    "min_score": 100,
    "max_post_length": 3000,  # Maximum characters for story text
}

# Supported video formats for input videos
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']

# Supported story file formats
SUPPORTED_STORY_FORMATS = ['.txt']

# Supported audio formats for background music
SUPPORTED_AUDIO_FORMATS = ['.mp3', '.wav', '.ogg', '.m4a', '.flac']