// Shared display labels for a quota slot key (Know (d), R7). "Conditioning" is the ONLY user-facing
// label for the `load_window` kind (its one declared window is `metabolic`, which stays an internal
// token): the quota window, the leg strip and the leg wrap all go through here, so a fourth surface
// cannot quietly say "Metabolic".

export function titleCase(s) {
  return typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : s
}

// kind: 'capacity' | 'load_window' | 'activity'; key: the slot's token.
export function keyLabel(kind, key) {
  if (kind === 'load_window' && key === 'metabolic') return 'Conditioning'
  return titleCase(key)
}

// 'monday' -> 'Mon'
export function dayAbbrev(weekday) {
  return typeof weekday === 'string' && weekday ? titleCase(weekday.slice(0, 3)) : ''
}

// 'YYYY-MM-DD' -> '4 Oct'. Pure string work: a `new Date('2026-10-04')` is UTC midnight and reads a day
// early in a zone behind UTC (the trap FEEDBACK §55 names for `iso.slice`).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? '')
  if (!m) return iso ?? ''
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? m[2]}`
}

// Monday-first order for a list of weekday names (the tray lists candidate days Mon -> Sun whatever
// day the leg starts on).
export const WEEKDAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

// The resolver's `uncounted` reasons, in the words the page uses (R10). An unknown reason falls back to
// itself with the underscores removed, so a new server-side reason shows rather than vanishing.
const REASON_LABELS = {
  off_plan: 'off plan',
  untagged: 'untagged',
  unadjudicated_duplicate: 'duplicate not adjudicated',
  untimed: 'untimed',
  concurrent_strength: 'concurrent strength',
  unclaimed_session: 'other activity',
}
export function reasonLabel(reason) {
  return REASON_LABELS[reason] ?? String(reason).replace(/_/g, ' ')
}
