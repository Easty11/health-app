from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

# Raw-payload columns want JSONB on Postgres (the deployed engine — indexable,
# binary-stored) but must still build on the SQLite the test suite runs against
# (conftest `create_all` on an in-memory engine). `JSON().with_variant(...)`
# renders JSONB under Postgres and generic JSON everywhere else — one column type,
# both engines, no per-test dialect branching.
_JSONB = JSON().with_variant(JSONB, "postgresql")


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
    # Per-user catalogue-freshness marker (DECISIONS_LOG #211 / Q75). Stamped by
    # `sync_one_user` on a completed template pull; read by the staleness gate on the
    # workout-fetch path. Deliberately per (user, provider) rather than an aggregate
    # over `hevy_exercise_templates.synced_at`: that column is per-row and its default
    # rows are re-stamped by ANY user's sync, so an aggregate reads "fresh" off another
    # user's run while this user's own customs are stale — wrong once multi-user is live.
    # NULL = never synced -> treated as stale (a first fetch triggers a sync).
    templates_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    # Declared set: onboarding | chat | system | api. A CHANNEL axis -- how did
    # this arrive -- never who was behind it; authority lives in `asserted_by`
    # (#227). Validated at write against `SOURCE_VALUES` in routers/knowledge.py.
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
    # LIVE as of #219 — `cbti.replay.load_nights` now performs that read, so this is a
    # description of the code rather than an unhonoured contract. It was silent-when-wrong
    # for as long as the two disagreed; keep them in step.
    naps_min: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Logged PM on date D; belongs to night terminating D+1. Engine reads from (date-1).",
    )
    diary_se_pct: Mapped[float | None] = mapped_column(Float, nullable=True)          # frozen at AM; same contract as naive_baseline
    diary_tst_min: Mapped[int | None] = mapped_column(Integer, nullable=True)         # frozen at AM; same contract as naive_baseline
    # Waking-cause decomposition of night_wakings_n (nocturia/pain/spontaneous).
    # OBSERVATIONAL ONLY — the titration engine must not read these (grep -rn
    # 'wakings_' cbti/ stays empty). No sum constraint: recall is imperfect and
    # enforcement would block submission; consistency is surfaced, not enforced.
    wakings_nocturia_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wakings_pain_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wakings_spontaneous_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-text context that doesn't fit a structured field (an off night, a carnival
    # alarm). Separate AM/PM columns because the two submits are independent and a
    # shared column would clobber. Observational — read by no engine code.
    am_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pm_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


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

    source_package stays column-nullable, but not for the reason this docstring
    used to give. It read "current HCA builds send no dataOrigin", which was true
    when written (#36, 2026-06-29) and is now STALE: Health Connect began sending
    dataOrigin at 2026-07-05 05:51:53Z — a clean cutover eight minutes after the
    last identity-less write (05:43:14Z), nothing unattributed since — and the
    live health_connect_record_sources rows carry real packages. Identity DOES
    arrive (mirrors the correction at routers/health_connect.py; #188).

    It stays nullable because identity is not GUARANTEED, which is a different
    claim: 3,533 heart_rate records predate the cutover, carry no identity, and
    never will, so _capture_record_sources still coalesces a missing identity to
    the literal 'unknown' before insert — the sentinel stays load-bearing and a
    value always flows. It is part of the unique key: two apps writing the same
    (type, timestamp) persist as two rows rather than one overwriting the other —
    the multi-writer signal F1 needs (supersedes #37's "natural key collapses
    them" caveat). The 'unknown' sentinel also keeps re-syncs idempotent: a real
    NULL is UNIQUE-distinct on both SQLite and Postgres, so identity-less records
    would otherwise duplicate every sync. That same key property is why the
    cutover forked 10,406 heart_rate rows into 'unknown'/identified twins (#188).
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
    # Basis nights FLAGGED (in the basis, not dropped) — today only #253's excused
    # recorded-alcohol nights. <= basis_nights_n; written at authorship, never backfilled.
    basis_n_flagged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The per-night ledger, snapshotted at accept: one row per evaluated night in the
    # cycle window — {date, status(included|flagged|excluded), reason, sleep_efficiency,
    # total_sleep, evidence}. Persisted so a close-out states why each night was counted
    # or dropped WITHOUT recomputing against a since-moved ruleset (Brief B step 2).
    basis_ledger: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The ruleset the ledger above was produced under (cbti/engine.RULESET_VERSION),
    # frozen on the row so a stored ledger stays reproducible against its own rules.
    ruleset_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("cbti_prescriptions.id", ondelete="SET NULL"), nullable=True   # UPDATE-once when superseded
    )


class CBTIISI(Base):
    """Insomnia Severity Index administration (Morin) — the outcome measure a block is
    judged by. Stored as the SEVEN items (the record) plus the tool's reported total (a
    fact about the tool, not about us); the canonical total is DERIVED on read, never
    stored. A total cannot be decomposed later, and item-level distinguishes a sleep
    change (items 1-3) from a distress change (items 6-7) — different results.

    `block_id` is nullable: a screening or between-block administration belongs to no
    block. Unique on (block_id, timepoint) — one baseline/mid/exit per block; NULL
    block_ids do not collide (NULL != NULL), so screenings are unconstrained.
    """
    __tablename__ = "cbti_isi"
    __table_args__ = (
        UniqueConstraint("block_id", "timepoint", name="uq_cbti_isi_block_timepoint"),
        CheckConstraint("timepoint IN ('baseline','mid','exit')", name="ck_cbti_isi_timepoint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SET NULL, not CASCADE: the ISI is the outcome record and must survive even a block
    # deletion (blocks are append-only and never deleted, so this is belt-and-braces).
    block_id: Mapped[int | None] = mapped_column(
        ForeignKey("cbti_blocks.id", ondelete="SET NULL"), nullable=True, index=True)
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timepoint: Mapped[str] = mapped_column(String(10), nullable=False)   # baseline | mid | exit
    item_1: Mapped[int] = mapped_column(Integer, nullable=False)
    item_2: Mapped[int] = mapped_column(Integer, nullable=False)
    item_3: Mapped[int] = mapped_column(Integer, nullable=False)
    item_4: Mapped[int] = mapped_column(Integer, nullable=False)
    item_5: Mapped[int] = mapped_column(Integer, nullable=False)
    item_6: Mapped[int] = mapped_column(Integer, nullable=False)
    item_7: Mapped[int] = mapped_column(Integer, nullable=False)
    total_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)   # what the tool returned
    instrument: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'ISI'"))
    administered_via: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def canonical_total(self) -> int:
        """Sum of the seven items — the canonical ISI total, derived not stored. May
        differ from total_reported when the administering tool anchors differently."""
        return (self.item_1 + self.item_2 + self.item_3 + self.item_4
                + self.item_5 + self.item_6 + self.item_7)


class AerobicSession(Base):
    """Aerobic sessions — the metabolic-window load source (Edwards TRIMP → load_events →
    Banister, #251); seeded from Polar Flow export, future HC. (Formerly the legacy ACWR
    input; that readout was retired #255.)"""
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
    cardio_load: Mapped[float | None] = mapped_column(Float, nullable=True)        # Polar-native cardio load
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


class HrvReading(Base):
    """Source-agnostic nightly HRV summary — one row per (user, night, source).

    Deliberately NOT a generalisation of `samsung_hrv_readings`, which conflates HRV
    with Samsung sleep architecture (see DECISIONS_LOG — Garmin HRV ingestion). This
    table carries only HRV: the nightly RMSSD average plus the Garmin-richer fields
    (status band + baseline range + weekly average) that Samsung does not supply and
    which stay NULL for nightly-only sources. The 5-min RMSSD series lives in the
    child `hrv_samples` (Garmin populates it; Samsung populates none).

    `source` tags provenance ('garmin', later 'samsung'); the unique key is per
    (user, night, source) so two sources on the same night coexist and read-time
    arbitration (`reads/recovery_reads.py`) picks the canonical one — the same
    order-independent, never-persisted pattern as `reads/aerobic_reads.py`.
    """
    __tablename__ = "hrv_readings"
    __table_args__ = (
        UniqueConstraint("user_id", "captured_at", "source", name="uq_hrv_reading_user_date_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)   # the night
    source: Mapped[str] = mapped_column(String(50), nullable=False)               # 'garmin', later 'samsung'
    rmssd_ms: Mapped[float | None] = mapped_column(Float)                         # nightly average RMSSD
    # Garmin-richer, nullable for nightly-only sources.
    status: Mapped[str | None] = mapped_column(String(30))                        # e.g. 'BALANCED', 'LOW'
    baseline_low: Mapped[float | None] = mapped_column(Float)                     # balanced-range lower bound
    baseline_high: Mapped[float | None] = mapped_column(Float)                    # balanced-range upper bound
    weekly_avg: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HrvSample(Base):
    """The 5-min RMSSD series for one `hrv_readings` night — source-agnostic.

    Garmin populates this from `hrvReadings[]`; nightly-only sources (Samsung) leave
    it empty. Children replace-on-reingest: a re-pull of a night clears and rewrites
    its samples, so the series never accumulates duplicates. ON DELETE CASCADE ties
    the series' lifetime to its parent night.
    """
    __tablename__ = "hrv_samples"
    __table_args__ = (
        UniqueConstraint("hrv_reading_id", "reading_time", name="uq_hrv_sample_reading_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    hrv_reading_id: Mapped[int] = mapped_column(
        ForeignKey("hrv_readings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reading_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rmssd_ms: Mapped[float | None] = mapped_column(Float)


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
    (DECISIONS_LOG — Adaptive Exposure Engine entry).

    THE WEARABLE-METRIC INVARIANT SCOPES TO THIS TABLE'S VERDICT, NOT TO
    MEASUREMENT (DECISIONS_LOG #161). `status` here remains self-reported through
    the education idiom (spec §12) and is never derived from a wearable. That is
    unchanged. What changed is that it is no longer the engine's only capability
    signal: `capability_observations` carries measured QUANTITIES, which may be
    device-derived (GPS max velocity, deceleration counts). Different signal,
    different provenance, both real — the verdict stays self-reported, the
    measurement need not be. Stated here explicitly because a silent widening of
    this invariant is the failure mode it exists to prevent.
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


class CapabilityObservation(Base):
    """Adaptive Exposure Engine — graded, timestamped capability MEASUREMENT
    (DECISIONS_LOG #161).

    Not a replacement for `capability_state`, and deliberately not a column on it.
    `capability_state.status` is the response-to-load VERDICT, written from the
    adaptation loop's response tags and self-reported through the education idiom.
    A row here is a measured QUANTITY someone recorded. Different signals,
    different provenance, both real — which is why they are different tables and
    why this one may carry device-derived values (see the invariant note on
    `CapabilityState`).

    Why a table and not a wider `capability_state`: `capability_state` is
    overwritten in place, so it can only ever show today's label. A 4-level
    ordinal cannot be regressed against dose, and an overwritten row has no
    trajectory. Asymmetry direction-of-travel, re-attainment curves, and
    dose-response slopes all need history that the state table structurally
    cannot hold.

    APPEND-ONLY. There is no `updated_at` and no UPDATE path, by construction: a
    correction is a NEW row, and supersession is decided by `observed_on` then
    `created_at`. `observed_on` is the date the measurement was taken, which is
    not the date it was entered — backfilling a battery from a fortnight ago must
    land on the day it happened or the series lies about when it moved.

    `region_key` and `measure_key` are both validated against `engine/taxonomy.py`
    at write time (fail-closed — an orphan key is refused, never stored), the same
    guard `adaptation.py` applies to `region_key`. A region with no declared
    measure is observation-ineligible.

    BOUNDARY: a value here is a measurement, never a verdict. Deriving symmetry,
    trend, or dose-response for display is legal; converting any of it into a
    clearance, a "safe to return", a severity grade, or a return-to-sport call is
    not. Enforced by `tests/test_capability_observations.py`, not by this
    docstring — same pattern as `injury_probes.py`.
    """
    __tablename__ = "capability_observations"
    __table_args__ = (
        Index("ix_capability_obs_user_region_side_date",
              "user_id", "region_key", "side", "observed_on"),
        Index("ix_capability_obs_user_date", "user_id", "observed_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region_key: Mapped[str] = mapped_column(String(100), nullable=False)   # matches taxonomy Region.key
    side: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'bilateral'"))
    # The measurement date, NOT the insert date. See the append-only note above.
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    measure_key: Mapped[str] = mapped_column(String(60), nullable=False)   # matches taxonomy Measure.key
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # baseline_battery | probe | session | manual — the protocol that produced it
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    # self_report | catapult | hevy | polar | manual — device-agnostic source tag
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # certain | likely | guessing — mirrors taxonomy.Confidence
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'likely'"))
    # {block, load, fatigue_state, notes, session_id} — free context, not queried on
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'v0'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # Why this report contributed no `LabResult` rows. NULL when it contributed at least one.
    #   all_markers_declined — every extracted marker was already stored at this collected_date
    #                          and was skipped by the #156 guard. The system worked.
    #   no_values_extracted  — the document yielded no extractable values at all (a graph or
    #                          chart PDF with no table). A FAULT.
    # Both previously looked identical after the fact: the confirm response carried `duplicates`
    # but nothing persisted it, so a zero-row report could not be classified by any stored field.
    # Filtering the results list on "zero rows" alone would therefore have hidden the faults
    # along with the repeats — absence-as-emptiness one layer along.
    zero_row_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
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


class MarkerCanonicalEntry(Base):
    """The canonical marker map, runtime-mutable (DECISIONS_LOG #220, fulfilling #50).

    Was a startup-loaded dict over `reference/marker_canonical.json`; that file is now
    only this table's migration seed. The move exists so #50's "confirmation-populated"
    half is buildable at all — a runtime bind cannot edit a file the app loaded at import.

    `marker_name_raw` is the exact-string lookup key (no fuzzy matching, #50). Rows are
    global, not per-user: canonical identity is a property of the marker, not the reader.
    `unit_established` is legitimately nullable — a unitless marker (eGFR, ratios) has no
    established unit, and null means NOT ESTABLISHED, which the over-collapse guard reads
    as "no unit claim to contradict" rather than as a mismatch.
    """
    __tablename__ = "marker_canonical_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    marker_name_raw: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    marker_canonical: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit_established: Mapped[str | None] = mapped_column(String(50), nullable=True)
    loinc: Mapped[str | None] = mapped_column(String(20), nullable=True)  # #50's dormant B2B field
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # column only, unwired
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # 'seed' | 'bind'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


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
    # App-owned annotation (DECISIONS_LOG #74): exercise-level laterality, NOT
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
    # Per-template bodyweight fraction (DECISIONS_LOG #245): the fraction of bodyweight
    # moved per rep for a bodyweight-CLASS movement (push-up ~0.65, chin/dip ~1.0, BW
    # squat/lunge ~0.85, Nordic ~0.9, dead bug ~0.25). NULL = NOT bodyweight-class → the
    # Tier-0 transform prices the set on `weight_kg` as logged. Read ONLY for rep-based
    # sets with `weight_kg` NULL or 0: eff_w = BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0);
    # a set with a logged weight > 0 is never scaled by it. Operator-owned like
    # `laterality`/`adjudicated_at` — never assigned by `_upsert_template`, so a resync
    # preserves it.
    bw_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExerciseRegionTag(Base):
    """App-owned exercise→taxonomy-region annotation (DECISIONS_LOG #74).

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
    # Weekly dose allocation — {"slots": [{capacity, sessions_per_week, minutes}]}.
    # Sport-agnostic BY CONSTRUCTION (DECISIONS_LOG #221): a slot names a taxonomy
    # Capacity and a quota, never a sport, position, or exercise. What makes a given
    # user's template netball-shaped or marathon-shaped is which regions `select_next`
    # picks to fill each slot — driven by `vehicle_bias`, `horizon` and
    # `primary_target`. NULL is a valid state (no template), not a degraded one.
    weekly_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # standing Probe allocation — never drops to zero (spec §2)
    probe_budget: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.25"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterpretationRephrase(Base):
    """Disposable plain-register overlay + its promotion state (DECISIONS_LOG #202).

    One row is a generated plain-language rephrase of an interpretation presentation, keyed
    by the base text it was built from (`payload_hash` from `presentation.presentation_hash`)
    and the register. It is BOTH the presentation cache (step 4) and the training-wheels
    promotion record (step 6) — one table, because a promotion must survive a Railway
    restart, which an in-memory cache would not.

    NEVER THE RECORD, always disposable. Dropping any row is safe: the structured payload is
    the record (#202 clause 2), and a missing row simply regenerates or renders the template.

    Promotion binds to the TEXT, not the panel. A new draw or an asset edit changes the base
    text -> a new `payload_hash` -> a new row at `ai_draft`. A stale `human_verified` can
    therefore never attach to changed text — regeneration is a fail-closed demotion, never a
    wrong promotion. The eligibility gate is UNCONDITIONAL and server-side: a plain-register
    request whose row is not `human_verified` renders the template regardless of the client's
    toggle (the toggle is a preference; the server decides). There is no auto-retire counter —
    retiring the gate after a few promoted panels is a later manual call.
    """
    __tablename__ = "interpretation_rephrases"
    __table_args__ = (
        UniqueConstraint("payload_hash", "register", name="uq_interp_rephrase_payload_register"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # sha256 hex of the base text (addr+text), NOT of meta.generated_at — see presentation_hash.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    register: Mapped[str] = mapped_column(String(20), nullable=False)   # 'plain' (only the overlay is stored)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # ai_draft | human_verified — the #194 promotion-gate vocabulary. NOTE: server_default is a
    # plain string (SQLAlchemy wraps it as text()) because the column named `text` above shadows
    # the imported `text()` function inside this class body.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'ai_draft'")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HevyWorkout(Base):
    """Persisted Hevy workout header — the append-only substrate the Q6 four-window
    load path is built on (DECISIONS_LOG #28/#32, the persistence-first lane).

    Keyed on the Hevy workout `id` (PK), so ingestion is a PK-upsert: a resync of the
    same 180-day window re-reads unchanged rows and cannot mint duplicates (D-G:
    dedup is flag-and-adjudicate, NOT delete). The full untouched Hevy payload is kept
    in `raw` (JSONB on Postgres) so a later transform version can recompute load from
    source without a re-fetch — the two-level store of D-B (`load_events` derive from
    this; corrections are recomputes, never migrations of history).

    Two app-owned columns the sync path NEVER writes, mirroring the
    `hevy_exercise_templates.laterality`/`adjudicated_at` convention (a resync must not
    clobber an operator annotation):

      * `excluded_at` — the D-G exclusion mark. An adjudicated-out duplicate is marked,
        never deleted; load consumers filter `excluded_at IS NULL`. Set by operator
        adjudication, not by ingestion.
      * `exclusion_reason` — free text paired with the mark.

    `dedup_flag` / `dedup_partner_ids` ARE sync-derived (recompute-safe): each sync
    re-derives which same-day high-similarity workouts a row pairs with. Flag, never
    drop — the operator adjudicates, then sets `excluded_at`.
    """
    __tablename__ = "hevy_workouts"
    __table_args__ = (
        Index("ix_hevy_workouts_user_id", "user_id"),
        Index("ix_hevy_workouts_start_time", "start_time"),
        Index("ix_hevy_workouts_user_start", "user_id", "start_time"),
    )

    hevy_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Hevy workout id (UUID string)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    # The full raw Hevy workout object, verbatim — source of truth for any recompute.
    raw: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Sync-derived dedup signal (D-G). Recompute-safe: overwritten every sync.
    dedup_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    dedup_partner_ids: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    # App/operator-owned exclusion mark (D-G). Sync NEVER assigns it, so a resync
    # preserves an adjudication. NULL = in-scope for load; NOT NULL = adjudicated out.
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class HevySet(Base):
    """One persisted Hevy set — the per-set grain the Mechanical/Neuromuscular
    transform (D-C) reads (weight_kg × reps, RPE/RIR, set type).

    Hevy sets carry no stable id of their own in the workout payload (only a
    positional `index`), so the PK is synthetic and identity is the natural key
    (workout_id, block_index, set_index) — a re-ingest of the same workout replaces
    its sets in place rather than appending. `block_index` is the exercise's position
    in the workout; `set_index` the set's position in the exercise.

    Keyed on `exercise_template_id` (#79), NEVER the logged title: a workout stores a
    title snapshot from when it was logged and Hevy renames its default templates, so
    a title key drifts. DELIBERATELY NOT an FK to `hevy_exercise_templates`: a logged
    template id can be absent from the local catalogue (#79/#81, and the very
    default-template hole the usage-joined laterality audit exists to surface). A hard
    FK would reject the ingest of exactly the rows the audit must find. The audit
    LEFT-joins instead.

    Set fields are the live-verified snake_case shape (hevy_format.py, #68):
    `type`, `weight_kg`, `reps`, `duration_seconds`, `distance_meters`, `rpe`.
    """
    __tablename__ = "hevy_sets"
    __table_args__ = (
        UniqueConstraint("workout_id", "block_index", "set_index", name="uq_hevy_set_position"),
        Index("ix_hevy_sets_workout_id", "workout_id"),
        Index("ix_hevy_sets_exercise_template_id", "exercise_template_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_id: Mapped[str] = mapped_column(
        ForeignKey("hevy_workouts.hevy_id", ondelete="CASCADE"), nullable=False
    )
    exercise_template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)   # exercise position in workout
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)     # set position in exercise
    type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # normal|warmup|dropset|failure
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)      # half-point decimals preserved


class LoadEvent(Base):
    """One derived per-session-window load contribution — the recomputable middle
    layer of the Q6 four-window store (DECISIONS_LOG #28/#32, D-B/D-C/D-D; gate 2).

    The Tier-0 transform (`backend/load_events.py`) reads `hevy_workouts.raw`
    (source of truth, gate 1) and writes one row per (session, window) here; the
    daily `load_metrics` + Banister rollup (gate 3) reads these. Per D-B this is the
    DERIVED tier: a coefficient/routing correction is a recompute — bump
    `formula_version` and re-derive — never a migration of computed history. So the
    transform is delete-and-reinsert per (user, `formula_version`); a re-run of the
    same version is idempotent (the `uq_load_event_session_window_version` natural
    key), and a new version's rows coexist beside the old until the rollup switches.

    Source-neutral (parallels the wearable ingestion contract, #236):
    `(source, source_ref)` names the originating session generically, with NO hard FK
    to `hevy_workouts`. The strength transform emits Mechanical / Neuromuscular from
    Hevy, but this same store will later hold Metabolic (aerobic) and Psychological
    (sRPE) events whose `source_ref` points elsewhere — a hard FK would reject them.
    `user_id` IS a hard FK (CASCADE). Rows orphaned by a hard-deleted or
    adjudicated-out (`excluded_at`) source session are cleared by the next recompute,
    which skips those sessions and rewrites the user's rows.

    `provenance` records the transform's GAPS at row grain (D-C/D-D coverage): which
    sets were RPE-banded vs reps-banded, whether h(I) used a fitted e1RM or the 0.5
    fallback, non-rep bridging contribution, the laterality `paired_templates` /
    `indeterminate_laterality` surfacing (for the asymmetry instrument, never cost), and
    the `post_epoch_zero_rpe` artifact-signature flag. It is diagnostic, not consumed by
    load — **load sums sets as logged**; the D-E pairing never discounts it.
    """
    __tablename__ = "load_events"
    __table_args__ = (
        UniqueConstraint("source", "source_ref", "load_window", "formula_version",
                         name="uq_load_event_session_window_version"),
        Index("ix_load_events_user_id", "user_id"),
        Index("ix_load_events_user_window", "user_id", "load_window"),
        Index("ix_load_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_load_events_formula_version", "formula_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)        # 'hevy'
    source_ref: Mapped[str] = mapped_column(String(64), nullable=False)   # session id (soft ref)
    load_window: Mapped[str] = mapped_column(String(20), nullable=False)  # 'mechanical' | 'neuromuscular' (`window` is a PG reserved word, #246)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    load: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)         # 'kg_reps' | 'nm_au'
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)  # 'tier0-v1'
    provenance: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LoadMetric(Base):
    """One derived per-(user, day, load_window) daily load rollup — the recomputable
    top layer of the Q6 four-window store (DECISIONS_LOG #28/#32, D-B; gate 3).

    The Banister transform (`backend/load_metrics.py`) reads `load_events` (gate 2's
    derived store, source of `daily_load`) and writes one row per (user, day, window)
    here; it never reads the raw Hevy payload. Per D-B this is a RECOMPUTE, never a
    migration: `fitness`/`fatigue` are EWMA stocks over a continuous daily series whose
    identity is pinned by TWO version axes — `formula_version` (inherited from the
    load_events transform) and `metrics_version` (this layer's τ-set / EWMA identity). A
    τ tune bumps `metrics_version` and delete-and-reinserts per
    `(user, formula_version, metrics_version)`; a `form` k-change is a form-column refresh
    from the stored stocks alone, neither a stock recompute nor a version bump.

    `fitness` = EWMA(daily_load, τ=42d, all windows); `fatigue` = EWMA(daily_load, τ per
    #32 — mechanical 10, neuromuscular 6, metabolic 4); `form` = fitness − k·fatigue (k=1).
    ΔLoad (#33): `acute_load` trailing-7d mean, `chronic_load` trailing-28d mean,
    `load_ratio` = acute/chronic (NULL if chronic 0). `maturity` = 'low' until ≥42d
    continuous history for the window, else 'ok' (annotate-never-suppress, #10/#28).

    Windows are computed only where `load_events` supply rows (today: mechanical,
    neuromuscular); the machinery is window-generic, so Metabolic/Psychological light up
    when fed. Units are window-native (kg_reps, nm_au) and never crossed. The window column
    is `load_window` — NOT `window` (#246 renamed that reserved word out of `load_events`;
    this table must not reintroduce it).
    """
    __tablename__ = "load_metrics"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "load_window", "formula_version", "metrics_version",
                         name="uq_load_metric_day_window_version"),
        Index("ix_load_metrics_user_window", "user_id", "load_window"),
        Index("ix_load_metrics_user_day", "user_id", "day"),
        Index("ix_load_metrics_metrics_version", "metrics_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)               # user-local (AEST) calendar day
    load_window: Mapped[str] = mapped_column(String(20), nullable=False)  # 'mechanical' | 'neuromuscular'
    daily_load: Mapped[float] = mapped_column(Float, nullable=False)      # Σ load_events.load that day
    fitness: Mapped[float] = mapped_column(Float, nullable=False)         # Banister EWMA τ=42
    fatigue: Mapped[float] = mapped_column(Float, nullable=False)         # Banister EWMA τ per #32
    form: Mapped[float] = mapped_column(Float, nullable=False)            # fitness − k·fatigue (k=1)
    acute_load: Mapped[float] = mapped_column(Float, nullable=False)      # #33 trailing-7d mean
    chronic_load: Mapped[float] = mapped_column(Float, nullable=False)    # #33 trailing-28d mean
    load_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)  # acute/chronic; NULL if chronic 0
    unit: Mapped[str] = mapped_column(String(20), nullable=False)         # 'kg_reps' | 'nm_au'
    maturity: Mapped[str] = mapped_column(String(8), nullable=False)      # 'low' | 'ok'
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)  # load_events transform version
    metrics_version: Mapped[str] = mapped_column(String(20), nullable=False)  # 'banister-v1'
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
