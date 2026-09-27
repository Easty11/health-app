// @vitest-environment jsdom
//
// Close-out "Estimated need" after a correction adopt (follow-up to #333). With only the
// operator-set window in force (rx 18 alone) the card shows "re-baselining after correction",
// never a number; once the engine writes a row after it, the number returns (#333 fill).

import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import { PrescriptionCard } from './NightlyCloseOut'

afterEach(cleanup)

const base = { block_open: true, prescribed_lights_out: '21:48', wake_anchor: '05:45',
               window_minutes: 477, dither_minutes: 15 }

const show = (cbti) => render(<MemoryRouter><PrescriptionCard cbti={cbti} /></MemoryRouter>)

test('rx 18 alone: re-baselining, no need number', () => {
  const { container } = show({ ...base, centre_minutes: null, centre_cycles_n: 0,
                               centre_rebaselining: true })
  expect(container.textContent).toMatch(/re-baselining after correction/i)
  expect(container.textContent).not.toMatch(/Estimated need ≈/)
  // 7h57 legitimately appears as tonight's TIME IN BED; it must never appear as the need.
  expect(container.textContent).toMatch(/7h57 in bed/)
  expect(container.textContent).not.toMatch(/Estimated need[^·]*\dh\d{2}/)
})

test('rx 18 + one engine row: the number returns', () => {
  const { container } = show({ ...base, window_minutes: 462, centre_minutes: 469.5,
                               centre_cycles_n: 2, centre_rebaselining: false })
  expect(container.textContent).toMatch(/Estimated need ≈/)
  expect(container.textContent).not.toMatch(/re-baselining/i)
})
