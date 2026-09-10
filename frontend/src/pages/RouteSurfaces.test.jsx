// @vitest-environment jsdom
//
// Increment 4 STEP 0 — the page split. The lab surface (ingestion, stored results, upload
// history) and the training charts used to share one page at /metrics. This GATE holds the
// split: each route renders ONLY its own surface, and the hub carries a distinct doorway to
// each. The failure it guards is a regression that re-merges the two — a chart leaking back
// onto /labs, or the lab uploader back onto /metrics.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Metrics from './Metrics'
import Labs from './Labs'
import Dashboard from './Dashboard'

beforeEach(() => {
  vi.clearAllMocks()
  // Every surface fetches on mount (charts: /series/*, /engine/phase/history; labs:
  // /labs/results, /labs/canonical-map). A benign empty array satisfies all of them —
  // `res.data?.windows || []`, `res.data?.history || []`, and the labs list read alike —
  // and drops every surface into its empty state, which is exactly where its identifying
  // chrome (chart region / upload button) still renders.
  api.get.mockResolvedValue({ data: [] })
  api.post.mockResolvedValue({ data: [] })
})
afterEach(cleanup)

describe('/metrics renders the training charts and NOT the lab surface', () => {
  test('the four chart regions are present', async () => {
    await act(async () => { render(<MemoryRouter><Metrics /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Training load' })).toBeTruthy())
    expect(screen.getByRole('region', { name: 'Fitness, fatigue and form' })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Exercise progression' })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Readiness' })).toBeTruthy()
  })

  test('no lab ingestion or results chrome bleeds through', async () => {
    await act(async () => { render(<MemoryRouter><Metrics /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Training load' })).toBeTruthy())
    expect(screen.queryByText('Attach Lab Report')).toBeNull()
    expect(screen.queryByText(/Attach a lab report/i)).toBeNull()
    expect(screen.queryByText('Upload history')).toBeNull()
  })
})

describe('/labs renders the lab surface and NOT the training charts', () => {
  test('the ingestion affordance is present', async () => {
    await act(async () => { render(<MemoryRouter><Labs /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Attach Lab Report')).toBeTruthy())
  })

  test('no chart region bleeds through', async () => {
    await act(async () => { render(<MemoryRouter><Labs /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Attach Lab Report')).toBeTruthy())
    expect(screen.queryByRole('region', { name: 'Training load' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Fitness, fatigue and form' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Readiness' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Exercise progression' })).toBeNull()
  })
})

describe('the hub carries one distinct doorway to each surface', () => {
  test('"Metrics" routes to /metrics and "Labs" routes to /labs', async () => {
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Labs')).toBeTruthy())

    const toMetrics = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/metrics')
    const toLabs = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/labs')
    expect(toMetrics).toHaveLength(1)
    expect(toLabs).toHaveLength(1)
    // The labels are what the page IS — the #121 served-bundle grep keys on these strings.
    expect(toMetrics[0].textContent).toContain('Metrics')
    expect(toLabs[0].textContent).toContain('Labs')
  })
})
