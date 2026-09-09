// ClosePhaseDialog — close the open phase to baseline (Exposure UI increment 2, W2).
//
// One required field, `close_reason`: the server requires it, and an empty reason is the "reads as
// an accident" case #222 exists to prevent — so Confirm is disabled until the reason is non-empty.
// The server is the validator; on 422 we show its `detail`. A 404 means there is no open phase to
// close — its own message, not a generic fault.

import { useState } from 'react'
import api from '../../api'
import { formatApiError } from '../../lib/apiError'

export default function ClosePhaseDialog({ onWritten, onCancel }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const canConfirm = reason.trim() !== '' && !submitting

  async function confirm() {
    setError('')
    setSubmitting(true)
    try {
      await api.post('/engine/phase/close', { close_reason: reason.trim() })
      onWritten?.()
    } catch (err) {
      if (err.response?.status === 404) setError('No open phase to close.')
      else setError(formatApiError(err, 'Could not close the phase.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-white border border-gray-300 rounded-2xl p-4 flex flex-col gap-3">
      <p className="text-sm font-semibold text-gray-900">Close to baseline</p>
      <p className="text-xs text-gray-500 leading-snug">
        Closing the open phase returns the engine to baseline. A reason is required — the ledger is
        append-only and an empty close reads as an accident.
      </p>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-gray-700">Close reason</span>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. phase complete — progressing to base"
          className="w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5 text-gray-800
            focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
      </label>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={confirm}
          disabled={!canConfirm}
          className="flex-1 bg-red-600 text-white rounded-xl py-2 text-sm font-medium
            hover:bg-red-700 transition-colors disabled:opacity-50"
        >
          {submitting ? 'Closing…' : 'Confirm — close to baseline'}
        </button>
        <button
          type="button"
          onClick={() => onCancel?.()}
          disabled={submitting}
          className="px-4 bg-white text-gray-600 border border-gray-300 rounded-xl py-2
            text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
