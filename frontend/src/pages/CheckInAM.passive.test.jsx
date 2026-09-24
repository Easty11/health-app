// @vitest-environment jsdom
//
// Check-in HRV tile (HRV staleness brief, G2 frontend half). The prefill carries CURRENT
// wake-day HRV only; with no reading for today (absent / stale_withheld) the tile renders
// "–", never an earlier night's number. A same-night pair shows both devices.

import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import { PassiveCard } from './CheckInAM'

afterEach(cleanup)

test('stale_withheld renders a dash, no number', () => {
  const { container } = render(<PassiveCard hrv={null} hrvState="stale_withheld" sleepMin={null} />)
  expect(screen.getByText('–')).toBeTruthy()
  expect(container.textContent).not.toMatch(/\d+\s*ms/)
  expect(container.textContent).not.toMatch(/Ring/)
})

test('absent renders a dash', () => {
  render(<PassiveCard hrv={null} hrvState="absent" sleepMin={420} />)
  expect(screen.getByText('–')).toBeTruthy()
})

test('value renders the number with its source and baseline delta', () => {
  const { container } = render(
    <PassiveCard hrv={62} hrvVsBaseline={3.5} hrvState="value" hrvSource="garmin" sleepMin={null} />,
  )
  expect(container.textContent).toMatch(/HRV · garmin/)
  expect(container.textContent).toMatch(/62/)
  expect(container.textContent).toMatch(/\+3\.5 vs baseline/)
})

test('pair surfaces both sources, garmin primary', () => {
  const { container } = render(
    <PassiveCard hrv={62} hrvState="pair" hrvSource="garmin"
      hrvSecondaryMs={70} hrvSecondarySource="samsung" sleepMin={null} />,
  )
  expect(container.textContent).toMatch(/HRV · garmin/)
  expect(container.textContent).toMatch(/samsung: 70 ms/)
})
