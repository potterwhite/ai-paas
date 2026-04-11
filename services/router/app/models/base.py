"""SQLAlchemy base and models."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ApiKeyRecord(Base):
    """Persisted API keys."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_name = Column(String(100), nullable=False)
    key_value = Column(String(255), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaskRecord(Base):
    """Persisted task state for recovery and inspection."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    celery_task_id = Column(String(255), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # llm | whisper | comfyui | switch
    status = Column(String(20), default="pending")  # pending | running | completed | failed
    payload = Column(Text, default="")
    result = Column(Text, default="")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


def init_db(engine):
    """Create all tables."""
    Base.metadata.create_all(engine)
