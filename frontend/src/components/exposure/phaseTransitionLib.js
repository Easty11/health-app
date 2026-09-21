// Pure helpers for PhaseTransitionFlow (2026-09-21 fixes). Kept out of the component module so
// react-refresh sees only a component export from the .jsx and the tests can assert these directly
// — the same split reason `phaseTime.js` exists.

export const TIME_BUCKETS = ['morning', 'afternoon', 'evening']

// Coarse bands mirroring the backend `_TIME_OF_DAY_BANDS` (knowledge.py). Used ONLY to derive a
// resolvable bucket from a precise start time, so a placement row always ships a valid
// `time_of_day` and NEVER 'unknown' — the B1 fault the server (rightly) rejected on every weekday.
const BAND_STARTS = [['evening', 17 * 60], ['afternoon', 12 * 60], ['morning', 5 * 60]]

export function parseHHMM(t) {
  const m = /^\s*(\d{1,2}):(\d{2})\s*$/.exec(t || '')
  if (!m) return null
  const h = Number(m[1])
  const mm = Number(m[2])
  if (h > 23 || mm > 59) return null
  return h * 60 + mm
}

// A parseable "HH:MM-HH:MM" range (F10). Returned trimmed for the payload's `time_range`; null when
// it does not parse (the form then falls back to the bucket alone).
export function normaliseTimeRange(raw) {
  const parts = String(raw || '').split(/\s*[-–—]\s*/)
  if (parts.length !== 2) return null
  const a = parseHHMM(parts[0])
  const b = parseHHMM(parts[1])
  if (a == null || b == null || a > b) return null
  return `${parts[0].trim()}-${parts[1].trim()}`
}

// The resolvable `time_of_day` a placement row ships (B1/F10). A precise range derives its bucket
// from the start minute; otherwise the explicit bucket; default 'evening'. Never 'unknown'.
export function deriveTimeOfDay(bucket, timeRange) {
  const range = normaliseTimeRange(timeRange)
  if (range) {
    const start = parseHHMM(range.split('-')[0])
    for (const [name, from] of BAND_STARTS) if (start >= from) return name
    return 'morning'
  }
  return TIME_BUCKETS.includes(bucket) ? bucket : 'evening'
}

// activity-name normalisation (F7): lowercase, spaces→underscores, collapsed. Matches how a
// `satisfies: {activity: …}` key is compared, so a link is not silently orphaned by casing.
export function normaliseActivityName(s) {
  return String(s || '').trim().toLowerCase().replace(/\s+/g, '_')
}

// The slots a stored microcycle carries, in the component's slot shape — for step-4 prefill (F6)
// and the confirm diff (F16).
export function microcycleSlots(microcycle) {
  const subs = microcycle && microcycle.sub_cycles
  const raw = Array.isArray(subs) && subs[0] && Array.isArray(subs[0].slots) ? subs[0].slots : []
  return raw.map((s) => {
    const kind = s.capacity != null ? 'capacity' : s.load_window != null ? 'load_window' : 'activity'
    const key = s.capacity ?? s.load_window ?? s.activity ?? ''
    return {
      kind, key,
      sessions: s.sessions_per_cycle ?? 0,
      minutes: s.minutes ?? 30,
      device_sports: Array.isArray(s.device_sports) ? s.device_sports : [],
      recorded_via: s.recorded_via ?? '',
    }
  })
}

export function slotIdentity(s) {
  return `${s.kind}:${s.key}`
}

// The confirm diff against the outgoing phase (F16, B2): removals FIRST, then changes, then adds —
// so a slot that silently vanished (B2's overwritten quota) is the first thing the operator reads.
export function diffSlots(outgoingSlots, newSlots) {
  const outByKey = new Map(outgoingSlots.map((s) => [slotIdentity(s), s]))
  const newByKey = new Map(newSlots.map((s) => [slotIdentity(s), s]))
  const removes = []
  const changes = []
  const adds = []
  for (const [id, s] of outByKey) if (!newByKey.has(id)) removes.push(s)
  for (const [id, s] of newByKey) {
    const prev = outByKey.get(id)
    if (!prev) {
      adds.push(s)
    } else if ((Number(prev.sessions) || 0) !== (Number(s.sessions) || 0)) {
      changes.push({ ...s, from: Number(prev.sessions) || 0, to: Number(s.sessions) || 0 })
    }
  }
  return { removes, changes, adds }
}

// True when the outgoing phase HAD capacity slots and the new phase keeps none with sessions > 0
// (B2): the confirm requires an explicit extra tick before a gym-less phase is written.
export function removesAllCapacity(outgoingSlots, newSlots) {
  const hadCapacity = outgoingSlots.some((s) => s.kind === 'capacity')
  if (!hadCapacity) return false
  const keepsCapacity = newSlots.some((s) => s.kind === 'capacity' && (Number(s.sessions) || 0) > 0)
  return !keepsCapacity
}

// The microcycle JSON the quota slots build (moved from the component so the confirm diff and the
// payload share one definition). One sub-cycle "A"; the step-4 raw-JSON escape hatch shows exactly
// this.
export function buildMicrocycle(slots) {
  return {
    sub_cycle_days: 7,
    sub_cycles: [{
      label: 'A',
      slots: slots.map((s) => {
        const out = { sessions_per_cycle: Number(s.sessions) || 0, minutes: Number(s.minutes) || 0 }
        if (s.kind === 'capacity') out.capacity = s.key
        else if (s.kind === 'load_window') { out.load_window = s.key || 'metabolic'; out.device_sports = s.device_sports }
        else { out.activity = s.key; out.device_sports = s.device_sports }
        if (s.recorded_via) out.recorded_via = s.recorded_via
        return out
      }),
    }],
  }
}
