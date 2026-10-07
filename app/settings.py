"""Paths and constants for the web app."""
import os
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "videos")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
TEMP_DIR = os.path.join(DATA_DIR, "tmp")
LIBRARY_DIR = os.path.join(ROOT, "input_videos")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
def _db_url() -> str:
    """DATABASE_URL env var (e.g. postgresql://user:pass@host/db) or a local SQLite file."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{os.path.join(DATA_DIR, 'app.db').replace(os.sep, '/')}"
    # providers often hand out postgres:// or postgresql://; SQLAlchemy needs the psycopg driver name
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DB_URL = _db_url()

for d in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, THUMB_DIR, TEMP_DIR, LIBRARY_DIR, MUSIC_DIR):
    os.makedirs(d, exist_ok=True)


def _load_secret() -> str:
    env = os.environ.get("REELFORGE_SECRET")
    if env:
        return env
    path = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_urlsafe(48))
    with open(path) as f:
        return f.read().strip()


SECRET_KEY = _load_secret()
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
COOKIE_NAME = "dolge_token"
COOKIE_SECURE = os.environ.get("REELFORGE_COOKIE_SECURE", "0") == "1"

SIGNUP_CREDITS = 24
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg")
MAX_STORY_CHARS = 4000
MAX_DURATION = 55
# Captions are always drawn on a 1080x1920 canvas, then scaled to the output size.
CAP_W, CAP_H = 1080, 1920
OUT_FPS = int(os.environ.get("REELFORGE_FPS", "30"))

VOICES = [
    {"id": "oliver", "name": "Oliver", "emoji": "🎙️", "gender": "male", "edge": "en-GB-RyanNeural",
     "tag": "Deep Vintage Storyteller (Male)", "desc": "Warm British tone, ideal for nostalgic travel and retro documentaries."},
    {"id": "aria", "name": "Aria", "emoji": "✨", "gender": "female", "edge": "en-US-AriaNeural",
     "tag": "Warm & Whimsical Docu (Female)", "desc": "Crisp, curious, and gentle cadence. Great for cafes, lifestyle, and books."},
    {"id": "kai", "name": "Kai", "emoji": "⚡", "gender": "male", "edge": "en-US-ChristopherNeural",
     "tag": "Gritty Noir & Suspense (Male)", "desc": "Low register for mystery hooks, eerie twists, and street stories."},
    {"id": "luna", "name": "Luna", "emoji": "🌿", "gender": "female", "edge": "en-US-AvaNeural",
     "tag": "Ethereal & Melodic (Female)", "desc": "Soft, expressive tone for calm travel clips and reflective stories."},
    {"id": "jasper", "name": "Jasper", "emoji": "🔥", "gender": "male", "edge": "en-US-AndrewNeural",
     "tag": "Energetic Viral Hook (Male)", "desc": "Punchy modern creator delivery engineered to capture the first 2 seconds."},
    {"id": "echo", "name": "Echo", "emoji": "📻", "gender": "nonbinary", "edge": "en-US-BrianNeural",
     "tag": "Lofi Radio Host (Neutral)", "desc": "Smooth, balanced late-night broadcast tone with natural inflection."},
]
VOICE_BY_ID = {v["id"]: v for v in VOICES}

CAPTION_STYLES = [
    {"id": "cut_paper", "label": "🏷️ Cut Paper"},
    {"id": "marker", "label": "🖊️ Marker Pop"},
    {"id": "typewriter", "label": "⌨️ Typewriter"},
    {"id": "neon", "label": "✨ Neon Tape"},
]
CAPTION_IDS = {c["id"] for c in CAPTION_STYLES}


# --------------------------------------------------------------------------- quality options
# Qualities users may pick. 1080p needs more RAM, so it is off unless REELFORGE_ALLOW_1080=1.
ALLOW_1080 = os.environ.get("REELFORGE_ALLOW_1080", "0") == "1"
QUALITIES = [
    {"width": 720, "label": "720p", "note": "Fast, works everywhere", "enabled": True},
    {"width": 1080, "label": "1080p HD", "note": "Sharper, slower, needs a bigger server", "enabled": ALLOW_1080},
]
ALLOWED_WIDTHS = {q["width"] for q in QUALITIES if q["enabled"]}
DEFAULT_WIDTH = 720

# --------------------------------------------------------------------------- email
# Public address of the site, used in email links (e.g. https://app.example.com).
APP_URL = os.environ.get("APP_URL", "").rstrip("/")
MAIL_FROM = os.environ.get("MAIL_FROM", "Dolge <onboarding@resend.dev>")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_ENABLED = bool(RESEND_API_KEY or SMTP_HOST)
# Verification is only enforced when email can actually be sent; otherwise nobody could verify.
REQUIRE_VERIFIED = MAIL_ENABLED
VERIFY_TTL_HOURS = 24
RESET_TTL_MINUTES = 60

# --------------------------------------------------------------------------- reddit
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "web:dolge-reel-studio:v1.0 (story import)")
