"""Zone-config reads — the one read behind `GET /hr-zones/config`, the MCP `get_hr_zone_config` tool and the
per-row `zoning` the sessions API attaches (design 0010 §6). READ-ONLY: nothing here writes a row.

`zone_config` answers "what zones this user today": per class the basis, the members, the band percents and
today's bpm edges; per anchor the entry in force, every entry (dated rows and restatement chains, provenance,
note), the derived retest flag; the R8 default date; the HRmax prompts; and the Garmin mirror (the band
percents as the operator's Garmin profile states them, plus the latest `hr_zone_config_snapshots` row —
observation only, never an anchor).

`row_zoning` answers "what zoned this row": derived from the row's source, sport and date and the anchors in
force, never stored (0010 §4). A Polar row reads `vendor` unless the Health Connect trace of the same bout
covers it, in which case it reads the model's basis — the same test `hc_zone_enrich` applies, so the read and
the fill agree.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from hr_zones import (ANCHOR_KINDS, ANCHORS_NEEDED, BASES, BAND_PCT_BY_BASIS, BASIS_HRR, BASIS_LTHR,
                      anchor_in_force, resolve_zone_spec, zone_session)
from sport_classes import LTHR_SPORTS, ZONE_CLASS_LABELS, zone_basis_for

ANCHOR_LABELS = {"hrmax": "HRmax", "lthr": "LTHR", "rhr": "Resting HR"}
BASIS_LABELS = {BASIS_LTHR: "% of LTHR (Friel)", BASIS_HRR: "% of heart-rate reserve (Karvonen)"}
# Garmin's own wording for the same two profiles (the mirror strip): cycling on %LTHR, default on %HRR.
GARMIN_PROFILE = {
    "cycling": {"basis": "%LTHR", "bands": ["<81", "81-89", "90-93", "94-99", "100+"]},
    "default": {"basis": "%HRR", "bands": ["50-59", "60-69", "70-79", "80-89", "90-100"]},
}
# A device auto-detected anchor is shown "retest" until a test or a strap observation replaces it.
RETEST_PROVENANCE = ("device_estimated",)
HRMAX_WRITER = "scripts/set_hrmax.py"


def _entry_dict(row, superseded: set[int]) -> dict[str, Any]:
    bpm = getattr(row, "hrmax_bpm", None)
    if bpm is None:
        bpm = row.bpm
    return {
        "id": row.id, "effective_from": row.effective_from.isoformat(), "bpm": bpm,
        "provenance": row.provenance, "note": row.note, "restates_id": row.restates_id,
        "rationale": getattr(row, "rationale", None), "base_bpm": getattr(row, "base_bpm", None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "superseded": row.id in superseded,
    }


def anchor_rows(db: Session, user_id: int) -> dict[str, list]:
    """The raw rows per kind, `created_at`/id order."""
    out = {"hrmax": (db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id)
                     .order_by(models.UserHrmax.effective_from, models.UserHrmax.id).all()),
           "lthr": [], "rhr": []}
    for a in (db.query(models.UserHrAnchor).filter(models.UserHrAnchor.user_id == user_id)
              .order_by(models.UserHrAnchor.effective_from, models.UserHrAnchor.id).all()):
        out[a.kind].append(a)
    return out


def anchor_entries(rows: dict[str, list]) -> dict[str, list]:
    from hr_zones import entry_from_row
    return {k: [entry_from_row(r) for r in rs] for k, rs in rows.items()}


def earliest_session_date(db: Session, user_id: int) -> Optional[date]:
    """The R8 seed default: the user's earliest `aerobic_sessions.session_date`, or None."""
    return db.query(func.min(models.AerobicSession.session_date)).filter(
        models.AerobicSession.user_id == user_id).scalar()


