import { useCallback, useState, useEffect } from 'react'
import api from '../api'
import useRecoveryRefresh from '../lib/useRecoveryRefresh'

function fmtMins(minutes) {
  if (minutes == null) return '—'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtDate(dateStr) {
  if (!dateStr) return ''
  // Use noon to avoid UTC midnight day-shift issues
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'short' })
}

function fmtShortDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function sourceLabel(source) {
  if (!source) return null
  return source.charAt(0).toUpperCase() + source.slice(1)
}

function colorText(value, greenMin, amberMin) {
  if (value == null) return 'text-gray-300'
  if (value >= greenMin) return 'text-green-600'
  if (value >= amberMin) return 'text-amber-500'
  return 'text-red-500'
}

function colorBorder(delta) {
  if (delta == null) return 'border-gray-200'
  if (delta > 2) return 'border-green-400'
  if (delta >= -5) return 'border-amber-400'
  return 'border-red-400'
}

function SleepMetricCard({ label, value, color }) {
  return (
    <div className="bg-gray-50 rounded-xl p-3 text-center">
      <p className={`text-lg font-bold leading-none ${color}`}>{value}</p>
      <p className="text-xs text-gray-400 mt-1">{label}</p>
    </div>
  )
}

export default function HealthPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Re-fetch the summary WITHOUT blanking the card on failure — used when a Garmin refresh
  // actually ingested a new night, so the newest HRV is reflected without a manual reload.
  const refetchSummary = useCallback(() => {
    return api.get('/health/summary')
      .then(({ data }) => setData(data))
      .catch(() => {}) // a background re-fetch must never blank a card already showing data
  }, [])

  // First paint: load the cached summary. A failure HERE (not a re-fetch) drops to the empty
  // state; this is the only path that may clear `data`.
  useEffect(() => {
    let cancelled = false
    api.get('/health/summary')
      .then(({ data }) => { if (!cancelled) setData(data) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // On mount, ask the server to pull this morning's Garmin HRV (server-gated, #299); on a REAL
  // run re-fetch the summary so the card updates. force = pull-to-refresh. Never blocks paint.
  const { refreshing, forceRefresh } = useRecoveryRefresh({ onFreshRun: refetchSummary })

  if (loading) {
    return (
      <div className="flex flex-col h-full p-4 space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-10 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  const latest = data?.latest          // Samsung device row — sleep architecture + vitals
  const latestHrv = data?.latest_hrv   // newest HRV across sources, source-labelled (Q130/#292)
  if (!latest && !latestHrv) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-center px-6 py-8">
        <p className="text-3xl mb-3">💤</p>
        <p className="text-sm text-gray-500 font-medium">No recovery data</p>
        <p className="text-xs text-gray-400 mt-1">Run extraction in the companion app</p>
      </div>
    )
  }

  const { vs_baseline, baseline_hrv, trend } = data
  const readingCount = trend?.length ?? 0

  // Headline HRV = newest reading across sources, source-labelled. Fall back to the Samsung
  // device reading when the API predates `latest_hrv` (never regress an older backend).
  const hrvValue = latestHrv?.hrv_ms ?? latest?.hrv_ms ?? null
  const hrvSource = latestHrv?.source ?? (latest ? 'samsung' : null)
  const hrvDate = latestHrv?.captured_at ?? latest?.captured_at
  const isSamsungHrv = hrvSource === 'samsung'

  // The ±baseline badge is Samsung-native: vs_baseline compares the Samsung latest to the
  // Samsung 7-day mean. Only show it when the headline HRV is itself Samsung — never pin a
  // Samsung baseline delta onto a Garmin number (the cross-device offset is non-constant, so
  // "above/below baseline" would be meaningless across instruments). A Garmin headline shows
  // Garmin's own status band when it carries one.
  let hrvBadgeText, hrvBadgeClass
  if (isSamsungHrv && vs_baseline != null) {
    if (vs_baseline > 2) {
      hrvBadgeText = `↑ ${Math.abs(vs_baseline)}ms above baseline`
      hrvBadgeClass = 'bg-green-100 text-green-700'
    } else if (vs_baseline >= -5) {
      hrvBadgeText = '~ Near baseline'
      hrvBadgeClass = 'bg-amber-100 text-amber-700'
    } else {
      hrvBadgeText = `↓ ${Math.abs(vs_baseline)}ms below baseline`
      hrvBadgeClass = 'bg-red-100 text-red-700'
    }
  } else if (!isSamsungHrv && latestHrv?.status && latestHrv.status !== 'NONE') {
    hrvBadgeText = latestHrv.status
    hrvBadgeClass = 'bg-gray-100 text-gray-600'
  } else {
    hrvBadgeText = 'No baseline'
    hrvBadgeClass = 'bg-gray-100 text-gray-500'
  }

  const borderDelta = isSamsungHrv ? vs_baseline : null

  const sleepMins = latest ? (latest.total_sleep_time_minutes ?? latest.actual_sleep_time_minutes) : null
  const sleepColor = colorText(sleepMins, 420, 360)
  const effColor = colorText(latest?.sleep_efficiency_pct, 85, 80)
  const deepColor = colorText(latest?.deep_minutes, 60, 40)
  const remColor = colorText(latest?.rem_minutes, 60, 45)

  // Sleep stages bar
  const deep = latest?.deep_minutes ?? 0
  const rem = latest?.rem_minutes ?? 0
  const light = latest?.light_minutes ?? 0
  const awake = latest?.awake_minutes ?? 0
  const stagesTotal = deep + rem + light + awake
  const pct = (v) => stagesTotal > 0 ? `${((v / stagesTotal) * 100).toFixed(1)}%` : '0%'

  // Sleep is Samsung-measured; if it is from a different night than the headline HRV
  // (e.g. Garmin HRV synced for last night before the Samsung scraper caught up), say so.
  const sleepDate = latest?.captured_at
  const sleepIsOlderThanHrv = sleepDate && hrvDate && sleepDate !== hrvDate

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-800">Recovery</h2>
        <div className="flex items-center gap-2">
          {refreshing && (
            <span className="text-[11px] text-gray-400" role="status">refreshing…</span>
          )}
          <span className="text-xs text-gray-400">{fmtDate(hrvDate)}</span>
          <button
            type="button"
            onClick={forceRefresh}
            disabled={refreshing}
            className="text-xs font-medium text-blue-500 hover:text-blue-600 disabled:text-gray-300"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 px-4 py-4 space-y-4">
        {/* HRV readiness card */}
        <div className={`border-l-4 ${colorBorder(borderDelta)} bg-white rounded-xl shadow-sm p-4`}>
          <div className="flex items-baseline gap-1.5 mb-2">
            <span className="text-3xl font-bold text-gray-900">
              {hrvValue != null ? Math.round(hrvValue) : '—'}
            </span>
            <span className="text-sm text-gray-400">ms HRV</span>
            {sourceLabel(hrvSource) && (
              <span className="ml-auto text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
                {sourceLabel(hrvSource)}
              </span>
            )}
          </div>
          <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${hrvBadgeClass}`}>
            {hrvBadgeText}
          </span>
          {baseline_hrv != null && isSamsungHrv && (
            <p className="text-xs text-gray-400 mt-2">
              7-day avg: {baseline_hrv}ms ({readingCount} reading{readingCount !== 1 ? 's' : ''})
            </p>
          )}
        </div>

        {latest ? (
          <>
            {sleepIsOlderThanHrv && (
              <p className="text-xs text-gray-400 -mt-2">
                Sleep from Samsung · {fmtShortDate(sleepDate)}
              </p>
            )}

            {/* Sleep 2×2 grid */}
            <div className="grid grid-cols-2 gap-2">
              <SleepMetricCard
                label="Duration"
                value={fmtMins(sleepMins)}
                color={sleepColor}
              />
              <SleepMetricCard
                label="Efficiency"
                value={latest.sleep_efficiency_pct != null ? `${latest.sleep_efficiency_pct}%` : '—'}
                color={effColor}
              />
              <SleepMetricCard
                label="Deep"
                value={latest.deep_minutes != null ? `${latest.deep_minutes}m` : '—'}
                color={deepColor}
              />
              <SleepMetricCard
                label="REM"
                value={latest.rem_minutes != null ? `${latest.rem_minutes}m` : '—'}
                color={remColor}
              />
            </div>

            {/* Sleep stages bar */}
            {stagesTotal > 0 && (
              <div>
                <div className="flex rounded-full overflow-hidden h-2.5">
                  {deep > 0 && <div className="bg-indigo-500" style={{ width: pct(deep) }} />}
                  {rem > 0 && <div className="bg-purple-400" style={{ width: pct(rem) }} />}
                  {light > 0 && <div className="bg-gray-300" style={{ width: pct(light) }} />}
                  {awake > 0 && <div className="bg-orange-200" style={{ width: pct(awake) }} />}
                </div>
                <p className="text-xs text-gray-400 mt-1.5">
                  Deep {deep}m · REM {rem}m · Light {light}m · Awake {awake}m
                </p>
              </div>
            )}

            {/* Vitals row */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'Resp Rate', value: latest.respiratory_rate != null ? `${latest.respiratory_rate.toFixed(1)}` : '—', unit: 'br/m' },
                { label: 'Sleep HR', value: latest.sleep_hr_bpm ?? '—', unit: 'bpm' },
                { label: 'SpO2', value: latest.spo2_average_pct != null ? `${latest.spo2_average_pct.toFixed(1)}` : '—', unit: '%' },
              ].map(({ label, value, unit }) => (
                <div key={label} className="bg-gray-50 rounded-xl p-3 text-center">
                  <p className="text-base font-semibold text-gray-700">
                    {value}<span className="text-xs font-normal text-gray-400 ml-0.5">{unit}</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{label}</p>
                </div>
              ))}
            </div>

            {/* Sleep timing */}
            {(latest.bedtime || latest.wake_time) && (
              <p className="text-xs text-gray-400 text-center">
                Bedtime {latest.bedtime ?? '—'} → Wake {latest.wake_time ?? '—'}
              </p>
            )}
          </>
        ) : (
          <p className="text-xs text-gray-400 text-center">
            Sleep architecture not yet synced for this night.
          </p>
        )}
      </div>
    </div>
  )
}
