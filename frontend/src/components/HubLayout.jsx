// Hub shell layout — chat docked, module area as children (#150 rule 1).
//
// ONE ChatPanel INSTANCE, NOT TWO. The obvious implementation renders a rail for >= md and a
// separate drawer for < md and lets the breakpoint hide one. That is a duplicate-send bug: both
// instances mount, both receive `pendingFeedback`, both POST /chat, and both write the same
// localStorage history key. So there is a single element here whose POSITION changes at the
// breakpoint — static rail at >= md, fixed bottom sheet below it — and the panel never remounts.
//
// The sheet is h-[60vh] deliberately. ChatPanel's own root is `h-[60vh] md:h-full`, written for
// the old Dashboard column; matching the sheet to it means the docked panel needs no edit at all
// (#150 rule 3 / #59 — a layout change must not reach into chat's wiring).
//
// The sheet stays MOUNTED when closed and slides out via translate, so chat state survives being
// dismissed. `md:translate-y-0` clears the closed transform at the rail breakpoint.

import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import ChatPanel from './ChatPanel'
import { HubChatContext } from './hub/HubChatContext'

export default function HubLayout({ title, back, fill = false, children }) {
  const navigate = useNavigate()
  const [pendingFeedback, setPendingFeedback] = useState(null)
  const [chatOpen, setChatOpen] = useState(false)

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  // A message pushed into a closed sheet would send invisibly, so opening is part of sending.
  function sendToChat(message) {
    setPendingFeedback(message)
    setChatOpen(true)
  }

  return (
    <HubChatContext.Provider value={{ sendToChat }}>
      <div className={`bg-gray-50 flex flex-col ${fill ? 'h-screen' : 'min-h-screen md:h-screen'}`}>
        <header className="flex-none bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between sticky top-0 z-10">
          <div className="flex items-center gap-2 min-w-0">
            {back && (
              <Link to={back} className="text-gray-400 hover:text-gray-700 transition-colors" aria-label="Back">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </Link>
            )}
            <span className="text-sm font-bold text-gray-900 truncate">{title}</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setChatOpen(true)}
              className="md:hidden text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
            >
              💬 Chat
            </button>
            <button onClick={logout} className="text-xs text-red-500 hover:text-red-700 transition-colors">
              Sign out
            </button>
          </div>
        </header>

        <div className="flex-1 flex flex-col md:flex-row min-h-0">
          <main className={`flex-1 min-h-0 ${fill ? '' : 'overflow-y-auto'}`}>{children}</main>

          {/* Backdrop — sheet only, never the rail. */}
          {chatOpen && (
            <div
              className="md:hidden fixed inset-0 z-20 bg-black/30"
              onClick={() => setChatOpen(false)}
            />
          )}

          {/* Every sheet rule is max-md:-scoped rather than declared unconditionally and undone
              with md: resets — at the rail breakpoint this element is simply a static flex child
              with a width and a border, and there is no rounded/shadow/fixed/translate to cancel. */}
          <aside
            className={`bg-white flex flex-col overflow-hidden
              max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:z-30
              max-md:h-[calc(60vh+2.25rem)] max-md:rounded-t-2xl max-md:shadow-2xl
              max-md:transition-transform max-md:duration-200
              ${chatOpen ? 'max-md:translate-y-0' : 'max-md:translate-y-full'}
              md:h-full md:w-2/5 lg:w-1/3 md:border-l md:border-gray-200`}
          >
            {/* h-9 exactly, and the sheet is 60vh + 2.25rem, so ChatPanel's own h-[60vh] fits
                under this bar without being clipped by the aside's overflow-hidden. */}
            <div className="md:hidden flex-none h-9 flex items-center justify-end px-4">
              <button
                onClick={() => setChatOpen(false)}
                className="text-xs text-gray-400 hover:text-gray-700 transition-colors"
              >
                Close
              </button>
            </div>
            <div className="flex-1 min-h-0 flex flex-col">
              <ChatPanel
                pendingFeedback={pendingFeedback}
                onFeedbackSent={() => setPendingFeedback(null)}
              />
            </div>
          </aside>
        </div>
      </div>
    </HubChatContext.Provider>
  )
}