def latest_garmin_snapshot(db: Session, user_id: int) -> Optional[dict[str, Any]]:
    s = (db.query(models.HrZoneConfigSnapshot).filter_by(user_id=user_id)
         .order_by(models.HrZoneConfigSnapshot.captured_at.desc(), models.HrZoneConfigSnapshot.id.desc()).first())
    if s is None:
        return None
    return {"captured_at": s.captured_at.isoformat() if s.captured_at else None, "max_hr_bpm": s.max_hr_bpm,
            "lthr_bpm": s.lthr_bpm, "rhr_7d_auto_bpm": s.rhr_7d_auto_bpm, "method": s.method}


def class_specs(entries: dict[str, list], day: date) -> list[dict[str, Any]]:
    """Per basis: the members, band percents, and the bpm edges in force on `day` (None with the kinds missing)."""
    out = []
    for basis in BASES:
        spec = resolve_zone_spec(basis, day, hrmax_entries=entries["hrmax"],
                                 lthr_entries=entries["lthr"], rhr_entries=entries["rhr"])
        missing = [k for k in ANCHORS_NEEDED[basis] if anchor_in_force(entries[k], day) is None]
        if basis == BASIS_HRR and spec is None and not missing:
            missing = ["rhr"]          # present but incoherent (RHR not below HRmax): the RHR is the one to fix
        out.append({
            "key": basis, "label": ZONE_CLASS_LABELS[basis], "basis": basis, "basis_label": BASIS_LABELS[basis],
            "sports": sorted(LTHR_SPORTS) if basis == BASIS_LTHR else [],
            "band_pct": list(BAND_PCT_BY_BASIS[basis]),
            "edges_bpm": list(spec.edges_bpm) if spec else None,
            "anchors": dict(spec.anchors) if spec else {},
            "missing": missing,
        })
    return out


def zone_config(db: Session, user_id: int, *, today: date) -> dict[str, Any]:
    from hc_zone_enrich import over_ceiling_prompts
    rows = anchor_rows(db, user_id)
    entries = anchor_entries(rows)
    anchors: dict[str, Any] = {}
    for kind in ANCHOR_KINDS:
        rs = rows[kind]
        superseded = {r.restates_id for r in rs if r.restates_id is not None}
        in_force_bpm = anchor_in_force(entries[kind], today)
        in_force = None
        if in_force_bpm is not None:
            live = [r for r in rs if r.id not in superseded and r.effective_from <= today]
            top = max(r.effective_from for r in live)
            in_force = _entry_dict(next(r for r in live if r.effective_from == top), superseded)
        anchors[kind] = {
            "kind": kind, "label": ANCHOR_LABELS[kind],
            "in_force": in_force,
            "retest": bool(in_force) and in_force["provenance"] in RETEST_PROVENANCE,
            "entries": [_entry_dict(r, superseded) for r in rs],
            "writable": kind != "hrmax",
            "writer": None if kind != "hrmax" else HRMAX_WRITER,
        }
    return {
        "as_of": today.isoformat(),
        "classes": class_specs(entries, today),
        "anchors": anchors,
        "default_effective_from": (earliest_session_date(db, user_id) or today).isoformat(),
        "r8_pending": True,     # the seed-date rule (R8) awaits the operator's OK; the date stays editable
        "hrmax_prompts": over_ceiling_prompts(db, user_id),
        "garmin": {"profile": GARMIN_PROFILE, "snapshot": latest_garmin_snapshot(db, user_id)},
    }


# ── per-row basis, derived on read ───────────────────────────────────────────────────────────────

