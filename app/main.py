"""
Dolge reel studio - FastAPI backend.

Run:  uvicorn app.main:app --reload      (from the project root)
"""
import datetime as dt
import os
import re
import secrets
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, engine, mailer, reddit, settings as S
from .db import Asset, SessionLocal, User, Video, get_db, init_db, new_id

# One render at a time by default (each uses a few hundred MB); raise on bigger servers.
executor = ThreadPoolExecutor(max_workers=int(os.environ.get("RENDER_WORKERS", "1")),
                              thread_name_prefix="render")
_credit_lock = threading.Lock()


# --------------------------------------------------------------------------- startup
def _clean_title(filename: str) -> str:
    base = os.path.splitext(filename)[0]
    base = re.sub(r"^YTDown\.com_(Shorts_)?(Media_)?", "", base)
    base = re.sub(r"_\d{3}_\d+p$", "", base)
    base = re.sub(r"^[A-Za-z0-9\-]{8,12}_", "", base) if re.match(r"^[A-Za-z0-9\-]{11}_", base) else base
    return re.sub(r"[_\-]+", " ", base).strip().title()[:60] or "Untitled clip"


def seed_library():
    """Register every file in input_videos/ as a shared library clip."""
    with SessionLocal() as db:
        known = {a.path for a in db.scalars(select(Asset).where(Asset.owner_id.is_(None)))}
        for fn in sorted(os.listdir(S.LIBRARY_DIR)):
            path = os.path.join(S.LIBRARY_DIR, fn)
            if not fn.lower().endswith(S.VIDEO_EXTS) or path in known:
                continue
            asset = Asset(title=_clean_title(fn), path=path, duration=engine.probe_duration(path))
            thumb = os.path.join(S.THUMB_DIR, f"{asset.id}.jpg")
            if engine.make_thumbnail(path, thumb):
                asset.thumb = thumb
            db.add(asset)
        db.commit()


def fail_stale_jobs():
    """Jobs interrupted by a server restart are failed and their credit refunded."""
    with SessionLocal() as db:
        for v in db.scalars(select(Video).where(Video.status.in_(("queued", "processing")))):
            v.status, v.error, v.stage = "failed", "Server restarted while rendering.", "Failed"
            _refund(db, v)
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_library()
    fail_stale_jobs()
    yield
    executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Dolge Reel Studio", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=S.STATIC_DIR), name="static")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


# --------------------------------------------------------------------------- helpers
def _refund(db: Session, video: Video):
    with _credit_lock:
        if video.refunded:
            return
        video.refunded = True
        db.execute(update(User).where(User.id == video.user_id).values(credits=User.credits + 1))


def user_out(u: User):
    return {"id": u.id, "email": u.email, "name": u.name, "credits": u.credits,
            "email_verified": bool(u.email_verified), "verification_required": S.REQUIRE_VERIFIED}


def base_url(request: Request) -> str:
    """Public site address for email links. Set APP_URL in production (prevents Host-header spoofing)."""
    return S.APP_URL or str(request.base_url).rstrip("/")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def send_verification_email(db: Session, request: Request, user: User):
    raw = auth.create_email_token(db, user, "verify", dt.timedelta(hours=S.VERIFY_TTL_HOURS))
    mailer.send_verification(user.email, user.name, f"{base_url(request)}/verify?token={raw}")


def video_out(v: Video):
    return {
        "id": v.id, "title": v.title, "text": v.text, "voice": v.voice, "speed": v.speed,
        "pitch": v.pitch, "music": v.music, "caption_style": v.caption_style, "out_width": v.out_width,
        "clip_ids": [c for c in v.clip_ids.split(",") if c], "status": v.status,
        "stage": v.stage, "progress": round(v.progress, 1), "error": v.error,
        "duration": round(v.duration or 0, 1), "has_thumb": bool(v.thumb),
        "share_token": v.share_token, "created_at": v.created_at.isoformat(),
    }


