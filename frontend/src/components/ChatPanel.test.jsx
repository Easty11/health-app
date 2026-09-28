// @vitest-environment jsdom
//
// Q187: an assistant turn never renders as an empty bubble. Prod, 28 Sep: a "yes" to the coach's
// "Do you confirm?" came back blank and nothing was written. The server now always returns text;
// this pins the client floor for anything that still arrives blank.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import ChatPanel from './ChatPanel'

async function send(text) {
  const box = screen.getByPlaceholderText('Message…')
  fireEvent.change(box, { target: { value: text } })
  await act(async () => { fireEvent.click(screen.getByText('Send')) })
}

describe('ChatPanel reply rendering', () => {
  beforeEach(() => { localStorage.clear(); api.post.mockReset() })
  afterEach(() => cleanup())

  test.each([[''], ['   \n '], [undefined]])('a blank reply (%j) renders a visible notice', async (response) => {
    api.post.mockResolvedValue({ data: { response, actions_taken: [], write_results: [] } })
    render(<ChatPanel />)
    await send('yes')
    await waitFor(() => expect(screen.getByText(/No response came back/)).toBeTruthy())
    expect(screen.getByText(/nothing was saved/)).toBeTruthy()
  })

  test('a normal reply renders as sent', async () => {
    api.post.mockResolvedValue({ data: { response: 'Recording that.\n\n✓ 1 saved', actions_taken: [], write_results: [] } })
    render(<ChatPanel />)
    await send('record it')
    await waitFor(() => expect(screen.getByText(/Recording that\./)).toBeTruthy())
    expect(screen.queryByText(/No response came back/)).toBeNull()
  })
})
