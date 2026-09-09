// Training — the exposure recommendation above the workout record (#150 rule 4: a move, not a
// rewrite; ExposurePanel is added, WorkoutPanel and HubLayout are unedited).
//
// COUPLING THAT MOVED WITH IT. WorkoutPanel is not self-contained the way HealthPanel is: it takes
// `onFeedback`, which in the old Dashboard set Dashboard-held `pendingFeedback` state that was
// then passed to ChatPanel. Panel -> Dashboard state -> chat. With the panel on its own route and
// chat docked in the shell, that state now lives in HubLayout and is reached through `useHubChat`.
// ExposurePanel's `onDiscuss` is the same channel — one user-initiated push, nothing on mount (#59).
//
// LAYOUT. HubLayout `fill` gives its <main> no scroll and expects a single full-height child
// (WorkoutPanel is `h-full`). Two children break that assumption, so the stack owns its own scroll
// here rather than editing HubLayout. WorkoutPanel is given a bounded height so its internal scroll
// still works and it does not swallow the whole viewport above the recommendation.

import HubLayout from '../components/HubLayout'
import { useHubChat } from '../components/hub/HubChatContext'
import ExposurePanel from '../components/ExposurePanel'
import WorkoutPanel from '../components/WorkoutPanel'

function TrainingBody() {
  const { sendToChat } = useHubChat()
  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <ExposurePanel onDiscuss={sendToChat} />
      <div className="h-[75vh] min-h-[420px] border border-gray-200 rounded-2xl overflow-hidden bg-white">
        <WorkoutPanel onFeedback={sendToChat} />
      </div>
    </div>
  )
}

export default function Training() {
  return (
    <HubLayout title="Training" back="/dashboard" fill>
      <TrainingBody />
    </HubLayout>
  )
}
