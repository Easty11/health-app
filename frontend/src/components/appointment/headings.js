// Appointment brief headings (#345) — one per section module, per audience. Audience changes the
// heading voice only, never the content.
//
// The #121 served-bundle grep keys on "Leave with" and
// "Changes since" — both must stay string literals here.
export const HEADINGS = {
  header: { operator: 'Appointment', clinician: 'Appointment details' },
  leave_with: { operator: 'Leave with', clinician: "What I'd like to leave with today" },
  asks: { operator: 'Asks', clinician: "What I'd like to ask" },
  options_prep: { operator: 'If the answer is…', clinician: "Options I've considered" },
  since: { operator: 'Since last visit', clinician: 'What has happened since my last visit' },
  changes_vs_history: {
    operator: 'Changes since last visit',
    clinician: 'Changes since my last visit, against what was recorded before',
  },
  current_constraints: { operator: 'Current constraints', clinician: "Restrictions I'm working under" },
  background: { operator: 'Background', clinician: 'Background to this injury' },
  imaging_timeline: { operator: 'Imaging and documents', clinician: 'Imaging and documents on record' },
  request: { operator: 'The request', clinician: "What I'm requesting, and why" },
  logistics: { operator: 'Logistics', clinician: 'Before we finish' },
}
