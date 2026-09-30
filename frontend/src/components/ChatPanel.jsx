import { useState, useRef, useEffect } from 'react'
import api from '../api'

function getStorageKey() {
  const token = localStorage.getItem('token')
  if (!token) return 'chat_history'
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return `chat_history_${payload.sub}`
  } catch {
    return 'chat_history'
  }
}

// The session under review persists with the conversation (Q194, ruled option b): once a review pushes a
// `focus_session`, every later turn resends it until a new focus replaces it, the operator dismisses it,
// or the chat is cleared. Stored beside the history so a reload keeps both.
function getFocusKey() {
  return `${getStorageKey()}_focus`
}

const EMPTY_REPLY = '⚠️ No response came back for that message, and nothing was saved. Send it again.'

function Message({ role, content }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-indigo-600 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-800 rounded-bl-sm'
        }`}
      >
        {content}
      </div>
    </div>
  )
}

export default function ChatPanel({ pendingFeedback, onFeedbackSent }) {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem(getStorageKey())
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })
  // `{ focus: {kind, id, scope}, label }` or null. The label is the review's own short message.
  const [pinned, setPinned] = useState(() => {
    try {
      const saved = localStorage.getItem(getFocusKey())
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  // Ref on the scroll container div itself, not a sentinel inside it.
  // We scroll the container's scrollTop directly to avoid triggering
  // page-level scrolling that scrollIntoView can cause.
  const scrollContainerRef = useRef(null)
  const textareaRef = useRef(null)

  function scrollToBottom() {
    const el = scrollContainerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  useEffect(() => {
    try { localStorage.setItem(getStorageKey(), JSON.stringify(messages)) } catch {}
  }, [messages])

  useEffect(() => {
    try {
      if (pinned) localStorage.setItem(getFocusKey(), JSON.stringify(pinned))
      else localStorage.removeItem(getFocusKey())
    } catch { /* storage unavailable: the focus simply does not survive a reload */ }
  }, [pinned])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  // A fresh conversation: history and the pinned session both go.
  function newChat() {
    setMessages([])
    setPinned(null)
    setInput('')
  }

  // `newPin` ({ focus, label }) is a review that sets a NEW focus; without one the turn carries the pinned
  // focus, if any (a typed follow-up, or a push that names no session).
  async function sendMessage(text, currentMessages, newPin = null) {
    if (!text || loading) return

    const active = newPin ?? pinned
    if (newPin) setPinned(newPin)

    const base = currentMessages ?? messages
    const userMsg = { role: 'user', content: text }
    const nextMessages = [...base, userMsg]
    setMessages(nextMessages)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    setLoading(true)

    try {
      const history = nextMessages.slice(0, -1)
      const { data } = await api.post('/chat', {
        message: text,
        conversation_history: history,
        // A session review names its session; the server loads and renders it (server-side `session_focus`).
        ...(active ? { focus_session: active.focus } : {}),
      })
      // Never an empty bubble (Q187): the server guarantees text, and this catches anything that
      // still arrives blank, saying plainly that nothing came back.
      const reply = typeof data?.response === 'string' && data.response.trim() ? data.response : EMPTY_REPLY
      setMessages([...nextMessages, { role: 'assistant', content: reply }])
    } catch (err) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: '⚠️ ' + (err.response?.data?.detail || 'Something went wrong') },
      ])
    } finally {
      setLoading(false)
    }
  }

  // Auto-send when a message is pushed in from a panel (`{ message, focus }`; a bare string is a message
  // with no session focus). The user bubble shows only the short message; the session rides as a reference.
  useEffect(() => {
    if (pendingFeedback) {
      const { message, focus } = typeof pendingFeedback === 'string'
        ? { message: pendingFeedback, focus: null }
        : pendingFeedback
      sendMessage(message, messages, focus ? { focus, label: message } : null)
      onFeedbackSent?.()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFeedback])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input.trim())
    }
  }

  return (
    // On mobile: 60vh so the workout panel stays visible below.
    // On md+: h-full fills the flex column from the dashboard layout.
    <div className="flex flex-col h-[60vh] md:h-full">

      {/* Header */}
      <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-gray-800">AI Assistant</h2>
            <p className="text-xs text-gray-400 mt-0.5">Ask anything about your training</p>
          </div>
          {(messages.length > 0 || pinned) && (
            <button onClick={newChat} disabled={loading}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-40 shrink-0">
              New chat
            </button>
          )}
        </div>
        {pinned && (
          <div className="mt-2 flex items-center justify-between gap-2 bg-indigo-50 border border-indigo-100 rounded-lg px-2.5 py-1.5">
            <span className="text-xs text-indigo-700 truncate">Reviewing: {pinned.label}</span>
            <button onClick={() => setPinned(null)} aria-label="Stop reviewing this session"
              className="text-indigo-400 hover:text-indigo-700 text-sm leading-none shrink-0">×</button>
          </div>
        )}
      </div>

      {/* Scroll container — this div scrolls independently, not the page.
          flex-col + mt-auto on the inner wrapper anchors messages to the
          bottom (few messages sit at the bottom; many scroll up). */}
      <div
        ref={scrollContainerRef}
        className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col"
      >
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm mt-8">
            <p className="text-2xl mb-2">💬</p>
            <p>Ask about your workouts, progress, or get recommendations.</p>
          </div>
        )}
        <div className="mt-auto space-y-1">
          {messages.map((msg, i) => (
            <Message key={i} role={msg.role} content={msg.content} />
          ))}
          {loading && (
            <div className="flex justify-start mb-3">
              <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input area — kept outside the scroll container and pinned to the
          bottom so it is always visible (flex-none + sticky bottom-0). */}
      <div className="flex-none sticky bottom-0 z-10 px-4 py-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
            onKeyDown={handleKeyDown}
            placeholder="Message…"
            className="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed overflow-hidden"
            style={{ minHeight: '42px' }}
          />
          <button
            onClick={() => sendMessage(input.trim())}
            disabled={loading || !input.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors shrink-0"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1.5">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}
