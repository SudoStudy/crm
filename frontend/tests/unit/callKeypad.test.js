import { describe, it, expect, vi } from 'vitest'
import {
  sendCallDigit,
  keypadDigitFromEvent,
  createCallDigitQueue,
} from '@/utils/callKeypad'

describe('call keypad', () => {
  const activeCall = () => ({ status: () => 'open', sendDigits: vi.fn() })

  it.each('0123456789*#'.split(''))(
    'sends %s once on the active call',
    (digit) => {
      const call = activeCall()
      expect(sendCallDigit(call, true, digit)).toBe(true)
      expect(call.sendDigits).toHaveBeenCalledExactlyOnceWith(digit)
    },
  )

  it.each(['pending', 'connecting', 'ringing', 'closed'])(
    'blocks %s calls',
    (status) => {
      const call = activeCall()
      call.status = () => status
      expect(sendCallDigit(call, true, '1')).toBe(false)
      expect(call.sendDigits).not.toHaveBeenCalled()
    },
  )

  it('blocks missing and disconnected calls', () => {
    const call = activeCall()
    expect(sendCallDigit(null, true, '1')).toBe(false)
    expect(sendCallDigit({}, true, '1')).toBe(false)
    expect(sendCallDigit(call, false, '1')).toBe(false)
    expect(call.sendDigits).not.toHaveBeenCalled()
  })

  it.each(['12', 'w', '', 'x', undefined])(
    'rejects invalid digit %s',
    (digit) => {
      const call = activeCall()
      expect(sendCallDigit(call, true, digit)).toBe(false)
      expect(call.sendDigits).not.toHaveBeenCalled()
    },
  )

  it('propagates SDK errors so the UI can show an error without recording input', () => {
    const call = activeCall()
    call.sendDigits.mockImplementation(() => {
      throw new Error('disconnected')
    })
    expect(() => sendCallDigit(call, true, '1')).toThrow('disconnected')
  })

  it('accepts digits and shifted symbols, but ignores shortcuts and held keys', () => {
    expect(keypadDigitFromEvent({ key: '1' })).toBe('1')
    expect(keypadDigitFromEvent({ key: '#', shiftKey: true })).toBe('#')
    for (const modifier of [
      'isComposing',
      'repeat',
      'ctrlKey',
      'metaKey',
      'altKey',
    ]) {
      expect(keypadDigitFromEvent({ key: '1', [modifier]: true })).toBeNull()
    }
    expect(keypadDigitFromEvent({ key: 'Enter' })).toBeNull()
  })
})

describe('per-call digit queue', () => {
  function setup() {
    const call = { status: () => 'open', sendDigits: vi.fn() }
    const onSent = vi.fn(),
      onError = vi.fn()
    const state = { call, connected: true }
    const queue = createCallDigitQueue({
      getCall: () => state.call,
      isConnected: () => state.connected,
      onSent,
      onError,
    })
    return { call, state, queue, onSent, onError }
  }

  it('serializes rapid extension input without replacing pending SDK tones', () => {
    vi.useFakeTimers()
    try {
      const { call, queue, onSent } = setup()
      for (const digit of '123#') queue.send(digit)
      expect(call.sendDigits.mock.calls).toEqual([['1']])
      vi.advanceTimersByTime(249)
      expect(call.sendDigits).toHaveBeenCalledTimes(1)
      vi.runAllTimers()
      expect(call.sendDigits.mock.calls).toEqual([['1'], ['2'], ['3'], ['#']])
      expect(onSent).toHaveBeenCalledTimes(4)
      queue.clear()
    } finally {
      vi.useRealTimers()
    }
  })

  it('cancels pending digits on clear and never sends them on a replacement call', () => {
    vi.useFakeTimers()
    try {
      const { call, state, queue, onError } = setup()
      queue.send('1')
      queue.send('2')
      queue.clear()
      vi.runAllTimers()
      expect(call.sendDigits.mock.calls).toEqual([['1']])
      queue.send('3')
      queue.send('4')
      state.call = { status: () => 'open', sendDigits: vi.fn() }
      vi.runAllTimers()
      expect(state.call.sendDigits).not.toHaveBeenCalled()
      expect(onError).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports non-open calls and stops the queue on an SDK error', () => {
    vi.useFakeTimers()
    try {
      const { call, queue, onSent, onError } = setup()
      call.status = () => 'connecting'
      queue.send('1')
      expect(onError).toHaveBeenCalledTimes(1)
      expect(onSent).not.toHaveBeenCalled()
      call.status = () => 'open'
      queue.send('2')
      queue.send('3')
      queue.send('4')
      call.sendDigits.mockImplementation(() => {
        throw new Error('fail')
      })
      vi.runAllTimers()
      expect(onError).toHaveBeenCalledTimes(2)
      expect(call.sendDigits).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
