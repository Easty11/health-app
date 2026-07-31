// One ungrouped marker: a marker no authored group claims.
//
// DELIBERATELY NOT `MemberLine`. Ungrouped rows carry no `relations_rendered`, `mechanism`,
// `member_lever_effects`, `stable_rationale` or `role` — by construction, not omission: with no
// group, nothing in the interpretive layer attaches. `MemberLine` reads
// `member.relations_rendered.length` and `member.mechanism.text` unconditionally and would throw
// on every one of these rows. Rendering them through a separate component keeps that absence
// structural rather than defensive, and keeps the flat shape visible to a reader.
//
// Whether marker-authored fields SHOULD appear here is Q64, open — this renders what exists.

const DIRECTION_GLYPH = { up: '↑', down: '↓', flat: '→' }

function formatValue(reading) {
  if (!reading || reading.value_num == null) return '—'
  return `${reading.value_operator || ''}${reading.value_num}`
}

function formatRefRange(reading) {
  if (!reading) return '—'
  const { ref_low, ref_high } = reading
  if (ref_low == null && ref_high == null) return '—'
  if (ref_low == null) return `≤${ref_high}`
  if (ref_high == null) return `≥${ref_low}`
  return `${ref_low}–${ref_high}`
}

export default function UngroupedLine({ row, panelCollected }) {
  const breached = row.range_gate?.is_out_of_range
  const collected = row.current?.collected
  const stale = collected && panelCollected && collected !== panelCollected

  return (
    <div className="border-t border-gray-100 first:border-t-0 px-5 py-2.5">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-sm text-gray-900">{row.display_name || row.marker_canonical}</span>
          <span className="text-sm font-semibold text-gray-900 tabular-nums">
            {formatValue(row.current)}
          </span>
          <span className="text-xs text-gray-500">{row.current?.unit_canonical}</span>
          <span className="text-xs text-gray-400 tabular-nums">(ref {formatRefRange(row.current)})</span>
          {row.news_gate?.is_news && (
            <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
              news
            </span>
          )}
          {/* Same staleness signal as MemberLine — Q69's mitigation applies to every row that
              carries a value, not only to grouped ones. */}
          {stale && (
            <span className="text-xs text-amber-700 bg-amber-50 rounded-full px-2 py-0.5 tabular-nums">
              from {collected}, not this panel
            </span>
          )}
        </div>
        {breached && (
          <span className="inline-flex items-center gap-1 shrink-0">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" aria-hidden="true" />
            <span className="text-xs font-semibold text-orange-600">
              {row.range_gate.flag === 'L'
                ? 'Below range'
                : row.range_gate.flag === 'H'
                  ? 'Above range'
                  : 'Out of range'}
            </span>
          </span>
        )}
      </div>
      {row.delta && (
        <p className="text-xs text-gray-500 tabular-nums">
          <span className="text-gray-400">{DIRECTION_GLYPH[row.delta.direction] || ''}</span>{' '}
          {row.delta.pct_change != null
            ? `${row.delta.pct_change > 0 ? '+' : ''}${row.delta.pct_change}%`
            : row.delta.direction}
          {row.delta.censored && <span className="text-gray-400"> · censored</span>}
          {row.prior?.collected && <span className="text-gray-400"> · vs {row.prior.collected}</span>}
        </p>
      )}
    </div>
  )
}