def asset_out(a: Asset, uid: str):
    return {"id": a.id, "title": a.title, "duration": round(a.duration or 0, 1),
            "mine": a.owner_id == uid, "has_thumb": bool(a.thumb)}


def list_music():
    out = []
    for fn in sorted(os.listdir(S.MUSIC_DIR)):
        if fn.lower().endswith(S.MUSIC_EXTS):
            out.append({"id": fn, "title": os.path.splitext(fn)[0].replace("_", " ").title()})
    return out


def own_video(db: Session, user: User, vid: str) -> Video:
    v = db.get(Video, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "Video not found.")
    return v


def _set_cookie(resp: Response, user: User):
    resp.set_cookie(S.COOKIE_NAME, auth.make_token(user), max_age=S.TOKEN_TTL_SECONDS,
                    httponly=True, samesite="lax", secure=S.COOKIE_SECURE, path="/")


# --------------------------------------------------------------------------- schemas
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class PreviewIn(BaseModel):
    voice: str
    speed: float = Field(1.0, ge=0.75, le=1.5)
    pitch: int = Field(0, ge=-6, le=6)
    text: str = Field("", max_length=400)


class VideoIn(BaseModel):
    title: str = Field("Untitled reel", max_length=120)
    text: str = Field(min_length=10, max_length=S.MAX_STORY_CHARS)
    voice: str
    speed: float = Field(1.0, ge=0.75, le=1.5)
    pitch: int = Field(0, ge=-6, le=6)
    music: str | None = None
    caption_style: str = "cut_paper"
    quality: int = S.DEFAULT_WIDTH
    clip_ids: list[str] = Field(min_length=1, max_length=8)


class ShareIn(BaseModel):
    enabled: bool


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class RedditIn(BaseModel):
    url: str = Field(min_length=8, max_length=300)


