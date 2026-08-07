// Row-classification for the lab confirmation screen (LAB_EXTRACTION_SCHEMA v0.3 §6).
//
// Pure, JSX-free, and lifted out of Metrics.jsx so it can be imported by both the page
// and its tests — a component file may only export components (react-refresh), and these
// need to be reachable from vitest to pin the null-handling below. Same split as
// `lib/apiError.js`.
//
// The through-line across every function here: a `field_confidence` sub-field may be
// `null`, meaning NOT EXPRESSED — a ref-less row has no `ref` to have scored. JS coerces
// `null` to 0 in both `<` and `+`, so an unguarded read reports a clean extraction as a
// problem (`#179`, the last instance of the `#177`/`#178` null-on-sparse-row family).

export function isSuspect(r, canonicalMap) {
  const conf = r.field_confidence
  // `v != null` first: a null sub-field means NOT EXPRESSED (no ref on the row, so no
  // ref confidence), and in JS `null < 0.85` is true because null coerces to 0 — so an
  // unguarded compare marks the row suspect for a field that legitimately does not
  // exist. Suspect must mean "read badly", never "absent from the report".
  if (conf && Object.values(conf).some((v) => v != null && v < 0.85)) return true
  if (r.flag_agreement === false) return true
  if (!canonicalMap[r.marker_name_raw]) return true // unmapped — no canonical entry
  const hasUnit = !!(r.unit_canonical || r.unit_raw)
  if (r.value_num == null && r.value_qualitative == null && hasUnit) return true
  return false
}

export function isClinicalFlag(r) {
  return !!(r.lab_flag || r.computed_flag)
}

export function rowTier(r, canonicalMap) {
  if (isSuspect(r, canonicalMap)) return 0
  if (isClinicalFlag(r)) return 1
  return 2
}

export function confidencePct(r) {
  const conf = r.field_confidence
  if (!conf) return null
  // Filter BEFORE averaging, and average over the filtered count. A null sub-field
  // poisons this twice over, and the second way is easy to miss: `a + b` coerces null
  // to 0, AND the null still counts in the denominator. Four fields of ~0.97 with one
  // null would read 73%, understating a clean extraction by a quarter — a plausible
  // number, silently wrong, which is the worst kind.
  const values = Object.values(conf).filter((v) => v != null)
  // All-null (or an object of only absent fields) has no percentage to state. Return
  // null, same as an absent object — the render site prints '—' for it.
  if (values.length === 0) return null
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100)
}
