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


// ---- step-4 slot keys: the closed vocabularies, and the checks that used to fire only at step 8 ---- //
//
// 4 Oct 2026: the slot name was a free-text box for every kind, so 'Gym' (not a capacity) and a second
// 'metabolic' load_window both reached the save and were refused there, after the Hevy folder step.
// The backend's `slot_options` (from the draft) is the one source of the closed vocabularies; nothing here
// keeps a copy. `activity` is open (a sport name), so it has no list.

export const NO_SLOT_OPTIONS = { capacity: [], load_window: [] }

// The picker's options for a slot kind, or [] when the kind is open (activity) or the draft carried none
// (the form then falls back to a text box, so an older backend still works).
export function slotKeyOptions(kind, options) {
  const list = options && Array.isArray(options[kind]) ? options[kind] : []
  return kind === 'capacity' || kind === 'load_window' ? list : []
}

const _norm = (k) => String(k ?? '').trim().toLowerCase()

// The key a slot takes when it is added or its kind changes: the first option of that kind no other slot
// already holds (so a fresh slot is not an instant duplicate), else the first option; '' for an open kind.
// `skip` is the index of the slot being changed (its own current key is not "taken").
export function defaultSlotKey(kind, options, slots, skip = -1) {
  const opts = slotKeyOptions(kind, options)
  if (opts.length === 0) return kind === 'load_window' ? 'metabolic' : ''
  const taken = new Set(slots.filter((s, j) => j !== skip && s.kind === kind).map((s) => _norm(s.key)))
  return opts.find((o) => !taken.has(_norm(o))) ?? opts[0]
}

// One problem string per slot ('' when it is fine): exactly the refusals `validate_microcycle` would raise
// at save, found at step 4 instead. Mirrors the backend rules: a capacity / load_window key must be one of
// the offered values; an activity needs a name; one slot per (kind, key) within the sub-cycle; a
// load_window or activity slot needs at least one device sport.
export function validateSlots(slots, options) {
  const seen = new Map()
  return slots.map((s, i) => {
    const key = String(s.key ?? '').trim()
    const opts = slotKeyOptions(s.kind, options)
    if (s.kind === 'activity' && !key) return 'Name the activity.'
    if (opts.length > 0 && !opts.includes(key.toLowerCase())) {
      return `${key ? `"${key}"` : 'Nothing'} is not a ${s.kind === 'capacity' ? 'capacity' : 'load window'}: pick one of ${opts.join(', ')}.`
    }
    if (s.kind === 'capacity' && !key) return 'Pick a capacity.'
    const id = `${s.kind}:${key.toLowerCase() || (s.kind === 'load_window' ? 'metabolic' : '')}`
    if (seen.has(id)) {
      const hint = s.kind === 'load_window'
        ? ' A phase takes one load_window slot per window; count a further sport with an activity slot.'
        : ''
      return `Already a ${s.kind} slot for "${key || 'metabolic'}" (slot ${seen.get(id) + 1}): one per sub-cycle.${hint}`
    }
    seen.set(id, i)
    if ((s.kind === 'load_window' || s.kind === 'activity') && !(Array.isArray(s.device_sports) && s.device_sports.length)) {
      return 'Pick at least one device sport that counts.'
    }
    return ''
  })
}


// ---- step-5 placement links (4 Oct 2026: a slot picked on a "Keep" item was silently ignored) ---- //

// Do two `satisfies` values name the same quota slot? `satisfies` is `{kind: key}` or null. Null, undefined
// and {} all mean "fills no slot". Keys compare case-insensitively on the value, as the backend matches them.
export function sameSatisfies(a, b) {
  const pair = (s) => {
    const e = s && typeof s === 'object' ? Object.entries(s) : []
    return e.length ? `${e[0][0]}:${String(e[0][1]).trim().toLowerCase()}` : ''
  }
  return pair(a) === pair(b)
}

// The disposition an EXISTING placement should carry after its slot is changed. "Keep" retains the stored
// link and ignores the dropdown, so picking a different slot while on Keep must become "Relink" (the choice
// would otherwise be dropped by both the counter and the save). Picking the stored slot again stays Keep;
// Relink and Retire are the operator's own choice and are never changed here.
export function dispositionAfterSlotChange(placement, nextSatisfies) {
  if (!placement.isExisting || placement.disposition !== 'keep') return placement.disposition
  return sameSatisfies(placement.value?.satisfies, nextSatisfies) ? 'keep' : 'relink'
}
