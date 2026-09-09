// @vitest-environment jsdom
//
// The data-backed Training tile — assertions track F5's acceptance criteria: FOUR visible states,
// the no-profile mapping (404 AND a 200-with-no-target both → empty), an error that is red and NOT
// empty (absence is not emptiness), the copy line on ready, and the doorway to /training.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import ExposureTile from './ExposureTile'
import decompression from '../../fixtures/engineNextDecompression.json'

async function renderTile() {
  await act(async () => { render(<MemoryRouter><ExposureTile /></MemoryRouter>) })
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

describe('the four states (F5)', () => {
  test('loading shows the reading-the-engine line', async () => {
    api.get.mockReturnValue(new Promise(() => {})) // never resolves
    await act(async () => { render(<MemoryRouter><ExposureTile /></MemoryRouter>) })
    expect(screen.getByText('Reading the engine…')).toBeTruthy()
  })

  test('ready renders the copy line and links to /training', async () => {
    api.get.mockResolvedValue({ data: decompression })
    await renderTile()
    await waitFor(() =>
      expect(screen.getByText('Fortify · Anti-lateral-flexion · Decompression, review 5 Oct')).toBeTruthy(),
    )
    expect(screen.getByRole('link').getAttribute('href')).toBe('/training')
  })

  test('404 is a benign empty — no profile, not a fault', async () => {
    api.get.mockRejectedValue({ response: { status: 404 } })
    await renderTile()
    await waitFor(() => expect(screen.getByText('No exposure profile yet')).toBeTruthy())
  })

  test('a 200 with no fortify.target is also empty (the real no-profile response)', async () => {
    api.get.mockResolvedValue({ data: { mode_recommended: 'fortify', fortify: { target: null, target_label: '—' } } })
    await renderTile()
    await waitFor(() => expect(screen.getByText('No exposure profile yet')).toBeTruthy())
  })

  test('500 is an error — red, says fault, and is NOT the empty render', async () => {
    api.get.mockRejectedValue({ response: { status: 500 } })
    await renderTile()
    await waitFor(() =>
      expect(screen.getByText('Could not load — this is a fault, not an empty result')).toBeTruthy(),
    )
    expect(screen.queryByText('No exposure profile yet')).toBeNull()
  })
})

describe('the tile is always a doorway to /training (F2, GATE 4)', () => {
  test('even while loading the link target is /training', async () => {
    api.get.mockReturnValue(new Promise(() => {}))
    await act(async () => { render(<MemoryRouter><ExposureTile /></MemoryRouter>) })
    expect(screen.getByRole('link').getAttribute('href')).toBe('/training')
  })
})
