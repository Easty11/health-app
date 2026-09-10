// @vitest-environment jsdom
//
// LabsPanel + LabsPicker (Lab visuals) — the marker picker with the flagged filter, and its
// wiring to the per-marker chart fetch. jsdom, api mocked; the chart's own SVG is covered by
// LabChart.test.jsx, so here we assert the picker list, the flagged filter, and that selecting
// a marker fetches its series.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import LabsPanel from './LabsPanel'
import labIndex from '../../fixtures/labIndex.json'
import labSeries from '../../fixtures/labSeries.json'

function mockApi(index = labIndex) {
  api.get.mockImplementation((url) => {
    if (url === '/series/labs') return Promise.resolve({ data: index })
    if (url.startsWith('/series/lab/')) return Promise.resolve({ data: labSeries })
    return Promise.resolve({ data: {} })
  })
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderPanel() {
  let result
  await act(async () => { result = render(<LabsPanel width={640} height={200} />) })
  await waitFor(() => expect(screen.getByRole('group', { name: 'Marker' })).toBeTruthy())
  return result
}

test('lists markers newest-first and fetches the first marker by default', async () => {
  mockApi()
  await renderPanel()
  const group = screen.getByRole('group', { name: 'Marker' })
  const labels = [...group.querySelectorAll('button')].map((b) => b.textContent.trim())
  expect(labels).toEqual(['testosterone_total', 'crp'])  // endpoint order preserved
  // The first (most-recent) marker is auto-selected and its series fetched.
  expect(api.get).toHaveBeenCalledWith('/series/lab/testosterone_total')
})

test('the flagged filter hides markers with no out-of-range point', async () => {
  mockApi()
  await renderPanel()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /flagged only/i })) })
  const group = screen.getByRole('group', { name: 'Marker' })
  await waitFor(() => {
    const labels = [...group.querySelectorAll('button')].map((b) => b.textContent.trim())
    expect(labels).toEqual(['testosterone_total'])  // crp (any_flagged:false) is filtered out
  })
})

test('selecting a marker fetches its series', async () => {
  mockApi()
  await renderPanel()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'crp' })) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/lab/crp'))
})

test('empty index renders an empty state, no picker', async () => {
  mockApi([])
  await act(async () => { render(<LabsPanel />) })
  await waitFor(() => expect(screen.getByText(/no markers yet/i)).toBeTruthy())
  expect(screen.queryByRole('group', { name: 'Marker' })).toBeNull()
})