# --------------------------------------------------------------------------- pages
def _page(name: str):
    return FileResponse(os.path.join(S.STATIC_DIR, name), headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def studio_page(request: Request, db: Session = Depends(get_db)):
    if not auth.user_from_request(request, db):
        return RedirectResponse("/login")
    return _page("studio.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request, db: Session = Depends(get_db)):
    if auth.user_from_request(request, db):
        return RedirectResponse("/")
    return _page("login.html")


@app.get("/verify", include_in_schema=False)
def verify_page():
    return _page("verify.html")


@app.get("/reset", include_in_schema=False)
def reset_page():
    return _page("reset.html")


@app.get("/share/{token}", include_in_schema=False)
def share_page(token: str):
    return _page("share.html")


# --------------------------------------------------------------------------- auth api
@app.post("/api/auth/register")
def register(data: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.rate_limit(f"register:{client_ip(request)}", 10, 3600, "Too many sign-ups from this network. Try later.")
    user = User(email=data.email.lower(), name=data.name.strip(), password_hash=auth.hash_password(data.password),
                email_verified=not S.REQUIRE_VERIFIED)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists.")
    if S.REQUIRE_VERIFIED:
        send_verification_email(db, request, user)
    _set_cookie(response, user)
    return user_out(user)


@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{data.email.lower()}"
    auth.check_login_allowed(key)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not auth.verify_password(data.password, user.password_hash):
        auth.record_login_failure(key)
        raise HTTPException(401, "Incorrect email or password.")
    auth.clear_login_failures(key)
    _set_cookie(response, user)
    return user_out(user)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(S.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(auth.current_user)):
    return user_out(user)


@app.post("/api/auth/verify-email")
def verify_email(data: TokenIn, response: Response, db: Session = Depends(get_db)):
    user = auth.consume_email_token(db, data.token, "verify")
    user.email_verified = True
    db.commit()
    _set_cookie(response, user)          # also signs them in on this device
    return user_out(user)


@app.post("/api/auth/resend-verification")
def resend_verification(request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if user.email_verified or not S.REQUIRE_VERIFIED:
        return {"ok": True, "already_verified": True}
    auth.rate_limit(f"resend:{user.id}", 3, 3600, "You can request at most 3 emails per hour.")
    send_verification_email(db, request, user)
    return {"ok": True}


@app.post("/api/auth/forgot-password")
def forgot_password(data: ForgotIn, request: Request, db: Session = Depends(get_db)):
    auth.rate_limit(f"forgot-ip:{client_ip(request)}", 10, 3600, "Too many requests. Try again later.")
    email = data.email.lower()
    auth.rate_limit(f"forgot:{email}", 3, 3600, "Too many requests for this email. Try again later.")
    user = db.scalar(select(User).where(User.email == email))
    if user and S.MAIL_ENABLED:
        raw = auth.create_email_token(db, user, "reset", dt.timedelta(minutes=S.RESET_TTL_MINUTES))
        mailer.send_password_reset(user.email, user.name, f"{base_url(request)}/reset?token={raw}")
    # same answer whether or not the account exists (no account enumeration)
    return {"ok": True, "email_enabled": S.MAIL_ENABLED}


@app.post("/api/auth/reset-password")
def reset_password(data: ResetIn, response: Response, db: Session = Depends(get_db)):
    user = auth.consume_email_token(db, data.token, "reset")
    user.password_hash = auth.hash_password(data.password)
    user.session_version = (user.session_version or 0) + 1      # log out every other device
    user.email_verified = True                                   # they proved they own the inbox
    db.commit()
    _set_cookie(response, user)
    return user_out(user)


# --------------------------------------------------------------------------- catalog
@app.get("/api/config")
def config(user: User = Depends(auth.current_user)):
    return {
        "voices": [{k: v[k] for k in ("id", "name", "emoji", "gender", "tag", "desc")} for v in S.VOICES],
        "captions": S.CAPTION_STYLES,
        "music": list_music(),
        "qualities": S.QUALITIES,
        "default_quality": S.DEFAULT_WIDTH,
        "max_duration": S.MAX_DURATION,
        "max_chars": S.MAX_STORY_CHARS,
    }


@app.get("/api/assets")
def assets(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Asset).where((Asset.owner_id.is_(None)) | (Asset.owner_id == user.id))
                      .order_by(Asset.owner_id.is_(None), Asset.created_at.desc()))
    return [asset_out(a, user.id) for a in rows]


@app.get("/api/assets/{asset_id}/thumb")
def asset_thumb(asset_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a or (a.owner_id not in (None, user.id)) or not a.thumb or not os.path.exists(a.thumb):
        raise HTTPException(404)
    return FileResponse(a.thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), user: User = Depends(auth.current_user),
                       db: Session = Depends(get_db)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in S.VIDEO_EXTS:
        raise HTTPException(400, f"Unsupported file type. Use one of: {', '.join(S.VIDEO_EXTS)}")
    asset = Asset(owner_id=user.id, title=_clean_title(file.filename or "clip")[:120], path="")
    user_dir = os.path.join(S.UPLOAD_DIR, user.id)
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, f"{asset.id}{ext}")
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > S.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File too large (max 300 MB).")
                out.write(chunk)
        asset.duration = engine.probe_duration(path)
        if asset.duration <= 0:
            raise HTTPException(400, "That file doesn't look like a playable video.")
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise
    asset.path = path
    thumb = os.path.join(S.THUMB_DIR, f"{asset.id}.jpg")
    if engine.make_thumbnail(path, thumb):
        asset.thumb = thumb
    db.add(asset)
    db.commit()
    return asset_out(asset, user.id)


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a or a.owner_id != user.id:
        raise HTTPException(404, "Clip not found.")
    for p in (a.path, a.thumb):
        if p and os.path.exists(p):
            os.remove(p)
    db.delete(a)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- voice preview
@app.post("/api/voices/preview")
def voice_preview(data: PreviewIn, user: User = Depends(auth.current_user)):
    voice = S.VOICE_BY_ID.get(data.voice)
    if not voice:
        raise HTTPException(400, "Unknown voice.")
    text = engine.clean_text(data.text)[:180] or "It was a rainy Tuesday when I found a hidden jazz cafe down an alleyway."
    path = os.path.join(S.TEMP_DIR, f"preview_{new_id()}.mp3")
    try:
        engine.synthesize(text, voice["edge"], engine.speed_to_rate(data.speed),
                          engine.pitch_to_hz(data.pitch), path, want_words=False)
        with open(path, "rb") as f:
            audio = f.read()
    except Exception as exc:
        raise HTTPException(502, f"Voice service unavailable: {exc}")
    finally:
        if os.path.exists(path):
            os.remove(path)
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- videos
def run_job(video_id: str):
    db = SessionLocal()
    try:
        v = db.get(Video, video_id)
        if not v or v.status != "queued":
            return
        v.status, v.stage, v.progress = "processing", "Starting", 1.0
        db.commit()

        ids = [c for c in v.clip_ids.split(",") if c]
        by_id = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_(ids)))}
        paths = [by_id[i].path for i in ids if i in by_id]
        if not paths:
            raise RuntimeError("The selected clips no longer exist.")
        music_path = os.path.join(S.MUSIC_DIR, v.music) if v.music else None

        out_path = os.path.join(S.OUTPUT_DIR, f"{v.id}.mp4")
        last = {"pct": 0.0}

        def progress(pct, stage):
            if pct - last["pct"] < 1 and stage == v.stage:
                return
            last["pct"] = pct
            with SessionLocal() as pdb:
                pdb.execute(update(Video).where(Video.id == video_id).values(progress=pct, stage=stage))
                pdb.commit()
            v.stage = stage

        duration, truncated = engine.render_video(
            text=v.text, out_path=out_path, voice_edge=S.VOICE_BY_ID[v.voice]["edge"], speed=v.speed,
            pitch=v.pitch, clip_paths=paths, caption_style=v.caption_style, music_path=music_path,
            progress=progress, job_id=v.id, out_width=v.out_width)

        thumb = os.path.join(S.THUMB_DIR, f"v_{v.id}.jpg")
        v.thumb = thumb if engine.make_thumbnail(out_path, thumb, at=min(1.0, duration / 2)) else None
        v.path, v.duration = out_path, duration
        v.status, v.stage, v.progress = "done", "Ready", 100.0
        if truncated:
            v.error = f"Story was longer than {S.MAX_DURATION}s, so the reel was trimmed."
        db.commit()
    except Exception as exc:
        traceback.print_exc()
        db.rollback()
        v = db.get(Video, video_id)
        if v:
            v.status, v.stage, v.error = "failed", "Failed", (str(exc) or exc.__class__.__name__)[:500]
            _refund(db, v)
            db.commit()
    finally:
        db.close()


