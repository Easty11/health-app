// SYNTHETIC appointment brief shaped like a real follow-up (#350): three injuries in scope, one
// imaging-like finding, one self-set constraint with a review date, nine authored asks (one with
// options, one linked to a row the brief cannot show) and one derived review_due ask. Placeholder
// text only — the repo is public. Shared by BriefPrint.test.jsx and the real-browser print check.

const CONSTRAINT = {
  key: 'constraint_part_a_load_cap', type: 'constraint', tier: 'advisory', kind: 'cap',
  text: 'CAP (advisory — not engine-enforced) — Synthetic load cap on movement A, no loaded end range',
  restriction: 'Synthetic load cap on movement A, no loaded end range',
  exit: 'when injury_part_a_right is resolved', exit_label: 'when right part a is resolved',
  review_by: '2026-10-15', asserted_by: 'user', authority: 'set by you', detail: null,
  parent_key: 'injury_part_a_right', parent_label: 'right part a',
}

export const FINDING_TEXT =
  'Imaging report A (synthetic): placeholder signal change at level A with a grade B placeholder ' +
  'feature; no placeholder feature C. Reported by radiologist A.'

const FINDING = {
  key: 'finding_part_a_imaging', type: 'finding', text: FINDING_TEXT,
  parent_key: 'injury_part_a_right', parent_label: 'right part a',
  as_of: '2026-08-20', status: 'open', marker_status: null, review_by: null,
  asserted_by: 'clinician', authority: 'set by your clinician',
}

const ASK_TEXT = [
  'Ask 1 (synthetic): what does imaging report A mean for movement A, and does it change the plan?',
  'Ask 2 (synthetic): is placeholder exercise B still the right progression for part b?',
  'Ask 3 (synthetic): can I return to placeholder activity C this block, and at what load?',
  'Ask 4 (synthetic): what is the expected timeline for part c?',
  'Ask 5 (synthetic): should I keep placeholder routine D as it is?',
  'Ask 6 (synthetic): is placeholder test E worth repeating before the next visit?',
  'Ask 7 (synthetic): what would change your view on placeholder option F?',
  'Ask 8 (synthetic): who should I see about placeholder concern G?',
  'Ask 9 (synthetic): when should I book the next visit?',
]

const unlinked = { entry_key: null, note: null, row: null, unresolved: false }

export const AUTHORED = ASK_TEXT.map((text, i) => ({
  id: `q${i + 1}`, text, priority: i + 1, folded: [],
  resolves: i === 0
    ? { entry_key: FINDING.key, note: 'Note A (synthetic): the report arrived after the last visit.', row: FINDING, unresolved: false }
    : i === 3
      ? { entry_key: 'constraint_gone_a', note: null, row: null, unresolved: true }
      : unlinked,
}))

export const PRINT_BRIEF = {
  key: 'appt_20261001_clinician_a', kind: 'follow_up', audience: 'operator', status: 'planned',
  patient: { name: 'Person A' },
  scope: { parent_keys: ['injury_part_a_right', 'injury_part_b', 'injury_part_c_left'], missing_parent_keys: [], hops: 1 },
  limits: ['Scope is one hop.', 'Labs are out of scope.'],
  sections: [
    { module: 'header', clinician: 'Clinician A', practice: 'Practice A', at: '2026-10-01T13:00',
      date: '2026-10-01', time: '13:00', status: 'planned', kind: 'follow_up', audience: 'operator',
      detail: 'Purpose A (synthetic): a follow-up on three areas since the last visit, and the questions I want to settle today.' },
    { module: 'leave_with', total: 9,
      items: AUTHORED.slice(0, 5).map((a) => ({ id: a.id, short: a.text.split(':')[0], priority: a.priority })) },
    { module: 'since', since: '2026-06-01', findings: [], constraints: [],
      injuries: [{ key: 'injury_part_c_left', text: 'left part c', change: 'recorded', on: '2026-07-10' }] },
    { module: 'changes_vs_history', since: '2026-06-01',
      findings: [{ ...FINDING, previous: [] }],
      injuries: [{ key: 'injury_part_b', text: 'part b', change: 'updated', before: 'Part b detail, version one (synthetic)',
        after: 'Part b detail, version two (synthetic)', on: '2026-07-01' }] },
    { module: 'asks', authored: AUTHORED,
      derived: [{ rule: 'review_due', entry_key: CONSTRAINT.key, source: 'ledger', row: CONSTRAINT,
        question: 'Is this still appropriate?', text: `Is this still appropriate? ${CONSTRAINT.text}` }] },
    { module: 'options_prep', items: [{ ask_id: 'q3', text: ASK_TEXT[2], options: [
      { option: 'Yes at full load', implication: 'placeholder plan X' },
      { option: 'Yes at reduced load', implication: 'placeholder plan Y' },
      { option: 'Not yet', implication: 'placeholder plan Z' }] }] },
    { module: 'current_constraints', items: [CONSTRAINT] },
    { module: 'logistics', items: ['Bring imaging report A (synthetic)', 'Ask for a copy of the notes'] },
  ],
}
