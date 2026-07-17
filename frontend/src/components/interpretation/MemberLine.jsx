// One marker within a group: value, ref range, delta, the relations that read
// against THIS marker (present-marker), and the levers that act on it.
//
// Colour rule: a coloured breach indicator appears iff range_gate.is_out_of_range
// — the lab-asserted flag. Everything the platform infers (delta, magnitude,
// verdicts) stays monochrome. An expected-by-phase breach keeps its colour and
// shows its note beside it; the colour marks the fact, the note reframes it.

const DIRECTION_GLYPH = { up: '↑', down: '↓', flat: '→' }

function formatValue(reading) {
  if (reading.value_num == null) return '—'
  return `${reading.value_operator || ''}${reading.value_num}`
}

function formatRefRange(reading) {
  const { ref_low, ref_high } = reading
  if (ref_low == null && ref_high == null) return '—'
  if (ref_low == null) return `≤${ref_high}`
  if (ref_high == null) return `≥${ref_low}`
  return `${ref_low}–${ref_high}`
}

function formatMagnitude(magnitude) {
  return magnitude ? magnitude.replace(/_/g, ' ') : null
}

function DeltaLine({ delta, prior }) {
  if (!delta) {
    return <p className="text-xs text-gray-500">First observation, no prior.</p>
  }
  const parts = []
  if (delta.abs_change != null) parts.push(delta.abs_change > 0 ? `+${delta.abs_change}` : `${delta.abs_change}`)
  if (delta.pct_change != null) parts.push(`${delta.pct_change > 0 ? '+' : ''}${delta.pct_change}%`)
  const magnitude = formatMagnitude(delta.magnitude)

  return (
    <p className="text-xs text-gray-500 tabular-nums">
      <span className="text-gray-400">{DIRECTION_GLYPH[delta.direction] || ''}</span>{' '}
      {parts.length > 0 ? parts.join(' · ') : delta.direction}
      {magnitude && <span className="text-gray-400"> · {magnitude}</span>}
      {delta.censored && <span className="text-gray-400"> · censored</span>}
      {delta.crossed_ref && <span className="text-gray-400"> · {delta.crossed_ref.replace(/_/g, ' ')}</span>}
      {prior?.collected && <span className="text-gray-400"> · vs {prior.collected}</span>}
    </p>
  )
}

function BreachIndicator({ rangeGate }) {
  if (!rangeGate.is_out_of_range) return null
  return (
    <span className="inline-flex items-center gap-1 shrink-0">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" aria-hidden="true" />
      <span className="text-xs font-semibold text-orange-600">
        {rangeGate.flag === 'L' ? 'Below range' : rangeGate.flag === 'H' ? 'Above range' : 'Out of range'}
      </span>
      {rangeGate.expected_by_phase && (
        <span className="text-xs font-normal text-orange-600/70">· expected for phase</span>
      )}
    </span>
  )
}

export default function MemberLine({ member }) {
  const breached = member.range_gate.is_out_of_range

  return (
    <div className="border-t border-gray-100 px-5 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-sm font-medium text-gray-900">{member.display_name}</span>
          <span className="text-sm font-semibold text-gray-900 tabular-nums">
            {formatValue(member.current)}
          </span>
          <span className="text-xs text-gray-500">{member.current.unit_canonical}</span>
          <span className="text-xs text-gray-400 tabular-nums">
            (ref {formatRefRange(member.current)})
          </span>
          {member.news_gate.is_news && (
            <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
              news
            </span>
          )}
        </div>
        <BreachIndicator rangeGate={member.range_gate} />
      </div>

      <DeltaLine delta={member.delta} prior={member.prior} />

      {/* The note: beside the coloured breach when there is one, monochrome when
          there is not. Never dropped either way. */}
      {member.range_gate.note && (
        <p className={`text-xs ${breached ? 'text-orange-700 bg-orange-50 rounded-lg px-2 py-1' : 'text-gray-500'}`}>
          {member.range_gate.note}
        </p>
      )}

      {member.relations_rendered.length > 0 && (
        <ul className="space-y-1">
          {member.relations_rendered.map((rel) => (
            <li key={rel.relation_key} className="text-xs text-gray-600 pl-2 border-l-2 border-gray-200">
              <span className="text-gray-400">{rel.kind} · {rel.partner}</span>{' '}
              {rel.reads}
            </li>
          ))}
        </ul>
      )}

      {/* Mechanism slot — real text arrives with the producer (increment 4). */}
      <p className="text-xs text-gray-400 italic">{member.mechanism.text}</p>

      {member.member_lever_effects.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {member.member_lever_effects.map((effect) => (
            <span
              key={effect.lever_key}
              className="text-xs text-gray-600 bg-gray-100 rounded-full px-2 py-0.5"
            >
              {effect.lever_key} {effect.direction} · {effect.grade}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