@app.post("/api/videos")
def create_video(data: VideoIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if data.voice not in S.VOICE_BY_ID:
        raise HTTPException(400, "Unknown voice.")
    if data.caption_style not in S.CAPTION_IDS:
        raise HTTPException(400, "Unknown caption style.")
    if data.music and data.music not in {m["id"] for m in list_music()}:
        raise HTTPException(400, "Unknown soundtrack.")
    if not engine.clean_text(data.text):
        raise HTTPException(400, "Write a story first.")
    if S.REQUIRE_VERIFIED and not user.email_verified:
        raise HTTPException(403, "Please confirm your email address first. Check your inbox (and spam folder).")
    if data.quality not in S.ALLOWED_WIDTHS:
        raise HTTPException(400, "That video quality isn't available on this server.")

    clip_ids = list(dict.fromkeys(data.clip_ids))
    ok = {a.id for a in db.scalars(select(Asset).where(Asset.id.in_(clip_ids),
                                                       (Asset.owner_id.is_(None)) | (Asset.owner_id == user.id)))}
    if len(ok) != len(clip_ids):
        raise HTTPException(400, "One of the selected clips is unavailable.")

    # atomic credit deduction
    with _credit_lock:
        res = db.execute(update(User).where(User.id == user.id, User.credits > 0)
                         .values(credits=User.credits - 1))
        if res.rowcount == 0:
            db.rollback()
            raise HTTPException(402, "You're out of credits.")
        video = Video(user_id=user.id, title=data.title.strip() or "Untitled reel", text=data.text,
                      voice=data.voice, speed=data.speed, pitch=data.pitch, music=data.music,
                      caption_style=data.caption_style, out_width=data.quality,
                      clip_ids=",".join(clip_ids))
        db.add(video)
        db.commit()
    executor.submit(run_job, video.id)
    credits = db.scalar(select(User.credits).where(User.id == user.id))
    return {"video": video_out(video), "credits": credits}


@app.get("/api/videos")
def list_videos(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Video).where(Video.user_id == user.id).order_by(Video.created_at.desc()).limit(100))
    return [video_out(v) for v in rows]


