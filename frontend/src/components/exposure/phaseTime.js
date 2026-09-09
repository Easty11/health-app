// today in LOCAL time as YYYY-MM-DD — NOT toISOString(), which is UTC and rolls the date at the
// wrong hour. Its own module so PhaseForm exports only a component (react-refresh) and the test can
// assert the exact value the form sends.
export function todayLocal() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
