// Recovery — hosts the existing HealthPanel full-width (#150 rule 4: a move, not a rewrite).
//
// HealthPanel fetches /health/summary itself and held no Dashboard state, so nothing moved with
// it. `fill` bounds the module area so the panel's own `h-full` + internal scroll behave as they
// did inside the old Dashboard column.
//
// No forecast is previewed here and no readiness number appears on the Recovery TILE, so #150
// Constraint B does not engage — see the decision entry's "N/A" note.

import HubLayout from '../components/HubLayout'
import HealthPanel from '../components/HealthPanel'

export default function Recovery() {
  return (
    <HubLayout title="Recovery" back="/dashboard" fill>
      <HealthPanel />
    </HubLayout>
  )
}
