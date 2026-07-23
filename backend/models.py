from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
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
    # Fernet-encrypted credential payload (base64). TEXT, not varchar — v4 OAuth
    # tokens (long JWT access_token + refresh_token) exceed 512 chars encrypted.
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
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
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)



class DailyRecord(Base):
    """
    New two-moment daily record (AM check-in + nightly close-out).
    Replaces DailyCheckIn as the primary capture surface.
    DailyCheckIn is retained for backward-compat with existing routes.

    Append-only: once am_timestamp or pm_timestamp is set, those fields
    are never overwritten. naive_baseline and passive_* are stored at AM
    capture time and must never be recomputed later.
    """
    __tablename__ = "daily_records"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_record_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # ── AM check-in ────────────────────────────────────────────────────────────
    am_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    morning_readiness: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1–5, primary OUTCOME
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)       # 1–5
    fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)             # 0–10 (kept for baseline)
    soreness: Mapped[dict | None] = mapped_column(JSON, nullable=True)              # {"shoulder":2, "hamstring":1}
    motivation: Mapped[int | None] = mapped_column(Integer, nullable=True)          # 0–10 (kept for baseline)
    life_load: Mapped[int | None] = mapped_column(Integer, nullable=True)           # 1–5
    alcohol_units: Mapped[int | None] = mapped_column(Integer, nullable=True)       # conditional
    alcohol_finish_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "22:30"

    # ── Nightly close-out ──────────────────────────────────────────────────────
    pm_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    today_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 1–5, OUTCOME (all days)
    session_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 1–5, conditional (training days)
    session_rpe: Mapped[float | None] = mapped_column(Float, nullable=True)         # 0–10, training days
    mindfulness_occurred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # read from HC
    mindfulness_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Computed at AM capture time — NEVER recomputed ─────────────────────────
    naive_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)      # old formula frozen
    model_forecast: Mapped[float | None] = mapped_column(Float, nullable=True)      # what model showed
    model_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)    # n_valid_channels / maturity

    # ── Passive refs snapshotted at AM capture time ────────────────────────────
    passive_hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    passive_sleep_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── CBT-I sleep diary (AM moment) ──────────────────────────────────────────
    # Additive, nullable, sparse by design: rendered/captured only while an open
    # cbti_block exists, legended by cbti_prescription.effective_from/to (#108).
    # Same freeze contract as naive_baseline — set at AM write, never recomputed.
    # got_into_bed and lights_out are DISTINCT moments the diary separates: the
    # first is when you got into bed, the second when you tried to sleep. Sleep
    # efficiency is computed from lights_out (the SE window opens there), so only
    # lights_out was imported in phase 1 — historical rows carry got_into_bed NULL.
    got_into_bed: Mapped[str | None] = mapped_column(String(5), nullable=True)        # "22:20"
    lights_out: Mapped[str | None] = mapped_column(String(5), nullable=True)          # "22:36"
    sleep_latency_min: Mapped[int | None] = mapped_column(Integer, nullable=True)     # SOL; device systematically wrong — never prefilled
    waso_min: Mapped[int | None] = mapped_column(Integer, nullable=True)              # wake after sleep onset; never prefilled
    night_wakings_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_wake: Mapped[str | None] = mapped_column(String(5), nullable=True)          # "05:00"
    out_of_bed: Mapped[str | None] = mapped_column(String(5), nullable=True)          # "05:10"
    # naps_min is logged at PM on date D but belongs to the night terminating on
    # wake-date D+1. Stored at PM on D; the titration engine reads it from (date - 1).
    # Silent when wrong — the attribution lives here, not only in the engine.
    naps_min: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Logged PM on date D; belongs to night terminating D+1. Engine reads from (date-1).",
    )
    diary_se_pct: Mapped[float | None] = mapped_column(Float, nullable=True)          # frozen at AM; same contract as naive_baseline
    diary_tst_min: Mapped[int | None] = mapped_column(Integer, nullable=True)         # frozen at AM; same contract as naive_baseline


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


