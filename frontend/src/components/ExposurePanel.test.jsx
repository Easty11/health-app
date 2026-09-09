// @vitest-environment jsdom
//
// The exposure panel — assertions track F5's acceptance criteria: the decompression payload renders
// mode Fortify, the phase card, NO probe card, the suppressed-probe line, vehicles in received
// order and the notes verbatim; the held payload renders the probe card, no suppressed line, and
// the within-phase warning; Discuss is a single user-initiated push carrying the target label, and
// nothing pushes to chat on mount (#59).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn() } }))

import api from '../api'
import ExposurePanel from './ExposurePanel'
import decompression from '../fixtures/engineNextDecompression.json'
import held from '../fixtures/engineNextHeld.json'

async function renderPanel(payload, onDiscuss = vi.fn()) {
  api.get.mockResolvedValue({ data: payload })
  await act(async () => { render(<ExposurePanel onDiscuss={onDiscuss} />) })
  await waitFor(() => expect(screen.queryByText('Reading the engine…')).toBeNull())
  return onDiscuss
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

describe('decompression payload — fortify, phase, suppressed probe (F5)', () => {
  test('the mode chip reads Fortify', async () => {
    await renderPanel(decompression)
    expect(screen.getByText('Fortify')).toBeTruthy()
  })

  test('the phase card is present', async () => {
    await renderPanel(decompression)
    expect(screen.getByText('Phase · decompression')).toBeTruthy()
  })

  test('there is no probe card', async () => {
    await renderPanel(decompression)
    expect(screen.queryByText(/^Probe ·/)).toBeNull()
  })

  test('the suppressed-probe line names the phase', async () => {
    await renderPanel(decompression)
    expect(screen.getByText("Probe suppressed by training phase 'decompression'.")).toBeTruthy()
  })

  test('vehicles render in received order — no client-side re-sort', async () => {
    await renderPanel(decompression)
    const rendered = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(rendered).toEqual(decompression.fortify.vehicles.map((v) => v.label))
  })

  test('the notes render verbatim', async () => {
    await renderPanel(decompression)
    for (const note of decompression.notes) {
      expect(screen.getByText(note)).toBeTruthy()
    }
  })

  test('nothing pushes to chat on mount', async () => {
    const onDiscuss = await renderPanel(decompression)
    expect(onDiscuss).not.toHaveBeenCalled()
  })
})

describe('held payload — probe present, no suppression, within-phase warning (F5)', () => {
  test('the probe card is present', async () => {
    await renderPanel(held)
    expect(screen.getByText('Probe · Carry')).toBeTruthy()
  })

  test('there is no suppressed-probe line', async () => {
    await renderPanel(held)
    expect(screen.queryByText(/Probe suppressed by/)).toBeNull()
  })

  test('fortify_target_within_phase false surfaces the warning line (#221)', async () => {
    await renderPanel(held)
    expect(
      screen.getByText(/This phase excludes the standing Fortify target's capacity/),
    ).toBeTruthy()
  })
})

describe('Discuss is a single user-initiated push carrying the target (#59)', () => {
  test('clicking Discuss calls onDiscuss once with text containing the target label', async () => {
    const onDiscuss = await renderPanel(decompression)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /discuss in chat/i }))
    })
    expect(onDiscuss).toHaveBeenCalledTimes(1)
    expect(onDiscuss.mock.calls[0][0]).toContain('Anti-lateral-flexion')
  })
})
