// Late-reported appointments (#346): a `planned` appointment whose `at` has passed, in Brisbane
// wall time. Surfacing only — nothing transitions a status.

// `at` is Brisbane wall time ("YYYY-MM-DDTHH:MM", optionally "+10:00"), so the comparison is done
// in Brisbane wall time too — never the device's zone.
function brisbaneNow(now) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Australia/Brisbane', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map((p) => [p.type, p.value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

export function awaitingDays(at, now = new Date()) {
  const wall = String(at || '').slice(0, 16)
  const nowWall = brisbaneNow(now)
  if (wall.length < 16 || wall >= nowWall) return null
  const day = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10))
  return Math.round((day(nowWall) - day(wall)) / 86400000)
}

export function awaitingLabel(n) {
  if (n === 0) return 'Awaiting report · today'
  return `Awaiting report · ${n} day${n === 1 ? '' : 's'}`
}
