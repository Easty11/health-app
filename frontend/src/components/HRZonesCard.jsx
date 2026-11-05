// Settings -> "Heart rate zones" (design 0010 §6): per sport class the basis and today's bpm bands; the anchors
// (HRmax, LTHR, resting HR) in force with provenance, effective date and a retest flag; the HRmax prompts; the
// Garmin mirror strip; and the append form for LTHR / RHR with the FORCED choice (dated change vs restatement,
// #383 semantics) and a bpm preview before Save. The server decides everything shown (GET /hr-zones/config);
// this renders it as sent. HRmax is read-only here: its one writer is the operator script, which the card names.
//
// After a successful append the card forces the load chain (POST /load/refresh?force=true) so every row re-zones
// and the metabolic series recomputes at once; the chain's own report is not rendered, only that it ran.

import { useEffect, useState } from 'react'
import api from '../api'

const KIND_ORDER = ['hrmax', 'lthr', 'rhr']
const PROVENANCES = [
  ['tested', 'tested (a field test)'],
  ['observed', 'observed (a strap reading)'],
  ['device_estimated', 'device-estimated (auto-detect; shown as retest)'],
  ['stated', 'stated (no artefact)'],
]

function bandLabels(edges) {
  if (!edges) return null
  return edges.map((lo, i) => (i + 1 < edges.length ? `${lo}–${edges[i + 1] - 1}` : `${lo}+`))
}

function pctLabels(pct) {
  return pct.map((p, i) => (i === 0 && p === 0 ? `<${pct[1]}` : i + 1 < pct.length ? `${p}–${pct[i + 1] - 1}` : `${p}+`))
}

function BandRow({ label, cells, muted }) {
  return (
    <div className={`grid grid-cols-6 gap-1 text-[11px] ${muted ? 'text-gray-400' : 'text-gray-700'}`}>
      <span className="font-medium truncate">{label}</span>
      {cells.map((c, i) => <span key={i} className="text-center tabular-nums">{c}</span>)}
    </div>
  )
}

function ClassBlock({ cls }) {
  const bpm = bandLabels(cls.edges_bpm)
  return (
    <div className="rounded-xl bg-gray-50 p-3 space-y-1.5" data-testid={`zone-class-${cls.key}`}>
      <p className="text-xs font-semibold text-gray-900 capitalize">
        {cls.label} <span className="font-normal text-gray-500">· {cls.basis_label}</span>
      </p>
      {cls.sports.length > 0 && (
        <p className="text-[11px] text-gray-400">{cls.sports.join(' · ')}</p>
      )}
      {cls.sports.length === 0 && <p className="text-[11px] text-gray-400">every sport not in the cycling class</p>}
      <BandRow label="" cells={['Z1', 'Z2', 'Z3', 'Z4', 'Z5']} muted />
      <BandRow label="%" cells={pctLabels(cls.band_pct)} />
      {bpm ? (
        <BandRow label="bpm" cells={bpm} />
      ) : (
        <p className="text-[11px] text-amber-600 font-medium" data-testid={`zone-class-${cls.key}-missing`}>
          No bpm bands: missing anchor {cls.missing.join(', ')}
        </p>
      )}
    </div>
  )
}

