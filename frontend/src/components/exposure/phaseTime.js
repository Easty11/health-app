// today in LOCAL time as YYYY-MM-DD — NOT toISOString(), which is UTC and rolls the date at the
// wrong hour. Its own module so the phase components export only components (react-refresh) and a test can
// assert the exact value the flow sends.
export function todayLocal() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
