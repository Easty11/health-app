// Deep-sleep levers, rendered as education (#47).
//
// Collapsed by default: this is reference material, not a nightly task list, and an
// always-open block of five mechanisms would compete with the close-out form.
//
// The list is rendered in its authored order for every reader and is never scored,
// filtered, or reordered — see the #47 note in `leverContent.js`. Nothing here reads
// the user's record.

import { useState } from 'react'
import {
  CLEARANCE_RATIONALE, DEEP_SLEEP_LEVERS, TITRATION_SCOPE_NOTE, gradeLabel,
} from './leverContent'

const GRADE_CLASS = {
  strong: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200',
  emerging: 'bg-gray-100 text-gray-600 border-gray-200',
}

export default function DeepSleepLevers() {
  const [open, setOpen] = useState(false)

  return (
    <div className="bg-white border border-gray-200 rounded-2xl mb-4 text-left overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-center justify-between text-left
          hover:bg-gray-50 transition-colors"
      >
        <span>
          <span className="text-sm font-semibold text-gray-900">What drives deep sleep</span>
          <span className="block text-[11px] text-gray-400 mt-0.5">
            Five levers, evidence-ranked
          </span>
        </span>
        <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100 pt-3">
          <p className="text-[11px] text-gray-600 leading-relaxed bg-gray-50 rounded-xl px-3 py-2">
            {TITRATION_SCOPE_NOTE}
          </p>

          <ol className="space-y-3">
            {DEEP_SLEEP_LEVERS.map((lever) => (
              <li key={lever.key}>
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-gray-900">{lever.title}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      GRADE_CLASS[lever.grade] ?? GRADE_CLASS.emerging
                    }`}
                  >
                    {gradeLabel(lever.grade)}
                  </span>
                </div>
                <p className="text-[11px] text-gray-600 leading-relaxed mt-0.5">
                  {lever.mechanism}
                </p>
                {lever.note && (
                  <p className="text-[11px] text-gray-400 leading-relaxed mt-0.5">{lever.note}</p>
                )}
              </li>
            ))}
          </ol>

          <div className="border-t border-gray-100 pt-3">
            <p className="text-[11px] text-gray-600 leading-relaxed">
              <span className="font-medium text-gray-700">Why deep sleep: </span>
              {CLEARANCE_RATIONALE.claim}
            </p>
            <p className="text-[11px] text-gray-400 leading-relaxed mt-1">
              {CLEARANCE_RATIONALE.confidence}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
