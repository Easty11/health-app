// Which way fatigue is moving, for the home load card. Direction only: no band, no verdict (F1).
//
// It looks back one acute window (7 days, #33) rather than minting a new constant, and compares
// against the nearest stored day on or before that date. Under a week of history there is no
// arrow, not a guess.

export const DIRECTION_LOOKBACK_DAYS = 7

export const round1 = (n) => Math.round(n * 10) / 10

export function fatigueDirection(points) {
  if (!points || points.length < 2) return null
  const last = points[points.length - 1]
  const lastDay = new Date(`${last.day}T00:00:00Z`).getTime()
  const target = lastDay - DIRECTION_LOOKBACK_DAYS * 86400000
  const prior = [...points].reverse().find((p) => new Date(`${p.day}T00:00:00Z`).getTime() <= target)
  if (!prior) return null
  const delta = round1(last.fatigue) - round1(prior.fatigue)
  if (delta > 0) return { arrow: '▲', text: 'fatigue rising', key: 'rising' }
  if (delta < 0) return { arrow: '▼', text: 'fatigue easing', key: 'easing' }
  return { arrow: '●', text: 'fatigue steady', key: 'steady' }
}
