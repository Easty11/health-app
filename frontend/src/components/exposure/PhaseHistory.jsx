// PhaseHistory — the phase ledger, read-only (Exposure UI increment 2, W3).
//
// Append-only is the ledger's invariant and the UI must not imply otherwise: nothing here is
// editable. Collapsed by default; the rows are fetched from /engine/phase/history on the first
// expand and then kept — re-expanding does not refetch. Rows render newest first exactly as served
// (entered_on desc); no client-side re-sort.

import { useState } from 'react'
import api from '../../api'

function Chip({ children }) {
  return (
    <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
      {children}
    </span>
  )
}

export default function PhaseHistory() {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState(null) // null = not yet fetched
  const [status, setStatus] = useState('idle') // idle | loading | ready | error

  function expand() {
    const next = !open
    setOpen(next)
    if (next && rows === null && status !== 'loading') {
      setStatus('loading')
      api.get('/engine/phase/history')
        .then((res) => {
          setRows(Array.isArray(res.data) ? res.data : [])
          setStatus('ready')
        })
        .catch(() => setStatus('error'))
    }
  }

  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      <button
        type="button"
        onClick={expand}
        aria-expanded={open}
        className="flex items-center gap-1 text-sm font-semibold text-gray-900 text-left"
      >
        <span className="text-gray-400 text-xs">{open ? '▾' : '▸'}</span>
        Phase history
      </button>

      {open && status === 'loading' && (
        <p className="text-xs text-gray-500">Reading the ledger…</p>
      )}
      {open && status === 'error' && (
        <p className="text-xs text-red-600">Could not load the phase history.</p>
      )}
      {open && status === 'ready' && rows.length === 0 && (
        <p className="text-xs text-gray-500">No phases recorded yet.</p>
      )}

      {open && status === 'ready' && rows.length > 0 && (
        <ul className="flex flex-col divide-y divide-gray-100">
          {rows.map((r) => (
            <li key={r.id} className="py-2 flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-gray-800">{r.label}</span>
                <span className="text-[11px] text-gray-500">{r.probe_posture}</span>
              </div>
              <p className="text-[11px] text-gray-500">
                {r.entered_on} → {r.closed_on || 'open'}
              </p>
              {r.close_reason && (
                <p className="text-[11px] text-gray-500 leading-snug">Closed: {r.close_reason}</p>
              )}
              <div className="flex flex-wrap gap-1 items-center">
                {r.capacities === null ? <Chip>all</Chip> : (r.capacities ?? []).map((c) => (
                  <Chip key={c}>{c}</Chip>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
