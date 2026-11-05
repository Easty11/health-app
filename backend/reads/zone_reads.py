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

`zone_coverage` answers "how is every row zoned now" (the MCP `get_zone_coverage` tool): per source the count
per category, each row classified by `row_zoning` and nothing else. The chain report `hc_zone_enrich.enrich_user`
returns is never persisted, so coverage is derived on read, not recorded per run.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
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
        "default_effective_from": (earliest_session_date(db, user_id) or today).isoformat(),   # R8; editable
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


# ── coverage: how every row is zoned, derived on read ────────────────────────────────────────────

COVERAGE_CATEGORIES = ("lthr", "hrr", "vendor", "no_anchor", "withheld")
COVERAGE_SAMPLE_CAP = 20


def coverage_category(zoning: dict[str, Any]) -> str:
    """One of `COVERAGE_CATEGORIES` for a `row_zoning` result. The reason wins when one is set, so the
    categories partition the rows: `vendor` is exactly `polar_vendor_fallback` (anchors in force, no
    Polar Flow trace covering the bout); a Polar row with NO anchor reads `no_anchor` here even though
    its basis is `vendor` (the sessions API says both; the count keeps them apart)."""
    reason = zoning.get("reason")
    if reason == "polar_vendor_fallback":
        return "vendor"
    if reason in ("no_anchor", "withheld"):
        return reason
    return zoning["basis"]            # lthr / hrr: zoned on the model


def zone_coverage(db: Session, user_id: int, days: Optional[int] = None, *,
                  today: Optional[date] = None) -> dict[str, Any]:
    """How every `aerobic_sessions` row of the user is zoned NOW, per source, derived live from
    `row_zoning` (the same path as the sessions API's `zoning` field) with the anchors read once.
    READ-ONLY: nothing is written, nothing committed. Nothing persists the chain report
    (`hc_zone_enrich.enrich_user` returns and prints it), so this is the one place to read coverage.

    Every raw row is counted, twins included, because the fill zones every raw row (a non-canonical
    twin is zoned on its own and shows on its own card). `days` limits the rows to
    `session_date >= today - days`; None is all history.

    Returns `{as_of, days, since, total, date_range: {first, last}, by_source: {source: {category: n}},
    totals: {category: n}, polar: {rows, rezoned, vendor_fallback, vendor_no_anchor}, rows: [...]}`,
    where `rows` lists up to `COVERAGE_SAMPLE_CAP` rows that are not zoned on the model (`vendor`,
    `no_anchor`, `withheld`), oldest first, each `{id, date, sport, source, basis, reason}`."""
    from hc_zone_enrich import POLAR_SOURCES
    today = today or date.today()
    since = today - timedelta(days=days) if days is not None else None
    q = db.query(models.AerobicSession).filter(models.AerobicSession.user_id == user_id)
    if since is not None:
        q = q.filter(models.AerobicSession.session_date >= since)
    rows = q.order_by(models.AerobicSession.session_date, models.AerobicSession.id).all()
    entries = anchor_entries(anchor_rows(db, user_id))

    by_source: dict[str, dict[str, int]] = {}
    totals = {c: 0 for c in COVERAGE_CATEGORIES}
    polar = {"rows": 0, "rezoned": 0, "vendor_fallback": 0, "vendor_no_anchor": 0}
    sample: list[dict[str, Any]] = []
    sample_overflow = 0
    for r in rows:
        z = row_zoning(db, user_id, r, entries)
        cat = coverage_category(z)
        by_source.setdefault(r.source, {c: 0 for c in COVERAGE_CATEGORIES})[cat] += 1
        totals[cat] += 1
        if r.source in POLAR_SOURCES:
            polar["rows"] += 1
            if z["basis"] in (BASIS_LTHR, BASIS_HRR):
                polar["rezoned"] += 1
            elif z["reason"] == "polar_vendor_fallback":
                polar["vendor_fallback"] += 1
            else:
                polar["vendor_no_anchor"] += 1
        if cat in ("vendor", "no_anchor", "withheld"):
            if len(sample) < COVERAGE_SAMPLE_CAP:
                sample.append({"id": r.id, "date": r.session_date.isoformat(), "sport": r.sport_name,
                               "source": r.source, "basis": z["basis"], "reason": z["reason"]})
            else:
                sample_overflow += 1
    return {
        "as_of": today.isoformat(),
        "days": days,
        "since": since.isoformat() if since else None,
        "total": len(rows),
        "date_range": {"first": rows[0].session_date.isoformat(), "last": rows[-1].session_date.isoformat()} if rows else None,
        "by_source": by_source,
        "totals": totals,
        "polar": polar,
        "rows": sample,
        "rows_not_listed": sample_overflow,
    }


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


COVERAGE_LABELS = {"lthr": "lthr", "hrr": "hrr", "vendor": "vendor (polar_vendor_fallback)",
                   "no_anchor": "no_anchor", "withheld": "withheld"}


def _counts_text(counts: dict[str, int]) -> str:
    return " · ".join(f"{COVERAGE_LABELS[c]} {counts[c]}" for c in COVERAGE_CATEGORIES)


def format_zone_coverage(cov: dict[str, Any]) -> str:
    window = f"last {cov['days']} days, since {cov['since']}" if cov["days"] is not None else "all history"
    lines = [f"Zone coverage (as of {cov['as_of']}; {window}; design 0010: every raw aerobic_sessions row, "
             f"twins included, as the fill zones them)"]
    if cov["total"] == 0:
        lines.append("  no aerobic sessions in the window")
    else:
        rng = cov["date_range"]
        lines.append(f"  {cov['total']} row{'s' if cov['total'] != 1 else ''}, {rng['first']} to {rng['last']}: "
                     f"{_counts_text(cov['totals'])}")
        for source in sorted(cov["by_source"]):
            counts = cov["by_source"][source]
            lines.append(f"  {source} ({sum(counts.values())}): {_counts_text(counts)}")
        p = cov["polar"]
        if p["rows"]:
            lines.append(f"  Polar rows {p['rows']}: polar_rezoned {p['rezoned']} (zoned on the model from the "
                         f"fi.polar.polarflow trace) · polar_vendor_fallback {p['vendor_fallback']} (Polar's own zones "
                         f"kept: anchors in force, no trace covering the bout) · vendor with no anchor "
                         f"{p['vendor_no_anchor']} (counted under no_anchor above)")
        if cov["rows"]:
            n = len(cov["rows"])
            more = f"; {cov['rows_not_listed']} more not listed" if cov["rows_not_listed"] else ""
            lines.append(f"  rows not zoned on the model (oldest first, first {n}{more}):")
            for r in cov["rows"]:
                lines.append(f"    row {r['id']} {r['date']} {r['sport']} [{r['source']}]: {r['reason']}"
                             + (f" (basis {r['basis']})" if r["basis"] else ""))
    lines.append("  Counts are derived live from reads.zone_reads.row_zoning, the sessions API's zoning path; "
                 "the refresh_load chain report is not stored, so no run-to-run delta is available here.")
    return "\n".join(lines)
