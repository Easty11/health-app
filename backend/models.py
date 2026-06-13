from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class UserIntegration(Base):
    __tablename__ = "user_integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Fernet-encrypted API key stored as base64 token
    api_key_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserKnowledge(Base):
    __tablename__ = "user_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserKnowledgeEntry(Base):
    __tablename__ = "user_knowledge_entries"
    __table_args__ = (
        Index("ix_uke_user_type_active", "user_id", "type", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # schedule_item | load_context | event | injury | preference
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # unique identifier within type+user, e.g. "physio_2026_06", "weekly_split"
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    # onboarding | chat | system
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    added_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("user_knowledge_entries.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"), default=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class DailyCheckIn(Base):
    __tablename__ = "daily_check_ins"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_checkin_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sleep_quality: Mapped[int] = mapped_column(Integer, nullable=False)       # 1-10
    fatigue: Mapped[int] = mapped_column(Integer, nullable=False)             # 1-10
    shoulder_pain: Mapped[int] = mapped_column(Integer, nullable=False)       # 0-10
    motivation: Mapped[int] = mapped_column(Integer, nullable=False)          # 1-10
    rugby_session_yesterday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HealthConnectSync(Base):
    __tablename__ = "health_connect_syncs"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_hc_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps: Mapped[int | None] = mapped_column(Integer)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float)
    hrv_rmssd: Mapped[float | None] = mapped_column(Float)

    sleep_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    deep_sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    rem_sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    light_sleep_minutes: Mapped[int | None] = mapped_column(Integer)

    active_calories: Mapped[int | None] = mapped_column(Integer)
    distance_meters: Mapped[int | None] = mapped_column(Integer)
    oxygen_saturation: Mapped[float | None] = mapped_column(Float)
    respiratory_rate: Mapped[float | None] = mapped_column(Float)


class SamsungHRVReading(Base):
    __tablename__ = "samsung_hrv_readings"
    __table_args__ = (UniqueConstraint("user_id", "captured_at", name="uq_samsung_hrv_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    hrv_ms: Mapped[float | None] = mapped_column(Float)
    sleep_hr_bpm: Mapped[int | None] = mapped_column(Integer)
    respiratory_rate: Mapped[float | None] = mapped_column(Float)
    sleep_efficiency_pct: Mapped[int | None] = mapped_column(Integer)
    actual_sleep_time_minutes: Mapped[int | None] = mapped_column(Integer)
    sleep_duration_home_tile: Mapped[str | None] = mapped_column(String(20))
    bedtime: Mapped[str | None] = mapped_column(String(10))
    wake_time: Mapped[str | None] = mapped_column(String(10))
    awake_minutes: Mapped[int | None] = mapped_column(Integer)
    rem_minutes: Mapped[int | None] = mapped_column(Integer)
    light_minutes: Mapped[int | None] = mapped_column(Integer)
    deep_minutes: Mapped[int | None] = mapped_column(Integer)
    awake_pct: Mapped[int | None] = mapped_column(Integer)
    rem_pct: Mapped[int | None] = mapped_column(Integer)
    light_pct: Mapped[int | None] = mapped_column(Integer)
    deep_pct: Mapped[int | None] = mapped_column(Integer)
    total_sleep_time_minutes: Mapped[int | None] = mapped_column(Integer)
    spo2_average_pct: Mapped[float | None] = mapped_column(Float)
    extraction_method: Mapped[str] = mapped_column(String(50), server_default=text("'accessibility'"))
