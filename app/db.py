"""SQLAlchemy models and session handling (SQLite)."""
import datetime as dt
import uuid

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import settings as S

IS_SQLITE = S.DB_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(S.DB_URL, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    engine = create_engine(S.DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now():
    return dt.datetime.now(dt.timezone.utc)


def new_id():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    credits: Mapped[int] = mapped_column(Integer, default=S.SIGNUP_CREDITS)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Asset(Base):
    """A background clip: shared library (owner_id NULL) or a user upload."""
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    path: Mapped[str] = mapped_column(Text)
    thumb: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(String(32))
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    pitch: Mapped[int] = mapped_column(Integer, default=0)
    music: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caption_style: Mapped[str] = mapped_column(String(32), default="cut_paper")
    clip_ids: Mapped[str] = mapped_column(Text, default="")   # comma separated asset ids, ordered
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|processing|done|failed
    stage: Mapped[str] = mapped_column(String(80), default="Queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumb: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    share_token: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True, index=True)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User] = relationship()


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
