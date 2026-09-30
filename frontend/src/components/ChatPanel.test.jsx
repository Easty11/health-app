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


// Brief A A1/A3: a session review rides as a REFERENCE. The panel pushes `{ message, focus }`; the request
// carries `focus_session`, and the bubble shows only the short message.
describe('ChatPanel session focus', () => {
  beforeEach(() => { localStorage.clear(); api.post.mockReset() })
  afterEach(() => cleanup())

  const REPLY = { data: { response: 'Reviewing.', actions_taken: [], write_results: [] } }

  test('a pushed review sends focus_session with the short message', async () => {
    api.post.mockResolvedValue(REPLY)
    const focus = { kind: 'hevy', id: 'hv1', scope: 'context' }
    await act(async () => {
      render(<ChatPanel pendingFeedback={{ message: 'Context review: Lower, 2026-09-29', focus }} />)
    })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post).toHaveBeenCalledWith('/chat', {
      message: 'Context review: Lower, 2026-09-29', conversation_history: [], focus_session: focus,
    })
    expect(screen.getAllByText('Context review: Lower, 2026-09-29')).toHaveLength(1)   // the bubble: message only
  })

  test('a bare-string push (the exposure panel) and a typed message carry no focus_session', async () => {
    api.post.mockResolvedValue(REPLY)
    await act(async () => { render(<ChatPanel pendingFeedback="Discuss this recommendation" />) })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post.mock.calls[0][1]).not.toHaveProperty('focus_session')

    await send('and a typed follow-up')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(api.post.mock.calls[1][1]).not.toHaveProperty('focus_session')
  })

  test('an object push with no focus sends none', async () => {
    api.post.mockResolvedValue(REPLY)
    await act(async () => { render(<ChatPanel pendingFeedback={{ message: 'hello', focus: null }} />) })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post.mock.calls[0][1]).not.toHaveProperty('focus_session')
  })
})
