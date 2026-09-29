// The appointment brief's PRINT DOCUMENT (#350) — what Print / Save PDF puts on paper.
//
// A dedicated one-to-two page A4 document in the house "Appointment brief" style: title and
// subtitle, a purpose paragraph, data tables, a numbered question list and a disclaimer footer. It
// supersedes #348(4)'s "print the screen layout" for print only; the screen layout is unchanged and
// is `print:hidden`, this is `hidden print:block`.
//
// It is built from the SAME brief object the screen renders (no second fetch, no server PDF) and
// never rewrites, summarises or generates content: it lays out brief fields verbatim (#349 neutral
// framing). Paper always speaks in the clinician voice (the operator's first person), whatever
// `brief.audience` says. Each block renders only if its module is in `brief.sections`.
//
// Never printed: tick boxes, the appointment status, scope keys, authority pills (plain text in a
// "Set by" column instead), the "from ledger" badge, "linked row not found", tier boilerplate
// (`restriction` / `exit_label` / `parent_label` are the plain-words fields), `brief.limits`.
// Styles: `.brief-doc` in index.css — colour, exempt from `.brief-print`'s black-on-white rule.

import { AUTHORITY, HEADINGS } from './headings'
import { fmtAppointment, fmtDay } from './printDates'

const VOICE = 'clinician'
const SINCE_HEADING = 'Since my last visit'
const H = (module) => HEADINGS[module][VOICE]

function todayIso() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// Who set a row, in the first person ("set by me").
const authority = (row) => AUTHORITY[VOICE][row?.asserted_by] ?? row?.authority ?? ''
// The same label as a "Set by" cell: "Me", "My clinician", "The engine".
function setBy(row) {
  const label = authority(row).replace(/^set by\s+/i, '')
  return label ? label[0].toUpperCase() + label.slice(1) : ''
}

const capital = (s) => (s ? String(s)[0].toUpperCase() + String(s).slice(1) : '')

// A row as plain words: a constraint by its restriction (never the tier boilerplate), else its text.
const rowText = (row) => (row?.type === 'constraint' ? row.restriction : row?.text) || ''

function Table({ columns, rows, className = '' }) {
  return (
    <table className={className}>
      <thead>
        <tr>{columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  )
}

// "Since my last visit": one table, date ascending, from changes_vs_history and since.
function sinceRows(bySection) {
  const chv = bySection.changes_vs_history
  const since = bySection.since
  const rows = []
  for (const f of chv?.findings || []) {
    rows.push({
      id: `f:${f.key}`, key: f.key, date: f.as_of, area: f.parent_label, setBy: setBy(f),
      what: (
        <>
          {f.text}
          {(f.previous || []).length === 0
            ? <span className="brief-doc-muted"> (new)</span>
            : f.previous.map((p) => (
              <span key={p.id} className="brief-doc-sub">
                Previously ({fmtDay(p.as_of)}{p.asserted_by && p.asserted_by !== f.asserted_by ? `; ${authority(p)}` : ''}): {p.statement}
              </span>
            ))}
        </>
      ),
    })
  }
  for (const i of chv?.injuries || []) {
    rows.push({ id: `ci:${i.key}`, key: i.key, date: i.on, area: i.text, setBy: '',
      what: <>{i.before} → {i.after}</> })
  }
  for (const i of since?.injuries || []) {
    rows.push({ id: `si:${i.key}`, key: i.key, date: i.on, area: i.text, setBy: '',
      what: <>{capital(i.change)}{i.basis ? ` — ${i.basis}` : ''}</> })
  }
  for (const f of since?.findings || []) {
    rows.push({ id: `sf:${f.key}`, key: f.key, date: f.as_of, area: f.parent_label, setBy: setBy(f),
      what: <>{f.text}</> })
  }
  for (const c of since?.constraints || []) {
    rows.push({ id: `sc:${c.key}:${c.change}`, key: c.key, date: c.on, area: c.parent_label, setBy: setBy(c),
      what: <>{capital(c.change)}: {c.restriction}{c.basis ? ` — ${c.basis}` : ''}</> })
  }
  // Stable sort: rows with the same date keep the order above.
  return rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => String(a.r.date || '').slice(0, 10).localeCompare(String(b.r.date || '').slice(0, 10)) || a.i - b.i)
    .map(({ r }) => r)
}