function AnchorLine({ a }) {
  const f = a.in_force
  return (
    <li className="flex items-start gap-2 text-xs" data-testid={`anchor-${a.kind}`} data-retest={a.retest ? 'true' : 'false'}>
      <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${f ? (a.retest ? 'bg-amber-500' : 'bg-green-500') : 'bg-gray-300'}`} />
      <div className="flex-1 min-w-0">
        <p className="text-gray-800">
          <span className="font-medium">{a.label}</span>{' '}
          {f ? `${f.bpm} bpm · ${f.provenance} · from ${f.effective_from}` : 'none in force'}
          {f?.restates_id ? ' · restated' : ''}
          {a.retest ? <span className="ml-1 text-amber-600 font-medium">retest</span> : null}
        </p>
        {f?.note && <p className="text-[11px] text-gray-400 truncate">{f.note}</p>}
        {!a.writable && (
          <p className="text-[11px] text-gray-400">Written by the operator script ({a.writer}); read-only here.</p>
        )}
      </div>
    </li>
  )
}

function AnchorForm({ cfg, onDone, showToast }) {
  const [kind, setKind] = useState('lthr')
  const [bpm, setBpm] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [provenance, setProvenance] = useState('observed')
  const [note, setNote] = useState('')
  const [change, setChange] = useState('')       // the forced choice: nothing until the operator picks
  const [rationale, setRationale] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // R8 (pending the operator's OK): a kind with no entry yet defaults to the earliest session date; editable.
  useEffect(() => {
    const a = cfg.anchors[kind]
    setEffectiveFrom(a?.in_force ? '' : (cfg.default_effective_from || ''))
    setPreview(null)
    setError('')
  }, [kind, cfg])

  const body = () => ({
    kind, bpm: Number(bpm), effective_from: effectiveFrom, provenance, note: note.trim(), change,
    rationale: rationale.trim() || null,
  })
  const ready = kind && bpm && effectiveFrom && note.trim() && change && (change !== 'restate' || rationale.trim())

  async function doPreview() {
    setBusy(true); setError('')
    try {
      const { data } = await api.post('/hr-zones/anchors/preview', body())
      setPreview(data)
    } catch (err) { setPreview(null); setError(err.response?.data?.detail || 'Preview failed') }
    finally { setBusy(false) }
  }

  async function doSave() {
    setBusy(true); setError('')
    try {
      await api.post('/hr-zones/anchors', body())
      showToast(`${kind.toUpperCase()} ${bpm} bpm recorded; re-zoning…`)
      try { await api.post('/load/refresh?force=true') } catch { /* the nightly sweep is the guarantee */ }
      setBpm(''); setNote(''); setRationale(''); setChange(''); setPreview(null)
      await onDone()
    } catch (err) { setError(err.response?.data?.detail || 'Save failed') }
    finally { setBusy(false) }
  }

  const cls = (k) => preview?.classes_after?.find((c) => c.key === k)
  const clsBefore = (k) => preview?.classes_before?.find((c) => c.key === k)
  const input = 'w-full text-xs rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white'

  return (
    <form onSubmit={(e) => e.preventDefault()} className="bg-indigo-50 border border-indigo-100 rounded-xl p-3 space-y-2" data-testid="anchor-form">
      <div className="grid grid-cols-2 gap-2">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={input} data-testid="anchor-kind">
          <option value="lthr">LTHR (cycling class)</option>
          <option value="rhr">Resting HR (other sports)</option>
        </select>
        <input type="number" value={bpm} onChange={(e) => setBpm(e.target.value)} placeholder="bpm" className={input} data-testid="anchor-bpm" />
        <input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} className={input} data-testid="anchor-date" />
        <select value={provenance} onChange={(e) => setProvenance(e.target.value)} className={input} data-testid="anchor-provenance">
          {PROVENANCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      {!cfg.anchors[kind]?.in_force && (
        <p className="text-[11px] text-gray-500" data-testid="r8-note">
          First entry: the date defaults to the earliest session (R8, pending the operator's OK); change it if the value held from a different date.
        </p>
      )}
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Evidence (required): e.g. Garmin auto-detect 2026-10-28" className={input} data-testid="anchor-note" />
      <fieldset className="text-xs text-gray-700 space-y-1" data-testid="anchor-change">
        <legend className="text-[11px] text-gray-500 mb-1">What kind of change is this? (required)</legend>
        <label className="flex items-start gap-2">
          <input type="radio" name="change" value="dated" checked={change === 'dated'} onChange={() => setChange('dated')} />
          <span><span className="font-medium">Dated change</span> — the value genuinely changed with fitness; applies from this date forward only.</span>
        </label>
        <label className="flex items-start gap-2">
          <input type="radio" name="change" value="restate" checked={change === 'restate'} onChange={() => setChange('restate')} />
          <span><span className="font-medium">Restatement</span> — a correction from better evidence; replaces the entry dated this date over its whole span (history reflows).</span>
        </label>
      </fieldset>
      {change === 'restate' && (
        <input value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Rationale (required): why the earlier value was wrong" className={input} data-testid="anchor-rationale" />
      )}
      {error && <p className="text-[11px] text-red-600 font-medium" data-testid="anchor-error">{error}</p>}
      {preview && (
        <div className="rounded-lg bg-white border border-indigo-100 p-2 space-y-1" data-testid="anchor-preview">
          <p className="text-[11px] font-semibold text-gray-700">
            Preview: {preview.rows_changed} session{preview.rows_changed === 1 ? '' : 's'} re-zone
            {preview.restates ? ` · restates the ${preview.restates.bpm} bpm entry (${preview.restates.provenance})` : ''}
          </p>
          {['lthr', 'hrr'].map((k) => {
            const b = bandLabels(clsBefore(k)?.edges_bpm), a = bandLabels(cls(k)?.edges_bpm)
            if (!a && !b) return null
            return (
              <div key={k} className="space-y-0.5">
                <p className="text-[11px] text-gray-500 capitalize">{cls(k)?.label}</p>
                <BandRow label="before" cells={b || ['—', '—', '—', '—', '—']} muted />
                <BandRow label="after" cells={a || ['—', '—', '—', '—', '—']} />
              </div>
            )
          })}
        </div>
      )}
      <div className="flex gap-2 justify-end">
        <button type="button" onClick={doPreview} disabled={busy || !ready} data-testid="anchor-preview-btn"
          className="text-xs text-indigo-700 border border-indigo-200 hover:border-indigo-400 rounded-lg px-3 py-1.5 disabled:opacity-40">
          {busy ? '…' : 'Preview bpm'}
        </button>
        <button type="button" onClick={doSave} disabled={busy || !ready || !preview} data-testid="anchor-save-btn"
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-xs font-medium rounded-lg px-4 py-1.5">
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}

export default function HRZonesCard({ showToast = () => {} }) {
  const [cfg, setCfg] = useState(null)
  const [failed, setFailed] = useState(false)

  async function load() {
    try {
      const { data } = await api.get('/hr-zones/config')
      setCfg(data); setFailed(false)
    } catch { setFailed(true) }
  }
  useEffect(() => { load() }, [])

  if (failed) return <p className="text-xs text-gray-400" data-testid="hr-zones-unavailable">Heart-rate zones could not be read.</p>
  if (!cfg) return <div className="text-center py-6 text-gray-400 text-sm">Loading…</div>

  const snap = cfg.garmin?.snapshot
  return (
    <div className="space-y-3" data-testid="hr-zones-card">
      <div className="space-y-2">
        {cfg.classes.map((c) => <ClassBlock key={c.key} cls={c} />)}
      </div>

      <div className="bg-white border border-gray-200 rounded-2xl p-4 space-y-2">
        <p className="text-sm font-semibold text-gray-900">Anchors</p>
        <ul className="space-y-1.5">
          {KIND_ORDER.map((k) => cfg.anchors[k] && <AnchorLine key={k} a={cfg.anchors[k]} />)}
        </ul>
        {(cfg.hrmax_prompts || []).map((p) => (
          <p key={p.id} data-testid="hrmax-prompt" className="text-[11px] font-medium text-amber-600">
            Restate HRmax? {p.date} {p.sport}: a sample of {p.hr_max} bpm against {p.hrmax_in_force} in force.
          </p>
        ))}
        <p className="text-[11px] text-gray-400">
          Resting HR is the stored, dated anchor the zones use, never the live daily device value. Entries are append-only.
        </p>
      </div>

      <AnchorForm cfg={cfg} onDone={load} showToast={showToast} />

      <div className="bg-white border border-gray-200 rounded-2xl p-4 space-y-1.5" data-testid="garmin-mirror">
        <p className="text-sm font-semibold text-gray-900">Garmin mirror</p>
        <p className="text-[11px] text-gray-400">The same two profiles as Garmin states them; observation only.</p>
        <BandRow label="" cells={['Z1', 'Z2', 'Z3', 'Z4', 'Z5']} muted />
        <BandRow label={`cycling ${cfg.garmin.profile.cycling.basis}`} cells={cfg.garmin.profile.cycling.bands} />
        <BandRow label={`default ${cfg.garmin.profile.default.basis}`} cells={cfg.garmin.profile.default.bands} />
        {snap ? (
          <p className="text-[11px] text-gray-500" data-testid="garmin-snapshot">
            Garmin reports: max {snap.max_hr_bpm ?? '—'} · LTHR {snap.lthr_bpm ?? '—'} · 7-day auto RHR {snap.rhr_7d_auto_bpm ?? '—'}
            {snap.method ? ` · ${snap.method}` : ''} ({(snap.captured_at || '').slice(0, 10)})
          </p>
        ) : (
          <p className="text-[11px] text-gray-400">No Garmin zone configuration captured yet.</p>
        )}
      </div>
    </div>
  )
}