class HealthConnectRecordSource(Base):
    """Per-record writer identity captured from /health-connect/sync BEFORE the
    night is collapsed by _aggregate_day. One row per inbound HC record.

    Exists because health_connect_syncs is one aggregated row per (user, date):
    a single night spans multiple writers (DECISIONS_LOG #35 — 286 sleep
    dup-groups span 2+ apps), so source identity has to be preserved at record
    granularity to survive aggregation. This is the backend enabler for
    source-priority dedup (F1, #35/#36); it does not itself filter.

    source_package stays column-nullable (the inbound request field is optional —
    current HCA builds send no dataOrigin), but _capture_record_sources coalesces
    a missing identity to the literal 'unknown' before insert, so a value always
    flows. It is part of the unique key: two apps writing the same
    (type, timestamp) persist as two rows rather than one overwriting the other —
    the multi-writer signal F1 needs (supersedes #37's "natural key collapses
    them" caveat). The 'unknown' sentinel also keeps re-syncs idempotent: a real
    NULL is UNIQUE-distinct on both SQLite and Postgres, so identity-less records
    would otherwise duplicate every sync.
    """
    __tablename__ = "health_connect_record_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "record_type", "record_start", "source_package", name="uq_hc_record_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)   # 'sleep','hrv','heart_rate',...
    record_start: Mapped[str] = mapped_column(String(40), nullable=False)  # record's primary timestamp (ISO)
    source_package: Mapped[str | None] = mapped_column(String(255))        # coalesced to 'unknown' at capture; nullable column
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CBTIBlock(Base):
    """A single CBT-I titration block (#108). The module is block-structured, not a
    single arc: a block opens with the in-flight prescription (decision='adopt') and
    closes (decision='close'); the ledger persists permanently after closure and is
    the baseline any later block titrates against.

    Append-only. The ONLY permitted UPDATE is setting closed_on / close_reason /
    exit_tst_min / exit_se_pct at closure — no other column is ever rewritten. There
    is no DB trigger enforcing this (the repo has no such precedent and the test path
    builds via create_all, not migrations); it is a model+application invariant, the
    same discipline DailyRecord's AM fields carry.
    """
    __tablename__ = "cbti_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opened_on: Mapped[date] = mapped_column(Date, nullable=False)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)          # UPDATE-once at closure
    wake_anchor: Mapped[str] = mapped_column(String(5), nullable=False)          # "05:00"
    open_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)        # UPDATE-once at closure
    exit_tst_min: Mapped[int | None] = mapped_column(Integer, nullable=True)     # UPDATE-once at closure
    exit_se_pct: Mapped[float | None] = mapped_column(Float, nullable=True)      # UPDATE-once at closure
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CBTIPrescription(Base):
    """One prescribed sleep window within a block (#107). Titration controls on total
    sleep time with sleep efficiency as a FLOOR (>=85%), not SE as the target: window =
    rolling mean TST + buffer, exit on TST plateau, SE held >=85%.

    Append-only. The ONLY permitted UPDATEs are setting effective_to (when a successor
    prescription takes over) and superseded_by (self-referential pointer to that
    successor). basis_* / decision / rationale are frozen at authorship. Same
    no-DB-trigger, model+application-invariant discipline as CBTIBlock.
    """
    __tablename__ = "cbti_prescriptions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('adopt','extend','hold','compress','close')",
            name="ck_cbti_prescription_decision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("cbti_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)       # UPDATE-once when superseded
    prescribed_lights_out: Mapped[str] = mapped_column(String(5), nullable=False)   # "22:36"
    wake_anchor: Mapped[str] = mapped_column(String(5), nullable=False)          # "05:00"
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)            # adopt|extend|hold|compress|close
    basis_tst_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis_se_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis_nights_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Adherence-source composition of the basis window. Written at the same moment
    # as basis_nights_n, never backfilled — a prescription whose adherence rested
    # on self-report must say so on its own row, because a later reader comparing
    # prescriptions cannot otherwise tell a device-verified basis from a diary one.
    # n_samsung + n_diary <= basis_nights_n (a night with neither contributes to
    # neither count).
    basis_n_samsung: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis_n_diary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Basis nights ADMITTED with alcohol unrecorded — assumed clean, not verified
    # clean. Recorded so the ledger states how much of a decision rested on an
    # assumption; provenance, independent of how the predicate is set.
    basis_n_alcohol_unknown: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mean actual TIB across the basis nights minus the prescribed window.
    # INSTRUMENTED, NOT GATED — two candidate gates over this quantity were built
    # and rejected on evidence (see cbti/engine.py). Recorded so a threshold can
    # eventually be set against a distribution across blocks rather than one.
    basis_tib_over_run_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis_window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis_window_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    excluded_nights: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # reason-tagged: {"2026-04-02":"alcohol",...}
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("cbti_prescriptions.id", ondelete="SET NULL"), nullable=True   # UPDATE-once when superseded
    )


