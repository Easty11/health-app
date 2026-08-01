// The group's as-of date (#159 rule 1; derivation fixed by #160 — current side only).
//
// #159 says a group whose as-of differs from the trigger draw "is labelled rather than merged".
// This is that label, rendered in place. Sectioning by provenance is the rest of (e) and is not
// what #159's wording asks for here.
//
// Silent when the group sits on the trigger draw — which is the common case, and a date on every
// group would be noise that trains the reader to ignore the one that matters. The label appears
// exactly when the group's contents did NOT come from the panel the page header names.

export default function GroupAsOf({ asOf, panelCollected }) {
  if (!asOf) return null

  if (asOf.spans_draws) {
    return (
      <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 tabular-nums">
        spans draws · {asOf.earliest} to {asOf.latest}
      </span>
    )
  }

  if (panelCollected && asOf.latest !== panelCollected) {
    return (
      <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 tabular-nums">
        as of {asOf.latest} · not this panel
      </span>
    )
  }

  return null
}
