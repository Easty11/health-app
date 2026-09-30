// The operator's local calendar date for a stored instant — Brisbane, never the device zone and
// never `iso.slice(0, 10)`.
//
// A timestamp's first ten characters are its UTC date. A session started at 07:00 AEST on 29 Sep is
// 21:00 UTC on 28 Sep, so slicing shows it a day early — every session before 10:00 AEST. The backend
// buckets on the same zone (`load_metrics._local_day`, aerobic `session_date`), so a session reads the
// same date on every surface. Fixed to Brisbane, like `awaitingReport.js`, so the result does not depend
// on the browser's zone (or the test runner's).

const BRISBANE_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Australia/Brisbane', year: 'numeric', month: '2-digit', day: '2-digit',
})

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

// 'YYYY-MM-DD' local date for an ISO timestamp; a bare date ('YYYY-MM-DD', e.g. aerobic `session_date`,
// already local) passes through unchanged. Missing or unparseable -> '—'.
export function localDate(iso) {
  if (!iso) return '—'
  if (DATE_ONLY.test(iso)) return iso
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return BRISBANE_DAY.format(d)
}
