// Dates on the printed appointment brief (#350).

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function parts(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''))
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  return { y, mo, d, wd: new Date(Date.UTC(y, mo - 1, d)).getUTCDay() }
}

// "1 Oct 2026" — fixed English, so paper reads the same whatever the browser's locale.
export function fmtDay(iso) {
  const p = parts(iso)
  return p ? `${p.d} ${MONTHS[p.mo - 1]} ${p.y}` : ''
}

// "Thu 1 Oct 2026, 13:00"
export function fmtAppointment(date, time) {
  const p = parts(date)
  if (!p) return ''
  return `${WEEKDAYS[p.wd]} ${p.d} ${MONTHS[p.mo - 1]} ${p.y}${time ? `, ${time}` : ''}`
}