def row_zoning(db: Session, user_id: int, row, entries: dict[str, list]) -> dict[str, Any]:
    """`{class, class_label, basis, basis_label, anchors, edges_bpm, reason}` for one `aerobic_sessions` row.
    `basis` is `lthr` / `hrr` (zoned on the model), `vendor` (a Polar row keeping Polar's own zones), or None
    (a health_connect row withheld; `reason` says why when it is a precondition)."""
    from hc_zone_enrich import POLAR_SOURCES, _row_samples, _utc, spec_for
    basis = zone_basis_for(row.sport_name)
    out: dict[str, Any] = {"class": basis, "class_label": ZONE_CLASS_LABELS[basis], "basis": None,
                           "basis_label": None, "anchors": {}, "edges_bpm": None, "reason": None}
    spec = spec_for(row, entries)
    if row.source in POLAR_SOURCES:
        start, stop = _utc(row.start_time), _utc(row.stop_time)
        rezoned = False
        if spec is not None and start is not None and stop is not None and stop > start:
            rezoned = zone_session(_row_samples(db, user_id, row, start, stop), start, stop, spec).zones is not None
        if not rezoned:
            out.update(basis="vendor", basis_label="Polar's own zones (not re-zoned)",
                       reason="no_anchor" if spec is None else "polar_vendor_fallback")
            return out
    if spec is None:
        out["reason"] = "no_anchor"
        return out
    out.update(basis=spec.basis, basis_label=BASIS_LABELS[spec.basis], anchors=dict(spec.anchors),
               edges_bpm=list(spec.edges_bpm))
    if row.source not in POLAR_SOURCES and row.z1_seconds is None:
        out["reason"] = "withheld"     # samples too sparse or none from the row's writer; the fill said so
    return out


def annotate_zoning(db: Session, user_id: int, rows: list) -> list:
    """Set `.zoning` on every row (the sessions API's derived field), with the anchors read once."""
    entries = anchor_entries(anchor_rows(db, user_id))
    for r in rows:
        r.zoning = row_zoning(db, user_id, r, entries)
    return rows


# ── MCP formatter ─────────────────────────────────────────────────────────────────────────────────

def _edge_text(edges: Optional[list[int]]) -> str:
    if not edges:
        return "no bpm bands (anchor missing)"
    parts = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] - 1 if i + 1 < len(edges) else None
        parts.append(f"z{i + 1} {lo}+" if hi is None else f"z{i + 1} {lo}-{hi}")
    return " · ".join(parts)


def format_zone_config(cfg: dict[str, Any]) -> str:
    lines = [f"Heart-rate zones (as of {cfg['as_of']}; design 0010: per sport class, threshold-anchored)"]
    for c in cfg["classes"]:
        members = f" [{', '.join(c['sports'])}]" if c["sports"] else " [every sport not in the cycling class]"
        lines.append(f"  {c['label']}: {c['basis_label']}{members}")
        pct = c["band_pct"]
        pct_text = " / ".join(f"z{i + 1} {p}%+" for i, p in enumerate(pct))
        lines.append(f"    bands: {pct_text}")
        lines.append(f"    bpm today: {_edge_text(c['edges_bpm'])}"
                     + (f"; missing anchor(s): {', '.join(c['missing'])}" if c["missing"] else ""))
    lines.append("  anchors:")
    for kind in ANCHOR_KINDS:
        a = cfg["anchors"][kind]
        f = a["in_force"]
        if f is None:
            lines.append(f"    {a['label']}: none in force")
            continue
        flag = " — RETEST (device auto-detect)" if a["retest"] else ""
        chain = " (restates an earlier row)" if f["restates_id"] else ""
        lines.append(f"    {a['label']}: {f['bpm']} bpm, {f['provenance']}, from {f['effective_from']}{chain}{flag}; "
                     f"{len(a['entries'])} entr{'y' if len(a['entries']) == 1 else 'ies'}")
    for p in cfg.get("hrmax_prompts", []):
        lines.append(f"  HRMAX, restate? row {p['id']} {p['date']} {p['sport']}: a sample of {p['hr_max']} bpm "
                     f"against {p['hrmax_in_force']} in force (the operator's call; nothing is restated)")
    g = cfg["garmin"]
    snap = g.get("snapshot")
    if snap:
        lines.append(f"  Garmin reports (observation only, {snap['captured_at']}): max {snap['max_hr_bpm']}, "
                     f"LTHR {snap['lthr_bpm']}, 7-day auto RHR {snap['rhr_7d_auto_bpm']}, method {snap['method']}")
    lines.append("  RHR is the stored, dated anchor, never the live daily device RHR (R3). "
                 "HRmax is written only by scripts/set_hrmax.py; LTHR and RHR by the Settings card, append-only.")
    return "\n".join(lines)