function exitCell(c) {
  const bits = []
  if (c.exit_label) bits.push(capital(c.exit_label))
  if (c.review_by) bits.push(`review by ${fmtDay(c.review_by)}`)
  return bits.join(' — ')
}

export default function BriefPrint({ brief, printedOn = todayIso() }) {
  const bySection = Object.fromEntries((brief.sections || []).map((s) => [s.module, s]))
  const header = bySection.header
  const patient = brief.patient?.name

  // Which table above already shows a row, by key → that table's heading (for "see … above").
  const sinceTable = (bySection.since || bySection.changes_vs_history) ? sinceRows(bySection) : null
  const shownIn = new Map()
  for (const r of sinceTable || []) shownIn.set(r.key, SINCE_HEADING)
  for (const c of bySection.current_constraints?.items || []) shownIn.set(c.key, H('current_constraints'))

  const subtitle = header ? [
    patient,
    fmtAppointment(header.date, header.time) && `Appointment ${fmtAppointment(header.date, header.time)}`,
    [header.clinician, header.practice].filter(Boolean).join(', '),
  ].filter(Boolean).join(' · ') : ''

  const sinceDate = bySection.since?.since || bySection.changes_vs_history?.since

  return (
    <article className="brief-doc hidden print:block" data-testid="brief-print">
      <header className="brief-doc-head">
        <h1>Appointment brief</h1>
        {subtitle && <p className="brief-doc-subtitle">{subtitle}</p>}
      </header>

      {header?.detail && <p className="brief-doc-purpose">{header.detail}</p>}

      {sinceTable && sinceTable.length > 0 && (
        <section>
          <h2>{SINCE_HEADING}{sinceDate ? ` (${fmtDay(sinceDate)})` : ''}</h2>
          <Table
            className="brief-doc-since"
            columns={['Date', 'Area', 'What changed', 'Set by']}
            rows={sinceTable.map((r) => (
              <tr key={r.id}>
                <td className="brief-doc-nowrap">{fmtDay(r.date)}</td>
                <td>{r.area}</td>
                <td>{r.what}</td>
                <td>{r.setBy}</td>
              </tr>
            ))}
          />
        </section>
      )}

      {bySection.current_constraints?.items?.length > 0 && (
        <section>
          <h2>{H('current_constraints')}</h2>
          <Table
            className="brief-doc-restrictions"
            columns={['Restriction', 'Ends / review', 'Set by']}
            rows={bySection.current_constraints.items.map((c) => (
              <tr key={c.key}>
                <td>{c.restriction}</td>
                <td>{exitCell(c)}</td>
                <td>{setBy(c)}</td>
              </tr>
            ))}
          />
        </section>
      )}

      {bySection.asks && (
        <AsksBlock
          asks={bySection.asks}
          mustCover={bySection.leave_with ? bySection.leave_with.items.length : null}
          options={bySection.options_prep}
          shownIn={shownIn}
        />
      )}

      {bySection.request && <RequestBlock s={bySection.request} />}
      {bySection.background && <BackgroundBlock s={bySection.background} shownIn={shownIn} />}
      {bySection.imaging_timeline?.items?.length > 0 && <ImagingBlock s={bySection.imaging_timeline} />}

      {bySection.logistics?.items?.length > 0 && (
        <section>
          <h2>{H('logistics')}</h2>
          <ul className="brief-doc-list">
            {bySection.logistics.items.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        </section>
      )}

      <footer className="brief-doc-footer">
        Compiled from my own records, printed {fmtDay(printedOn)}. A record and a list of questions, not a
        clinical interpretation.
      </footer>
    </article>
  )
}

// Under an ask: where its row is — "(see <heading> above)" if a table shows it, else the row itself.
function RowRef({ row, shownIn }) {
  if (!row) return null
  const where = shownIn.get(row.key)
  if (where) return <span className="brief-doc-muted brief-doc-sub">(see {where} above)</span>
  const who = authority(row)
  return <span className="brief-doc-muted brief-doc-sub">{rowText(row)}{who ? ` — ${who}` : ''}</span>
}

function AsksBlock({ asks, mustCover, options, shownIn }) {
  const optionsFor = new Map((options?.items || []).map((o) => [o.ask_id, o.options]))
  const items = [
    ...asks.authored.map((a) => (
      <li key={a.id}>
        <strong>{a.text}</strong>
        {a.resolves.note && <span className="brief-doc-sub">{a.resolves.note}</span>}
        <RowRef row={a.resolves.row} shownIn={shownIn} />
        {a.folded.map((d) => (
          <span key={`${d.rule}:${d.entry_key}`} className="brief-doc-sub">{d.question}</span>
        ))}
        {optionsFor.has(a.id) && (
          <em className="brief-doc-sub brief-doc-options">
            {H('options_prep')}: {optionsFor.get(a.id).map((o) => `${o.option} → ${o.implication}`).join('; ')}
          </em>
        )}
      </li>
    )),
    ...asks.derived.map((d) => (
      <li key={`${d.rule}:${d.entry_key}`}>
        <strong>{d.question}</strong>
        <RowRef row={d.row} shownIn={shownIn} />
      </li>
    )),
  ]
  if (items.length === 0) return null
  // The first `leave_with` count are must-cover; the rest follow an "If time allows" divider.
  const split = mustCover !== null && asks.authored.length > mustCover ? mustCover : items.length
  return (
    <section>
      <h2>{H('asks')}</h2>
      <ol className="brief-doc-asks">{items.slice(0, split)}</ol>
      {split < items.length && (
        <>
          <p className="brief-doc-divider" data-divider><em>If time allows</em></p>
          <ol className="brief-doc-asks" start={split + 1}>{items.slice(split)}</ol>
        </>
      )}
    </section>
  )
}

function RequestBlock({ s }) {
  return (
    <section>
      <h2>{H('request')}</h2>
      <p><strong>{s.ask}</strong></p>
      <p>{s.justification}</p>
      {s.evidence.length > 0 && (
        <ul className="brief-doc-list">{s.evidence.map((e, i) => <li key={i}>{e.ref}</li>)}</ul>
      )}
      {s.alternatives.length > 0 && <p>Alternatives: {s.alternatives.join('; ')}</p>}
    </section>
  )
}

function BackgroundBlock({ s, shownIn }) {
  // A finding a table above already shows is not repeated (each row once, #348).
  const findings = s.findings.filter((f) => !shownIn.has(f.key))
  if (s.injuries.length === 0 && findings.length === 0) return null
  return (
    <section>
      <h2>{H('background')}</h2>
      {s.injuries.length > 0 && (
        <Table
          columns={['Area', 'Detail']}
          rows={s.injuries.map((i) => (
            <tr key={i.key}>
              <td>{i.text}{i.resolved_on ? ` (resolved ${fmtDay(i.resolved_on)})` : ''}</td>
              <td>{i.detail}</td>
            </tr>
          ))}
        />
      )}
      {findings.length > 0 && (
        <Table
          columns={['Date', 'Area', 'Finding', 'Set by']}
          rows={findings.map((f) => (
            <tr key={f.key}>
              <td className="brief-doc-nowrap">{fmtDay(f.as_of)}</td>
              <td>{f.parent_label}</td>
              <td>{f.text}</td>
              <td>{setBy(f)}</td>
            </tr>
          ))}
        />
      )}
    </section>
  )
}

function ImagingBlock({ s }) {
  return (
    <section>
      <h2>{H('imaging_timeline')}</h2>
      <Table
        columns={['Document', 'Cited']}
        rows={s.items.map((d, i) => (
          <tr key={i}>
            <td>{d.ref}</td>
            <td className="brief-doc-nowrap">{fmtDay(d.as_of)}</td>
          </tr>
        ))}
      />
    </section>
  )
}