class AerobicSession(Base):
    """Aerobic sessions for ACWR load tracking — seeded from Polar Flow export, future HC."""
    __tablename__ = "aerobic_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "source_session_id", name="uq_aerobic_session_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)                # 'polar_flow_export', 'health_connect'
    source_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)   # original ID from source system
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sport_id: Mapped[str | None] = mapped_column(String(100), nullable=True)       # source system sport ID
    sport_name: Mapped[str | None] = mapped_column(String(100), nullable=True)     # decoded sport name
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cardio_load: Mapped[float | None] = mapped_column(Float, nullable=True)        # Polar cardio load (ACWR proxy)
    muscle_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    z1_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    z2_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    z3_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    z4_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    z5_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # passive_overnight | calibration | session
    context: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'passive_overnight'"))


class CapabilityState(Base):
    """
    Adaptive Exposure Engine — "map contents" (spec §3, v2.1 split).

    The axis list (engine/taxonomy.py) says which capability regions exist; this
    table says where THIS user stands on each one. The map self-builds one probe
    per session (§2.1): a row is written/updated only when the adaptation loop
    tags a logged session (engine/adaptation.py), so a missing row == untested.

    Readable per-side (§F symmetry layer): one row per (region, side), where side
    is 'bilateral' for non-lateralised regions or 'left' / 'right' otherwise.

    source/confidence-tagged per the device-agnostic schema rule (CLAUDE.md).
    Standalone table for now; folds into `health_events` when that schema lands
    (DECISIONS_LOG — Adaptive Exposure Engine entry). Capability state is
    self-reported through the education idiom (spec §12), never a wearable metric.
    """
    __tablename__ = "capability_state"
    __table_args__ = (
        UniqueConstraint("user_id", "region_key", "side", name="uq_capability_user_region_side"),
        Index("ix_capability_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    region_key: Mapped[str] = mapped_column(String(100), nullable=False)   # matches taxonomy Region.key
    side: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'bilateral'"))
    # untested | pass | deficient | fortifying
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'untested'"))
    # probe | fortify | history | manual — how this row's status was established
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # last response tag, revealed-signal text, stand-down flags, free notes
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_probed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LabReport(Base):
    """Collection-event envelope for observed labs (DECISIONS_LOG #52). One row per
    draw/report; `LabResult` rows hang off it per marker. Not `user_knowledge_entries`
    (declared facts only) and not the deferred `health_events` spine (#43) — a
    concrete domain table for a concrete observational series.
    """
    __tablename__ = "lab_reports"
    __table_args__ = (
        Index("ix_lab_report_user_collected", "user_id", "collected_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lab_name: Mapped[str] = mapped_column(String(255), nullable=False)
    lab_provider_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    panel_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    accreditation_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referrer_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    collected_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_created_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_comments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # sonic_dx_extract | full_report | unknown | verbal
    source_completeness: Mapped[str] = mapped_column(String(50), nullable=False)
    # file_extraction | verbal
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_doc_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabResult(Base):
    """One row per marker per `LabReport` (DECISIONS_LOG #52). `current_state` reads
    the latest row per (user, marker_canonical) via join to `LabReport.collected_date`
    — compute-on-read, no supersede column here. `marker_canonical` is nullable:
    unmapped raw names surface as an interpretation-layer skip, not a placeholder
    canonical id (DECISIONS_LOG #58).
    """
    __tablename__ = "lab_results"
    __table_args__ = (
        UniqueConstraint("lab_report_id", "marker_name_raw", name="uq_lab_result_report_marker_raw"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lab_report_id: Mapped[int] = mapped_column(ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    marker_name_raw: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # as extracted, #58
    marker_canonical: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # mapped id, #50/#58
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)  # #58
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_operator: Mapped[str | None] = mapped_column(String(1), nullable=True)  # '<' | '>'
    value_qualitative: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_canonical: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_low_exclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    ref_high_exclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    lab_flag: Mapped[str | None] = mapped_column(String(10), nullable=True)
    computed_flag: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HevyExerciseTemplate(Base):
    """Synced Hevy exercise templates — defaults + per-user customs (DECISIONS_LOG #61).

    Persisted so the provisioning path never sources exercise-template ids live.
    Keyed on the Hevy `id` alone: defaults are 8-char UPPERCASE hex global
    singletons, customs are lowercase UUIDs (globally unique) — no id reuse across
    the two spaces (confirmed live, GET /v1/exercise_templates), so no composite key
    is needed. `String(64)` absorbs both id shapes (max observed len 36).

    Upsert-only: the Hevy API cannot delete templates, so there is nothing to
    reconcile. `owner_user_id` is app `users.id` (NULL for defaults) — the template
    object itself carries no owner field (confirmed live), so ownership is assigned
    at sync time from the key's user for `is_custom` rows. Resolution is
    default-wins on title collision (DECISIONS_LOG #60).
    """
    __tablename__ = "hevy_exercise_templates"
    __table_args__ = (
        Index("ix_hevy_exercise_templates_title", "title"),
        Index("ix_hevy_exercise_templates_owner_user_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Hevy id — hex (default) or UUID (custom)
    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_custom: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    primary_muscle_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    secondary_muscle_groups: Mapped[list | None] = mapped_column(JSON, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # App-owned annotation (DECISIONS_LOG #NEXT): exercise-level laterality, NOT
    # derivable from the region taxonomy and load-bearing for plan↔log
    # reconciliation (a unilateral movement is logged as two sided Hevy entries).
    # bilateral | unilateral | alternating | NULL(untagged). Deliberately NOT
    # assigned by `_upsert_template`, so a Hevy resync preserves it (the whole
    # reason tags live off the synced columns).
    laterality: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Three-state tag coverage (DECISIONS_LOG #76). NULL = never adjudicated
    # (untagged → keyword fallback); NOT NULL = human-confirmed adjudication:
    # with ≥1 exercise_region_tags row → TAGGED, with zero rows → deliberate
    # NO-PATTERN (the movement demonstrates no screenable taxonomy region, e.g.
    # an isolation or a joint-level strength lift v0 has no axis for). Set only
    # by the --confirm seed. Like `laterality`, never assigned by
    # `_upsert_template`, so a resync preserves it.
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExerciseRegionTag(Base):
    """App-owned exercise→taxonomy-region annotation (DECISIONS_LOG #NEXT).

    Deliberately a SEPARATE table from `hevy_exercise_templates`, which is
    upsert-from-Hevy-sync (`_upsert_template`) and clobber-exposed on every
    resync. Keeping tags here cleanly splits Hevy-owned data from app-owned
    annotation, and a resync can never touch a row it does not write.

    Many-to-many by design: some movements legitimately load more than one
    region (Suitcase Carry = carry + anti_lateral_flexion). `role` makes the
    primacy explicit and reviewable — the current keyword matcher's bug is
    UNINTENTIONAL multi-match with no primacy, not multi-match per se.

    `region_key` is validated against `engine/taxonomy.py` at write time
    (fail-closed — an orphan key is refused, never stored). Plane and capacity
    are NOT stored: `Region` already carries them and region_key derives both;
    duplicating them would create a drift surface for no gain.
    """
    __tablename__ = "exercise_region_tags"
    __table_args__ = (
        Index("ix_exercise_region_tags_region_key", "region_key"),
    )

    hevy_exercise_template_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hevy_exercise_templates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    region_key: Mapped[str] = mapped_column(String(100), primary_key=True)  # validated vs taxonomy Region.key
    # primary | secondary — explicit primacy for deliberate multi-region tags
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'primary'"))
    # mirrors engine.taxonomy.TAXONOMY_VERSION (currently 'v0')
    taxonomy_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'v0'"))
    # llm_proposed | human_confirmed — the labs-style extract→confirm provenance
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'llm_proposed'"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FortificationProfile(Base):
    """
    Adaptive Exposure Engine — fortification-target profile (spec §9).

    Structured, per-user object that replaces the hardcoded injury string in
    context_builder. One row per user, so multi-user scale falls out for free.
    `probe_queue` is COMPUTED at request time (spec §4), never stored.
    """
    __tablename__ = "fortification_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_fortification_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    floor: Mapped[dict | None] = mapped_column(JSON, nullable=True)          # {demonstrated, tag: clean|managed}
    ceiling: Mapped[str | None] = mapped_column(String(20), nullable=True)   # breadth | peak
    horizon: Mapped[str | None] = mapped_column(String(30), nullable=True)   # life | event-dated
    horizon_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_target: Mapped[str | None] = mapped_column(String(100), nullable=True)   # region key or descriptor
    primary_target_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    live_signals: Mapped[list | None] = mapped_column(JSON, nullable=True)   # [{signal, side, branch_param, status}]
    hard_stops: Mapped[list | None] = mapped_column(JSON, nullable=True)     # [{region_key|pattern, side, reason}]
    vehicle_bias: Mapped[list | None] = mapped_column(JSON, nullable=True)   # ranked vehicle keys for the target
    # standing Probe allocation — never drops to zero (spec §2)
    probe_budget: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.25"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
