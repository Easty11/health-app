// @vitest-environment jsdom
//
// The appointment brief's print document (#350). Gates, on a SYNTHETIC fixture shaped like a real
// follow-up (three injuries, one imaging-like finding, one self-set constraint with a review date,
// nine asks — one with options — and one derived review_due ask):
//   - the print document is print-only and the screen layout is print:hidden;
//   - its text carries no snake_case token and none of the screen-only or boilerplate strings;
//   - no checkbox or tick square reaches paper;
//   - each row once: the finding's text appears once, an ask whose row is in a table points there;
//   - the "If time allows" divider comes after the must-cover asks (after ask 5), and options sit
//     under their ask;
//   - paper always speaks in the clinician voice, whatever `brief.audience` says;
//   - it lays out brief fields verbatim — never a generated sentence (#349).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import Appointment from '../../pages/Appointment'
import BriefPrint from './BriefPrint'
import { fmtAppointment, fmtDay } from './printDates'
import { FINDING_TEXT, PRINT_BRIEF } from './briefPrint.fixture'

async function renderPage(brief = PRINT_BRIEF) {
  api.get.mockImplementation(() => Promise.resolve({ data: brief }))
  await act(async () => {
    render(
      <MemoryRouter initialEntries={['/appointments/appt_x']}>
        <Routes><Route path="/appointments/:key" element={<Appointment />} /></Routes>
      </MemoryRouter>,
    )
  })
  return screen.findByTestId('brief-print')
}

const withSections = (fn) => ({ ...PRINT_BRIEF, sections: fn(PRINT_BRIEF.sections) })
const text = (el) => el.textContent.replace(/\s+/g, ' ')

beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('print target', () => {
  test('the print document is print-only; the screen layout is print:hidden', async () => {
    const doc = await renderPage()
    expect(doc.className).toMatch(/(^|\s)hidden(\s|$)/)
    expect(doc.className).toMatch(/(^|\s)print:block(\s|$)/)
    const screenLayout = screen.getByTestId('appointment-brief')
    expect(screenLayout.className).toMatch(/(^|\s)print:hidden(\s|$)/)
    expect(screenLayout.contains(doc)).toBe(false)
    // Exempt from the screen layout's black-on-white rule: its own class, not inside .brief-print.
    expect(doc.className).toMatch(/(^|\s)brief-doc(\s|$)/)
    expect(doc.closest('.brief-print')).toBeNull()
  })

  test('one fetch: the print document is built from the same brief object', async () => {
    await renderPage()
    expect(api.get).toHaveBeenCalledTimes(1)
  })
})

describe('what never reaches paper', () => {
  test('no snake_case token and no screen-only or boilerplate string', async () => {
    const t = text(await renderPage())
    expect(t).not.toMatch(/\b[A-Za-z0-9]+_[A-Za-z0-9_]+\b/)
    for (const banned of ['linked row not found', 'from ledger', 'engine-enforced', 'Injuries in scope',
      'set by you', 'Status', 'planned', 'Scope is one hop', 'Labs are out of scope']) {
      expect(t).not.toContain(banned)
    }
  })

  test('no checkbox or tick square', async () => {
    const doc = await renderPage()
    expect(within(doc).queryAllByRole('checkbox')).toHaveLength(0)
    expect(doc.querySelectorAll('input, [data-print-tick]')).toHaveLength(0)
    expect(doc.textContent).not.toMatch(/[☐☑☒□■✓✔]/)
  })
})

