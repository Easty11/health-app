// @vitest-environment jsdom
//
// The #214 confirm gate, tested where the defect actually lived: THE WIRING.
//
// This is the repo's first component test, and the reason it is worth the jsdom
// dependency is that a pure-function test cannot express the property under protection.
// The copy helpers are already unit-tested in `evaluationCopy.test.js`; the #214 defect
// was not wrong copy or a wrong predicate but a button bound straight to the POST. Only a
// render-and-click test can fail when someone rebinds it, and the write it guards is an
// append to an append-only ledger — the one class of bug this codebase cannot walk back.
//
// The assertions are therefore all about the NETWORK, not the DOM: what was posted, and
// after which interaction. Text is matched only where it is the control being pressed.
//
// The environment is declared in the docblock above rather than in `vite.config.js`, so
// the other suites keep running in node and pay nothing for this one.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import api from '../../api'
import EvaluationOffer from './EvaluationOffer'

// An eligible, ACCEPTABLE offer: the engine reached a decision on merits.
const EXTEND = {
  block_open: true,
  eligible: true,
  reason: '',
  decision: 'extend',
  decision_reason: 'extended 390->405min (mean TST 420 + 30 buffer, move capped at 15)',
  sufficient: true,
  days_since_effective_from: 4,
  nights_since_effective_from: 4,
  basis: {
    cycle_from: '2026-08-13', cycle_to: '2026-08-16',
    tst_min: 420, se_pct: 90,
    window_minutes_current: 390, window_minutes_proposed: 405,
    lights_out_current: '22:30', lights_out_proposed: '22:15',
    wake_anchor: '05:00',
    nights_counted: 4, n_diary: 4, n_samsung: 0, n_alcohol_unknown: 0,
    nights_excluded: {}, ema_count: 0, move_capped: true, tib_over_run_min: null,
  },
}

// An eligible offer the engine could NOT adjudicate — the class the server refuses.
const INSUFFICIENT = {
  ...EXTEND,
  decision: 'hold',
  decision_reason: 'insufficient_nights: 2 valid of 4, need 3 (2 excluded: nap x2)',
  sufficient: false,
  nights_since_effective_from: 2,
  basis: {
    ...EXTEND.basis,
    nights_counted: 2,
    nights_excluded: { '2026-08-14': 'nap', '2026-08-15': 'nap' },
  },
}

async function renderOffer(data) {
  api.get.mockResolvedValue({ data })
  await act(async () => { render(<EvaluationOffer />) })
  // the fetch has resolved and the card is on screen before any assertion runs
  await waitFor(() => expect(api.get).toHaveBeenCalled())
}

async function click(name) {
  await act(async () => { screen.getByRole('button', { name }).click() })
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
})
afterEach(cleanup)


describe('an acceptable offer takes two deliberate acts (#214)', () => {
  test('the offer card carries no live accept control', async () => {
    await renderOffer(EXTEND)
    // The old label is gone: its presence WAS the defect, so this is the regression pin.
    expect(screen.queryByRole('button', { name: /accept and prescribe/i })).toBeNull()
    expect(screen.getByRole('button', { name: /review and accept/i })).toBeTruthy()
  })

  test('the first tap fires no request', async () => {
    await renderOffer(EXTEND)
    await click(/review and accept/i)
    expect(api.post).not.toHaveBeenCalled()
  })

  test('the confirmation restates the actual write, clock reset included', async () => {
    await renderOffer(EXTEND)
    await click(/review and accept/i)

    // The decision, RESTATED — matched on the confirmation's own sentence, because the
    // headline above still carries the same phrase and a bare text query would pass on
    // the headline alone even if the confirmation had dropped it.
    expect(screen.getByText(/Record this prescription\? Extend the window by \+15 min/)).toBeTruthy()
    expect(screen.getAllByText(/Extend the window by \+15 min/)).toHaveLength(2)
    // both moves the row will record
    expect(screen.getByText(/Window 6h 30m → 6h 45m/)).toBeTruthy()
    expect(screen.getByText(/Lights out 22:30 → 22:15/)).toBeTruthy()
    // and the consequence that is not visible anywhere in the decision itself
    expect(screen.getByText(/resets the evaluation clock/i)).toBeTruthy()
  })

  test('the POST happens only on the second, explicit control', async () => {
    await renderOffer(EXTEND)
    await click(/review and accept/i)
    expect(api.post).not.toHaveBeenCalled()

    api.post.mockResolvedValue({ data: { ...EXTEND, reason: 'accepted', eligible: false } })
    await click(/confirm — record prescription/i)

    expect(api.post).toHaveBeenCalledTimes(1)
    // an empty body: the server re-evaluates and mints from its own result (#118)
    expect(api.post).toHaveBeenCalledWith('/checkin-v2/cbti/evaluation/accept')
  })

  test('cancel fires nothing and returns to the offer', async () => {
    await renderOffer(EXTEND)
    await click(/review and accept/i)
    await click(/cancel/i)

    expect(api.post).not.toHaveBeenCalled()
    // back to step 1 — not stranded, and still not a live accept
    expect(screen.getByRole('button', { name: /review and accept/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /confirm — record prescription/i })).toBeNull()
  })

  test('the accepted state card still renders after a confirmed accept', async () => {
    await renderOffer(EXTEND)
    await click(/review and accept/i)
    api.post.mockResolvedValue({ data: { ...EXTEND, reason: 'accepted', eligible: false } })
    await click(/confirm — record prescription/i)

    expect(screen.getByText(/Evaluation recorded/i)).toBeTruthy()
  })
})


describe('an insufficiency offer is information-only (Q101)', () => {
  test('no accept control of any kind, in any state', async () => {
    await renderOffer(INSUFFICIENT)

    // Not a disabled button and not a hidden one — no control at all. `queryAllByRole`
    // rather than three separate name queries: the claim is about the whole card, so a
    // control added later under any label fails this too.
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(api.post).not.toHaveBeenCalled()
  })

  test('it shows the engine reason and the nights tally instead', async () => {
    await renderOffer(INSUFFICIENT)

    expect(screen.getByText(/Not enough logged nights to evaluate/i)).toBeTruthy()
    expect(screen.getByText(/insufficient_nights: 2 valid of 4, need 3/)).toBeTruthy()
    expect(screen.getByText(/Nights counted/i)).toBeTruthy()
    // the exclusions panel is preserved on this card too — exclusions are the likeliest
    // cause of the shortfall, so they are what make an insufficiency finding diagnosable
    expect(screen.getByText(/2 nights excluded from the basis/i)).toBeTruthy()
    expect(screen.getByText(/2026-08-14 — nap/)).toBeTruthy()
  })

  test('a server that omits the flag keeps the two-step accept, not read-only', async () => {
    // Read strictly: only an explicit `false` suppresses the control. A missing field
    // must not silently turn every offer into a dead card during a rolling deploy.
    const { sufficient, ...withoutFlag } = EXTEND
    void sufficient
    await renderOffer(withoutFlag)

    expect(screen.getByRole('button', { name: /review and accept/i })).toBeTruthy()
  })
})
