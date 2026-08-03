// Copy for the sleep-need estimate. Pure, so it is reviewable in one place and
// assertable the moment a frontend test runner exists (the assertion is recorded OWED).

export function formatMinutes(m) {
  if (m == null) return '—'
  const total = Math.round(m)
  const h = Math.floor(total / 60)
  const min = total % 60
  return h > 0 ? `${h}h ${String(min).padStart(2, '0')}m` : `${min}m`
}

// The band the window hunts within: centre +/- one dither step. Shown instead of the
// bare current window so a +/-15 nudge every four nights reads as a search around a
// stable estimate, not as the app revising its answer.
export function convergenceBand(centreMinutes, ditherMinutes) {
  if (centreMinutes == null || !ditherMinutes) return null
  return `${formatMinutes(centreMinutes - ditherMinutes)}–${formatMinutes(centreMinutes + ditherMinutes)}`
}

// States what the number IS and what it rests on. An estimate from one cycle is not
// nothing, but the reader has to be able to tell it from one built on four.
export function centreBasisNote(cyclesN) {
  if (!cyclesN) return null
  if (cyclesN === 1) return 'from the last cycle only'
  return `centre of the last ${cyclesN} cycles`
}
