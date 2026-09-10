import { useState } from 'react'
import { Link } from 'react-router-dom'
import LoadChart from '../components/charts/LoadChart'
import FormChart from '../components/charts/FormChart'
import ReadinessChart from '../components/charts/ReadinessChart'
import ExerciseChart from '../components/charts/ExerciseChart'
import { usePhaseMarkers } from '../components/charts/PhaseMarkers'

// The training-performance view (Visuals increments 1–3). The lab surface — ingestion,
// stored results, upload history — used to share this page; it now lives at /labs (STEP 0
// of increment 4: a new surface gets a home before it gets a chart). This page is the four
// charts only, and is where increment 4's weekly wrap and phase caption will mount.

export default function Metrics() {
  // Range shared across the three Banister-view charts (Visuals increment 2). Lifted here so a
  // single control drives them all: the LoadChart renders the selector (its lead role) and
  // reports changes up, and FormChart / ReadinessChart take the chosen window as a prop.
  const [chartDays, setChartDays] = useState(90)
  // Training-phase boundaries, fetched ONCE for the page and overlaid on every chart below
  // (Visuals increment 3, D4). An empty list until resolved — markers are an overlay, never a
  // precondition for a chart to draw.
  const phaseMarkers = usePhaseMarkers()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Metrics</span>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-5 space-y-4">
        {/* Banister view (Visuals increments 1–3). The range is shared: LoadChart owns the
            visible selector and lifts the chosen window to `chartDays`, which the others follow.
            LoadChart (work-done per window) and FormChart (fitness/fatigue/form) read
            /series/load; ReadinessChart reads /series/readiness; ExerciseChart (per-exercise
            e1RM + volume) reads /series/exercise*. Training-phase boundaries (`phaseMarkers`,
            one fetch of /engine/phase/history) are overlaid on all four. */}
        <LoadChart days={chartDays} onSelectRange={setChartDays} markers={phaseMarkers} />
        <FormChart days={chartDays} markers={phaseMarkers} />
        <ExerciseChart days={chartDays} markers={phaseMarkers} />
        <ReadinessChart days={chartDays} markers={phaseMarkers} />
      </div>
    </div>
  )
}