@app.get("/api/videos/{vid}")
def get_video(vid: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    v = own_video(db, user, vid)
    return {"video": video_out(v), "credits": db.get(User, user.id).credits}


@app.get("/api/videos/{vid}/file")
def video_file(vid: str, download: int = 0, user: User = Depends(auth.current_user),
               db: Session = Depends(get_db)):
    v = own_video(db, user, vid)
    if v.status != "done" or not v.path or not os.path.exists(v.path):
        raise HTTPException(404, "Video isn't ready.")
    name = re.sub(r"[^\w\- ]", "", v.title).strip() or "reel"
    return FileResponse(v.path, media_type="video/mp4", filename=f"{name}.mp4",
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/videos/{vid}/thumb")
def video_thumb(vid: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    v = own_video(db, user, vid)
    if not v.thumb or not os.path.exists(v.thumb):
        raise HTTPException(404)
    return FileResponse(v.thumb, media_type="image/jpeg")


@app.delete("/api/videos/{vid}")
def delete_video(vid: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    v = own_video(db, user, vid)
    if v.status in ("queued", "processing"):
        raise HTTPException(409, "Wait for the render to finish first.")
    for p in (v.path, v.thumb):
        if p and os.path.exists(p):
            os.remove(p)
    db.delete(v)
    db.commit()
    return {"ok": True}


@app.post("/api/videos/{vid}/share")
def share_video(vid: str, data: ShareIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    v = own_video(db, user, vid)
    if v.status != "done":
        raise HTTPException(409, "Only finished videos can be published.")
    v.share_token = (v.share_token or secrets.token_urlsafe(16)) if data.enabled else None
    db.commit()
    return video_out(v)


# --------------------------------------------------------------------------- reddit import
@app.post("/api/reddit/import")
def reddit_import(data: RedditIn, user: User = Depends(auth.current_user)):
    auth.rate_limit(f"reddit:{user.id}", 20, 3600, "You've imported a lot of stories this hour. Try again later.")
    try:
        return reddit.import_story(data.url)
    except reddit.RedditError as exc:
        raise HTTPException(400, str(exc))


# --------------------------------------------------------------------------- public share
def _shared(db: Session, token: str) -> Video:
    v = db.scalar(select(Video).where(Video.share_token == token, Video.status == "done"))
    if not v or not v.path or not os.path.exists(v.path):
        raise HTTPException(404, "This reel isn't available.")
    return v


@app.get("/api/share/{token}")
def share_info(token: str, db: Session = Depends(get_db)):
    v = _shared(db, token)
    return {"title": v.title, "duration": round(v.duration or 0, 1), "by": v.user.name}


@app.get("/api/share/{token}/file")
def share_file(token: str, db: Session = Depends(get_db)):
    v = _shared(db, token)
    return FileResponse(v.path, media_type="video/mp4")
