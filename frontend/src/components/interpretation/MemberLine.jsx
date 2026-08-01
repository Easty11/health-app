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

// The collection date of THIS marker's current value. `marker_series` has no temporal bound, so a
// group can render entirely off a draw months before the trigger panel (Q69/#159).
//
// SUPPRESSED WHEN THE GROUP ALREADY SAYS IT. Found by reading the live page: with a member badge
// on every stale marker the page carried FORTY "not this panel" labels, five of them repeating
// the one the hepatocellular group header had just stated. Repetition at that volume is how a
// signal becomes wallpaper, and it drowned the group-level label #159 exists to add.
//
// So the two levels divide the work exactly as #159 rules 1 and 2 do:
//   * group COHERENT  -> the group header states the date once; members stay silent.
//   * group SPANS     -> the header can only give a range, so each member carries its own date,
//                        which is the detail rule 2 asks for.
// Ungrouped rows have no group to defer to and keep their own badge (see UngroupedLine).
function CollectedFrom({ collected, panelCollected, groupAsOf }) {
  if (!collected || collected === panelCollected) return null
  if (groupAsOf && !groupAsOf.spans_draws) return null   // the group header already said it
  return (
    <span className="text-xs text-amber-700 bg-amber-50 rounded-full px-2 py-0.5 tabular-nums">
      from {collected}, not this panel
    </span>
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

export default function MemberLine({ member, panelCollected, groupAsOf }) {
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
          <CollectedFrom collected={member.current?.collected} panelCollected={panelCollected} groupAsOf={groupAsOf} />
        </div>
        <BreachIndicator rangeGate={member.range_gate} />
      </div>

      <DeltaLine delta={member.delta} prior={member.prior} />

      {/* `range_gate.note` was removed here: range_gate is {is_out_of_range, flag} and carries no
          note. The block rendered nothing and implied the producer supplies breach prose. An
          expected-by-phase breach is now stated on the relation, not on the gate. */}

      {member.relations_rendered.length > 0 && (
        <ul className="space-y-1">
          {member.relations_rendered.map((rel) => (
            <li key={rel.relation_key} className="text-xs text-gray-600 pl-2 border-l-2 border-gray-200">
              {/* `rel.partner` was removed: a single partner cannot express a multi-operand
                  relation, and the contract carries `operands_missing` + `operand_status`
                  instead. A degraded relation NAMES what it could not see — dropping that was
                  showing a partial reading as a whole one. */}
              <span className="text-gray-400">{rel.kind}</span>{' '}
              {rel.reads}
              {rel.operand_status === 'degraded' && (
                <span className="text-amber-700"> · partial: no {rel.operands_missing.join(', ')}</span>
              )}
              {rel.precondition_status === 'not_satisfied' && (
                <span className="text-amber-700"> · not expected in this phase</span>
              )}
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
