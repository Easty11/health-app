// Section placement for the lab-interpretation view (contract v0.4 §2).
//
// Placement CONSUMES `should_surface`; it does not recompute it. The view previously
// recomputed moved-ness as gate 1 OR gate 2, which silently dropped gate 3 — the safety band.
// A marker can be unmoved and in-range and still sit in an authored band (that independence is
// the whole point of gate 3, #139), so a safety-band-only group was routed to Stable and its
// members folded away. That is the one placement error the view could make that hides the most
// serious finding it has.
//
// Recomputing a gate verdict client-side is the defect, not the particular formula: the
// producer resolves three gates against authored assets and declared state, and any
// reimplementation here is a second source of truth that drifts silently.

const GRADE_ORDER = { high: 0, moderate: 1, low: 2 }

export function isMovedGroup(group) {
  return group.should_surface === true
}

export function splitSections(interpretation) {
  const moved = []
  const stable = []
  for (const group of interpretation.groups) {
    ;(isMovedGroup(group) ? moved : stable).push(group)
  }
  return { moved, stable }
}

// Anchor id for a lever's in-card strip entry — the jump target the pooled
// Mechanisms index navigates back to.
export function leverAnchorId(groupKey, leverKey) {
  return `lever-${groupKey}-${leverKey}`
}

// Union of shared_levers across the moved groups, deduped by lever_key and
// ordered by grade. A lever is authored once per group; the first group that
// carries it owns the anchor.
export function poolLevers(movedGroups) {
  const byKey = new Map()
  for (const group of movedGroups) {
    for (const lever of group.shared_levers) {
      if (byKey.has(lever.lever_key)) continue
      byKey.set(lever.lever_key, { lever, groupKey: group.group_key })
    }
  }
  return [...byKey.values()].sort((a, b) => {
    const ga = GRADE_ORDER[a.lever.grade] ?? 99
    const gb = GRADE_ORDER[b.lever.grade] ?? 99
    return ga - gb
  })
}
