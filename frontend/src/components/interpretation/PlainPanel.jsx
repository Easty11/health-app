// Plain-register overlay (interpretation increment 2, DECISIONS_LOG #202).
//
// Reads GET /interpretation/presentation?register=plain. The SERVER decides what `text` is:
// the promoted plain-language overlay if one is human_verified for this exact base text, or
// the clinical template otherwise. The toggle is a preference; eligibility is server-side and
// unconditional — this component never assembles claims, it renders what the server returns.
//
// When the server returns an un-promoted `draft` (status ai_draft), it is shown in a review
// card with an approve action (POST .../promote) — the #194-style training-wheels gate. The
// overlay is disposable and never the record; nothing here writes or parses structured fields.

import { useEffect, useState } from 'react'
import api from '../../api'

function paragraphs(text) {
  return (text || '').split('\n\n').map((s) => s.trim()).filter(Boolean)
}

export default function PlainPanel() {
  const [data, setData] = useState(null)
  const [phase, setPhase] = useState('loading') // loading | ready | error
  const [promoting, setPromoting] = useState(false)

  function load() {
    setPhase('loading')
    api
      .get('/interpretation/presentation', { params: { register: 'plain' } })
      .then((res) => {
        setData(res.data)
        setPhase('ready')
      })
      .catch(() => setPhase('error'))
  }

  useEffect(load, [])

  function promote(id) {
    setPromoting(true)
    api
      .post(`/interpretation/presentation/${id}/promote`)
      .then(load)
      .catch(() => setPhase('error'))
      .finally(() => setPromoting(false))
  }

  if (phase === 'loading') {
    return (
      <div className="bg-white border border-gray-200 rounded-2xl p-10 text-center space-y-3">
        <div className="w-8 h-8 mx-auto rounded-full border-2 border-gray-200 border-t-indigo-600 animate-spin" />
        <p className="text-sm text-gray-500">Preparing the plain-language view…</p>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-6 space-y-2">
        <p className="text-sm font-semibold text-red-800">Could not load the plain-language view</p>
        <p className="text-xs text-red-700">
          This is a fault, not an empty result — your data is unaffected. The standard clinical view
          is unchanged; switch back to it above, or reload to try again.
        </p>
      </div>
    )
  }

  const paras = paragraphs(data.text)
  const draft = data.draft
  const showingTemplate = data.register_served !== 'plain'

  return (
    <div className="space-y-4">
      {showingTemplate && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3">
          <p className="text-xs text-amber-800">
            The plain-language view isn’t approved for this panel yet, so this is the standard
            wording.{draft ? ' A draft is waiting for your review below.' : ''}
          </p>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-3">
        {paras.map((p, i) => (
          <p key={i} className="text-sm text-gray-700 leading-relaxed">
            {p}
          </p>
        ))}
      </div>

      {draft && draft.status === 'ai_draft' && (
        <div className="bg-white border border-indigo-200 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              Plain-language draft · pending your approval
            </p>
            <span className="text-[11px] text-gray-400">ai_draft</span>
          </div>
          <div className="space-y-2">
            {paragraphs(draft.text).map((p, i) => (
              <p key={i} className="text-sm text-gray-600 leading-relaxed">
                {p}
              </p>
            ))}
          </div>
          <button
            type="button"
            disabled={promoting}
            onClick={() => promote(draft.id)}
            className="inline-block bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-2xl px-5 py-2.5 text-sm transition-colors"
          >
            {promoting ? 'Approving…' : 'Approve for plain view'}
          </button>
          <p className="text-[11px] text-gray-400">
            Approving shows this wording whenever the plain view is on, until the panel changes.
          </p>
        </div>
      )}
    </div>
  )
}
