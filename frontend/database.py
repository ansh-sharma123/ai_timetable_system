"""
ChronoGen — Database Layer (SQLAlchemy ORM)
Upgraded from raw sqlite3 to SQLAlchemy for a proper relational data model.
Adds a PasswordResetToken model with expiry for secure password resets.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash

# ─── Engine & Session ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# ─── Models ──────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PasswordResetToken(Base):
    """Secure, expiring password-reset tokens stored in the DB."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    token = Column(String(128), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Integer, default=0)   # 0 = unused, 1 = consumed

    def is_valid(self):
        return (not self.used) and (datetime.now(timezone.utc) < self.expires_at.replace(tzinfo=timezone.utc))


# ─── DB Init ─────────────────────────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(bind=engine)


# ─── User CRUD ───────────────────────────────────────────────────────────────
def create_user(email: str, password: str) -> bool:
    db = SessionLocal()
    try:
        hashed = generate_password_hash(password)
        user = User(email=email, password=hashed)
        db.add(user)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def check_user(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user and check_password_hash(user.password, password):
            return (user.id, user.email, user.password)
        return None
    finally:
        db.close()


def get_user_by_email(email: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return (user.id, user.email, user.password)
        return None
    finally:
        db.close()


def update_password(email: str, new_password: str) -> bool:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False
        user.password = generate_password_hash(new_password)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


# ─── Token CRUD ──────────────────────────────────────────────────────────────
TOKEN_EXPIRY_MINUTES = 30


def create_reset_token(email: str) -> str:
    """Generate a cryptographically secure reset token, store it, return it."""
    db = SessionLocal()
    try:
        # Invalidate any previous tokens for this email
        db.query(PasswordResetToken).filter(
            PasswordResetToken.email == email
        ).delete()

        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
        reset = PasswordResetToken(email=email, token=token, expires_at=expires_at)
        db.add(reset)
        db.commit()
        return token
    finally:
        db.close()


def verify_reset_token(token: str):
    """Return the email if token is valid & unused, else None."""
    db = SessionLocal()
    try:
        record = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == token
        ).first()
        if record and record.is_valid():
            return record.email
        return None
    finally:
        db.close()


def consume_reset_token(token: str) -> bool:
    """Mark token as used so it cannot be re-used."""
    db = SessionLocal()
    try:
        record = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == token
        ).first()
        if record:
            record.used = 1
            db.commit()
            return True
        return False
    finally:
        db.close()