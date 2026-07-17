// Section placement for the lab-interpretation view (contract v0.4 §2).
//
// A group is "moved" iff ANY member is news (gate 1) OR out-of-range (gate 2).
// The two gates are independent: a group with nothing newsworthy in it still
// moves on a lone range breach — that is the #47 gate-2 spine, not a bug.

const GRADE_ORDER = { high: 0, moderate: 1, low: 2 }

export function isMovedGroup(group) {
  return group.members.some((m) => m.news_gate.is_news || m.range_gate.is_out_of_range)
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
