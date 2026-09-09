// @vitest-environment jsdom
//
// The hub grid — F5 / GATE 4: the static Training tile was REPLACED by the data-backed ExposureTile,
// not duplicated, so exactly one doorway still routes to /training and the grid's tile count is
// unchanged.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Dashboard from './Dashboard'

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  // Every tile's fetch resolves to a benign empty; the routing assertion does not depend on state.
  api.get.mockResolvedValue({ data: {} })
  api.post.mockResolvedValue({ data: {} })
})
afterEach(cleanup)

describe('the Training doorway is data-backed but singular (GATE 4)', () => {
  test('exactly one link routes to /training', async () => {
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Training')).toBeTruthy())
    const toTraining = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/training')
    expect(toTraining).toHaveLength(1)
  })
})
