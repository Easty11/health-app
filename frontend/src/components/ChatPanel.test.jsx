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

// Q194 (ruled option b): the focus persists for the conversation. A pushed review sets it; every later turn
// resends it until a new focus replaces it, the operator dismisses it, or the chat is cleared.
describe('ChatPanel focus persistence (Q194)', () => {
  beforeEach(() => { localStorage.clear(); api.post.mockReset() })
  afterEach(() => cleanup())

  const REPLY = { data: { response: 'ok', actions_taken: [], write_results: [] } }
  const F1 = { kind: 'hevy', id: 'hv1', scope: 'context' }
  const F2 = { kind: 'aerobic', id: '12', scope: 'session' }
  const body = (n) => api.post.mock.calls[n][1]

  async function renderReview(focus = F1, message = 'Context review: Lower, 2026-09-29') {
    api.post.mockResolvedValue(REPLY)
    let utils
    await act(async () => { utils = render(<ChatPanel pendingFeedback={{ message, focus }} />) })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    return utils
  }

  test('a typed follow-up turn carries the same focus_session', async () => {
    await renderReview()
    await send('why was set 3 at RPE 9?')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(body(1)).toEqual({
      message: 'why was set 3 at RPE 9?',
      conversation_history: expect.any(Array),
      focus_session: F1,
    })
    await send('and the one after?')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3))
    expect(body(2).focus_session).toEqual(F1)        // every turn, not just the first follow-up
  })

  test('a new review replaces the focus; a push that names no session leaves it', async () => {
    const { rerender } = await renderReview()
    await act(async () => { rerender(<ChatPanel pendingFeedback={{ message: 'Session review: Elliptical, 2026-09-28', focus: F2 }} />) })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(body(1).focus_session).toEqual(F2)

    await act(async () => { rerender(<ChatPanel pendingFeedback="Discuss this recommendation" />) })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3))
    expect(body(2).focus_session).toEqual(F2)        // no new focus named: the pinned one rides
  })

  test('the chip names the review and dismissing it stops the focus but keeps the conversation', async () => {
    await renderReview()
    expect(screen.getByText(/Reviewing: Context review: Lower, 2026-09-29/)).toBeTruthy()
    await act(async () => { fireEvent.click(screen.getByLabelText('Stop reviewing this session')) })
    expect(screen.queryByText(/Reviewing:/)).toBeNull()
    expect(screen.getAllByText('Context review: Lower, 2026-09-29').length).toBeGreaterThan(0)   // history intact
    await send('a general question')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(body(1)).not.toHaveProperty('focus_session')
  })

  test('New chat clears the history and the focus', async () => {
    await renderReview()
    await act(async () => { fireEvent.click(screen.getByText('New chat')) })
    expect(screen.queryByText(/Reviewing:/)).toBeNull()
    expect(screen.queryByText('Context review: Lower, 2026-09-29')).toBeNull()
    await send('fresh start')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(body(1)).not.toHaveProperty('focus_session')
    expect(body(1).conversation_history).toEqual([])
  })

  test('the focus survives a reload with the history (localStorage), and New chat removes it there too', async () => {
    const first = await renderReview()
    first.unmount()
    await act(async () => { render(<ChatPanel />) })
    await send('after a reload')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(body(1).focus_session).toEqual(F1)

    await act(async () => { fireEvent.click(screen.getByText('New chat')) })
    cleanup()
    await act(async () => { render(<ChatPanel />) })
    await send('after new chat and reload')
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3))
    expect(body(2)).not.toHaveProperty('focus_session')
  })
})
