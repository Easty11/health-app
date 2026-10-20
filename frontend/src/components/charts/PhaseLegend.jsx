import { LEGEND_TITLE, NO_DATA_YET, bandLayout, phaseBandOpacity } from './PhaseMarkers'

// One legend per card (R11): the key to the shaded phase bands behind that card's charts. It
// reads the same `markers` and the same rows the card's charts draw, so it lists exactly the
// phases visible in the card's window, plus any phase that starts after the last data day, which
// has no band to draw and is marked "no data yet" rather than dropped. Renders nothing when there
// is nothing to key.
export default function PhaseLegend({ markers, data, xKey }) {
  const { legend } = bandLayout(markers, data, xKey)
  if (!legend.length) return null
  return (
    <ul aria-label={LEGEND_TITLE} className="phase-legend flex flex-wrap items-center gap-x-3 gap-y-1 m-0 p-0 list-none text-[11px] text-gray-500">
      <li className="font-medium text-gray-600">{LEGEND_TITLE}</li>
      {legend.map((p) => (
        <li key={p.label} className="phase-legend__item flex items-center gap-1" data-no-data={p.noDataYet ? 'true' : 'false'}>
          {/* The swatch is the band's own fill at the band's own opacity, outlined so it reads on
              white; a phase with no band yet is the outline alone, dashed. */}
          <span
            aria-hidden="true"
            className="phase-legend__swatch relative inline-block h-2.5 w-4 rounded-sm"
            style={{ border: `1px ${p.noDataYet ? 'dashed' : 'solid'} ${p.color}` }}
          >
            {!p.noDataYet && (
              <span className="absolute inset-0" style={{ background: p.color, opacity: phaseBandOpacity }} />
            )}
          </span>
          <span>{p.label}</span>
          {p.noDataYet && <span className="text-gray-400">({NO_DATA_YET})</span>}
        </li>
      ))}
    </ul>
  )
}