describe('layout', () => {
  test('title and subtitle; purpose verbatim', async () => {
    const doc = await renderPage()
    expect(within(doc).getByRole('heading', { level: 1 }).textContent).toBe('Appointment brief')
    expect(within(doc).getByText('Person A · Appointment Thu 1 Oct 2026, 13:00 · Clinician A, Practice A')).toBeTruthy()
    const header = PRINT_BRIEF.sections[0]
    expect(within(doc).getByText(header.detail)).toBeTruthy()
  })

  test('the subtitle omits empty parts', async () => {
    const doc = await renderPage({
      ...withSections((ss) => ss.map((s) => (s.module === 'header' ? { ...s, practice: null } : s))),
      patient: { name: null },
    })
    expect(within(doc).getByText('Appointment Thu 1 Oct 2026, 13:00 · Clinician A')).toBeTruthy()
  })

  test('paper speaks in the clinician voice whatever the audience', async () => {
    const doc = await renderPage()
    expect(PRINT_BRIEF.audience).toBe('operator')
    const headings = within(doc).getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Since my last visit (1 Jun 2026)', "Restrictions I'm working under",
      "What I'd like to ask", 'Before we finish'])
  })

  test('since: one table, date ascending, finding area in words, new/before→after, set by', async () => {
    const doc = await renderPage()
    const table = doc.querySelector('table.brief-doc-since')
    expect([...table.querySelectorAll('th')].map((th) => th.textContent)).toEqual(['Date', 'Area', 'What changed', 'Set by'])
    const rows = [...table.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map(text))
    expect(rows).toEqual([
      ['1 Jul 2026', 'part b', 'Part b detail, version one (synthetic) → Part b detail, version two (synthetic)', ''],
      ['10 Jul 2026', 'left part c', 'Recorded', ''],
      ['20 Aug 2026', 'right part a', `${FINDING_TEXT} (new)`, 'My clinician'],
    ])
  })

  test('a replaced finding shows what it replaced', async () => {
    const doc = await renderPage(withSections((ss) => ss.map((s) => (s.module === 'changes_vs_history'
      ? { ...s, findings: [{ ...s.findings[0], previous: [
        { id: 7, statement: 'Earlier statement A (synthetic)', as_of: '2026-03-02', asserted_by: 'clinician' }] }] }
      : s))))
    const cell = within(doc.querySelector('table.brief-doc-since')).getByText(/Imaging report A/)
    expect(text(cell)).toContain('Previously (2 Mar 2026): Earlier statement A (synthetic)')
    expect(text(cell)).not.toContain('(new)')
  })

  test('restrictions: plain restriction, exit in words with review date, set by', async () => {
    const doc = await renderPage()
    const table = doc.querySelector('table.brief-doc-restrictions')
    expect([...table.querySelectorAll('th')].map((th) => th.textContent)).toEqual(['Restriction', 'Ends / review', 'Set by'])
    expect([...table.querySelectorAll('tbody td')].map(text)).toEqual([
      'Synthetic load cap on movement A, no loaded end range',
      'When right part a is resolved — review by 15 Oct 2026',
      'Me',
    ])
  })

  test('logistics as a short list; the footer disclaims interpretation', async () => {
    const doc = await renderPage()
    const list = within(doc).getByRole('heading', { name: 'Before we finish' }).nextElementSibling
    expect([...list.querySelectorAll('li')].map((li) => li.textContent)).toEqual(
      ['Bring imaging report A (synthetic)', 'Ask for a copy of the notes'])
    expect(text(doc.querySelector('.brief-doc-footer'))).toMatch(
      /^Compiled from my own records, printed \d{1,2} [A-Z][a-z]{2} \d{4}\. A record and a list of questions, not a clinical interpretation\.$/)
  })

  test('a block renders only when its module is in the brief', async () => {
    const doc = await renderPage(withSections((ss) => ss.filter((s) => !['current_constraints', 'since',
      'changes_vs_history', 'logistics'].includes(s.module))))
    expect(within(doc).getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual(["What I'd like to ask"])
    expect(doc.querySelector('table')).toBeNull()
    // The derived ask's row is no longer in a table above, so it prints the row itself.
    const last = [...doc.querySelectorAll('ol.brief-doc-asks > li')].at(-1)
    expect(text(last)).toBe('Is this still appropriate?Synthetic load cap on movement A, no loaded end range — set by me')
  })
})

