// The docked chat's push channel, in its own module.
//
// WorkoutPanel pushes a formatted workout into chat via `onFeedback`. In the old Dashboard that
// flowed through Dashboard-held `pendingFeedback` state into ChatPanel; with the panel on /training
// and chat docked in the shell, HubLayout owns that state and hands `sendToChat` down through here.
//
// Separate from HubLayout.jsx only because react-refresh requires a component file to export
// components and nothing else — a module exporting the context and its hook keeps fast refresh
// working for the layout.

import { createContext, useContext } from 'react'

export const HubChatContext = createContext(null)

export function useHubChat() {
  return useContext(HubChatContext) ?? { sendToChat: () => {} }
}
