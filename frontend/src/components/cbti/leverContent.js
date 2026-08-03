// Deep-sleep levers — EDUCATION, evidence-ranked. Content only, no engine logic.
//
// WHY THIS EXISTS. The sleep window is one lever, not the whole game. CBT-I/SRT
// consolidates sleep and cuts fragmentation; it does not manufacture total sleep time
// (van Straten 2017: TST carries the smallest effect, g~0.16, against SE g~0.71; Scott
// 2022). A surface that shows only the titration implies the window is "the" fix, which
// the evidence does not support.
//
// THE #47 LINE. This list is IDENTICAL for every reader and is never reordered, scored,
// or filtered by anyone's data. That is what keeps it education rather than personalised
// prioritisation: #47 permits explaining mechanisms and listing evidence-ranked levers,
// and forbids connecting a lever to a personalised recommended action. So there is no
// "your top lever", no "you should", no per-user ranking, and nothing here reads the
// user's record. #150 Constraint A draws the same line for tiles.
//
// If a future change wants to highlight one lever for one user, that is the boundary —
// it needs a decision, not a patch here.

// Evidence grade describes the STRENGTH OF THE GENERAL CLAIM, not its relevance to any
// reader. Ordering is by grade then by directness of the SWS effect, fixed at authorship.
export const DEEP_SLEEP_LEVERS = [
  {
    key: 'airway',
    title: 'Airway control',
    grade: 'strong',
    mechanism:
      'Untreated or under-titrated obstructive sleep apnoea fragments slow-wave sleep — '
      + 'arousals end deep-sleep bouts before they finish. Where CPAP is in use, its '
      + 'effective titration is the single largest structural influence on SWS.',
    note: 'Assessed from clinician data (titration reports, AHI), not computed in this app.',
  },
  {
    key: 'exercise',
    title: 'Daytime aerobic exercise',
    grade: 'moderate',
    mechanism:
      'Daytime aerobic exercise raised slow-wave sleep by roughly a third in controlled '
      + 'work (Aritake-Okada 2019). Evening training is not itself a problem: the effect '
      + 'turns unfavourable mainly for vigorous work close to bedtime — within about an '
      + 'hour (Stutz 2018), with strenuous sessions better placed 4h or more before bed '
      + '(Leota 2025).',
  },
  {
    key: 'thermal',
    title: 'Evening thermal down-slope',
    grade: 'moderate',
    mechanism:
      'Core temperature falling is part of the normal sleep-onset process. A warm shower '
      + 'or bath 1–2 hours before bed raises peripheral blood flow, so core temperature '
      + 'drops faster afterwards than it otherwise would.',
  },
  {
    key: 'restriction',
    title: 'Keeping the sleep restriction',
    grade: 'moderate',
    mechanism:
      'Slow-wave sleep is homeostatic — it rises with time spent awake. Holding the '
      + 'prescribed window concentrates sleep pressure, so the sleep that does occur runs '
      + 'deeper. This is the lever the titration on this page is tuning.',
  },
  {
    key: 'suppressors',
    title: 'Removing suppressors',
    grade: 'strong',
    mechanism:
      'Alcohol and late caffeine both cost slow-wave sleep. Alcohol front-loads sedation '
      + 'and fragments the second half of the night; caffeine’s half-life keeps it active '
      + 'well into the evening after an afternoon dose.',
  },
]

// Why SWS is worth targeting at all. Stated at the confidence the human evidence
// actually carries — this is an active area, not a settled one, and it is emphatically
// not a claim that sleep prevents dementia.
export const CLEARANCE_RATIONALE = {
  claim:
    'Slow-wave sleep is when the brain’s glymphatic clearance of metabolic waste is most '
    + 'active, and that clearance appears impaired in insomnia.',
  confidence:
    'Evolving in humans — the mechanism is well described in animal work and is being '
    + 'extended to people. Read it as a reason SWS is worth protecting, not as a settled '
    + 'clinical outcome.',
  refs: ['10.1093/brain/awaf453', '10.1111/jsr.70069'],
}

const GRADE_LABEL = { strong: 'Strong', moderate: 'Moderate', emerging: 'Emerging' }

export function gradeLabel(grade) {
  return GRADE_LABEL[grade] ?? grade
}

// The framing line that keeps the titration in proportion. Deliberately about the
// INTERVENTION in general, never about this reader's numbers.
export const TITRATION_SCOPE_NOTE =
  'Sleep restriction consolidates sleep and reduces fragmentation. It is not a way to '
  + 'manufacture more total sleep — in trials, total sleep time moves least of all the '
  + 'measures. It is one lever among several.'
