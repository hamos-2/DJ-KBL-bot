"""SQLAlchemy ORM models for the KBL Bot database."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


class User(Base):
    """Represents a KakaoTalk user registered with the KBL Bot."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kakao_user_key_hmac: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    encrypted_kakao_user_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    favorite_team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Game(Base):
    """Represents a KBL game with scheduling, live, and final states."""

    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    home_team: Mapped[str] = mapped_column(String(50), nullable=False)
    away_team: Mapped[str] = mapped_column(String(50), nullable=False)
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    game_clock: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    arena: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    game_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SCHEDULED"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserAccountState(Base):
    """Durable PostgreSQL backing store for user preferences, prediction points, and streak."""

    __tablename__ = "user_account_states"

    user_hmac: Mapped[str] = mapped_column(String(64), primary_key=True)
    favorite_players_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notifications_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    prediction_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prediction_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PredictionVote(Base):
    """Durable record of user match predictions and settlement status."""

    __tablename__ = "prediction_votes"
    __table_args__ = (
        UniqueConstraint("user_hmac", "game_id", name="uq_prediction_vote_user_game"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    selected_team: Mapped[str] = mapped_column(String(50), nullable=False)
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_hit: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
