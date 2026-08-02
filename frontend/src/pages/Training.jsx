// Training — hosts the existing WorkoutPanel full-width (#150 rule 4: a move, not a rewrite).
//
// COUPLING THAT MOVED WITH IT. WorkoutPanel is not self-contained the way HealthPanel is: it takes
// `onFeedback`, which in the old Dashboard set Dashboard-held `pendingFeedback` state that was
// then passed to ChatPanel. Panel -> Dashboard state -> chat. With the panel on its own route and
// chat docked in the shell, that state now lives in HubLayout and is reached through `useHubChat`.
// The panel itself is unedited; only the owner of the state changed.

import HubLayout from '../components/HubLayout'
import { useHubChat } from '../components/hub/HubChatContext'
import WorkoutPanel from '../components/WorkoutPanel'

function TrainingBody() {
  const { sendToChat } = useHubChat()
  return <WorkoutPanel onFeedback={sendToChat} />
}

export default function Training() {
  return (
    <HubLayout title="Training" back="/dashboard" fill>
      <TrainingBody />
    </HubLayout>
  )
}