describe('asks', () => {
  const items = (doc) => [...doc.querySelectorAll('ol.brief-doc-asks > li')]

  test('the finding text appears once: the ask resolving it points at the table', async () => {
    const doc = await renderPage()
    expect(doc.textContent.split(FINDING_TEXT).length - 1).toBe(1)
    const ask1 = items(doc)[0]
    expect(ask1.querySelector('strong').textContent).toBe(PRINT_BRIEF.sections[4].authored[0].text)
    expect(text(ask1)).toContain('Note A (synthetic): the report arrived after the last visit.')
    expect(text(ask1)).toContain('(see Since my last visit above)')
  })

  test('nine authored asks then the derived one, numbered in order, verbatim', async () => {
    const doc = await renderPage()
    const lis = items(doc)
    expect(lis).toHaveLength(10)
    PRINT_BRIEF.sections[4].authored.forEach((a, i) => {
      expect(lis[i].querySelector('strong').textContent).toBe(a.text)
    })
    expect(lis[9].querySelector('strong').textContent).toBe('Is this still appropriate?')
    expect(text(lis[9])).toContain("(see Restrictions I'm working under above)")
  })

  test('an ask whose row cannot be shown prints nothing about it', async () => {
    const ask4 = items(await renderPage())[3]
    expect(text(ask4)).toBe(PRINT_BRIEF.sections[4].authored[3].text)
  })

  test('the "If time allows" divider comes after ask 5', async () => {
    const doc = await renderPage()
    const lists = doc.querySelectorAll('ol.brief-doc-asks')
    expect(lists).toHaveLength(2)
    expect(lists[0].children).toHaveLength(5)
    expect(lists[1].getAttribute('start')).toBe('6')
    const divider = doc.querySelector('[data-divider]')
    expect(divider.textContent).toBe('If time allows')
    expect(divider.querySelector('em')).toBeTruthy()
    expect(divider.previousElementSibling).toBe(lists[0])
    expect(divider.nextElementSibling).toBe(lists[1])
  })

  test('no divider when every authored ask is must-cover', async () => {
    const doc = await renderPage(withSections((ss) => ss.map((s) => (s.module === 'leave_with'
      ? { ...s, items: PRINT_BRIEF.sections[4].authored.map((a) => ({ id: a.id, short: 'x', priority: a.priority })) }
      : s))))
    expect(doc.querySelector('[data-divider]')).toBeNull()
    expect(doc.querySelectorAll('ol.brief-doc-asks')).toHaveLength(1)
  })

  test('options sit under their ask as one italic line; options_prep and leave_with print nothing alone', async () => {
    const doc = await renderPage()
    const ask3 = items(doc)[2]
    const line = ask3.querySelector('em')
    expect(line.textContent).toBe(
      "Options I've considered: Yes at full load → placeholder plan X; Yes at reduced load → placeholder plan Y; Not yet → placeholder plan Z")
    expect(doc.querySelectorAll('em.brief-doc-options')).toHaveLength(1)
    expect(text(doc)).not.toContain("What I'd like to leave with today")
    expect(doc.textContent.split(PRINT_BRIEF.sections[4].authored[0].text).length - 1).toBe(1)
  })

  test('a folded derived ask prints its question under the ask', async () => {
    const constraint = PRINT_BRIEF.sections[6].items[0]
    const derived = PRINT_BRIEF.sections[4].derived[0]
    const doc = await renderPage(withSections((ss) => ss.map((s) => (s.module === 'asks' ? {
      ...s, derived: [],
      authored: s.authored.map((a, i) => (i === 1 ? { ...a, folded: [derived],
        resolves: { entry_key: constraint.key, note: null, row: constraint, unresolved: false } } : a)),
    } : s))))
    const ask2 = items(doc)[1]
    expect(text(ask2)).toContain("(see Restrictions I'm working under above)")
    expect(text(ask2)).toContain('Is this still appropriate?')
    expect(items(doc)).toHaveLength(9)
  })
})

describe('date formats', () => {
  test('fixed English, independent of locale', () => {
    expect(fmtAppointment('2026-10-01', '13:00')).toBe('Thu 1 Oct 2026, 13:00')
    expect(fmtDay('2026-07-01T00:00:00')).toBe('1 Jul 2026')
    expect(fmtDay(null)).toBe('')
  })

  test('the footer carries the print date it is given', () => {
    render(<BriefPrint brief={PRINT_BRIEF} printedOn="2026-09-29" />)
    expect(text(screen.getByTestId('brief-print').querySelector('.brief-doc-footer'))).toContain('printed 29 Sep 2026.')
  })
})
