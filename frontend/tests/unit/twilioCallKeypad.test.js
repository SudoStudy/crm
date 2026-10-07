import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'

const mocks = vi.hoisted(() => ({ active: null }))
vi.mock('@twilio/voice-sdk', () => ({
  Device: class {
    on() {}
    register() {}
    connect() {
      return Promise.resolve(mocks.active)
    }
  },
}))
vi.mock('@/composables/doctypeModal', () => ({
  useDoctypeModal: () => ({ showModal() {} }),
}))
vi.mock('frappe-ui/frappe', () => ({
  useTelemetry: () => ({ capture() {} }),
  useOnboarding: () => ({ updateOnboardingStep() {} }),
}))
vi.mock('frappe-ui', () => ({
  Avatar: { render: () => null },
  call: async () => ({ token: 'test-only' }),
  createResource: () => ({ fetch() {} }),
}))
vi.mock('@/components/CountUpTimer.vue', () => ({
  default: defineComponent({
    setup(_, { slots, expose }) {
      expose({ start() {}, stop() {} })
      return () => slots.default?.()
    },
  }),
}))
import TwilioCallUI from '@/components/Telephony/TwilioCallUI.vue'

describe('Twilio call keypad UI', () => {
  let app, root, ui, listeners
  const button = (label) =>
    [...root.querySelectorAll('button')].find(
      (b) => b.textContent === label || b.getAttribute('aria-label') === label,
    )
  beforeEach(async () => {
    vi.useFakeTimers()
    listeners = {}
    mocks.active = {
      status: () => 'open',
      sendDigits: vi.fn(),
      on: (name, fn) => {
        listeners[name] = fn
      },
    }
    root = document.createElement('div')
    document.body.append(root)
    app = createApp(TwilioCallUI)
    app.config.globalProperties.__ = globalThis.__
    // Match the existing CRM global component name in this isolated test harness.
    app.component(
      // eslint-disable-next-line vue/no-reserved-component-names
      'Button',
      defineComponent({
        props: {
          label: String,
          icon: [String, Object, Function],
          tooltip: String,
        },
        setup(props, { attrs }) {
          return () => h('button', attrs, props.label || props.tooltip)
        },
      }),
    )
    ui = app.mount(root)
    await ui.setup()
    await ui.makeOutgoingCall('+15555550123')
    listeners.accept()
    listeners.messageReceived({ content: { CallStatus: 'in-progress' } })
    await nextTick()
  })
  afterEach(() => {
    app.unmount()
    root.remove()
    vi.useRealTimers()
  })

  async function openKeypad() {
    button('Keypad').click()
    await nextTick()
    await nextTick()
    return root.querySelector('[aria-label="Call keypad"]')
  }

  it('shows connected controls, focuses keypad, and sends click and keyboard digits once', async () => {
    expect(button('Accept')).toBeUndefined()
    const keypad = await openKeypad()
    expect(document.activeElement).toBe(keypad)
    button('1').click()
    keypad.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '#',
        bubbles: true,
        cancelable: true,
      }),
    )
    await vi.advanceTimersByTimeAsync(250)
    await nextTick()
    expect(mocks.active.sendDigits.mock.calls).toEqual([['1'], ['#']])
    expect(keypad.textContent).toContain('1#')
    root.dispatchEvent(
      new KeyboardEvent('keydown', { key: '2', bubbles: true }),
    )
    expect(mocks.active.sendDigits).toHaveBeenCalledTimes(2)
  })

  it('bounds the in-memory display, shows errors, and allows a successful retry', async () => {
    const keypad = await openKeypad()
    mocks.active.sendDigits.mockImplementationOnce(() => {
      throw new Error('fail')
    })
    button('2').click()
    await nextTick()
    expect(keypad.querySelector('[role="alert"]').textContent).toContain(
      'Could not send digit',
    )
    button('3').click()
    await nextTick()
    expect(keypad.querySelector('[role="alert"]')).toBeNull()
    expect(keypad.querySelector('[aria-live]').textContent.trim()).toBe('3')
    for (let i = 0; i < 30; i++) button('1').click()
    await vi.runAllTimersAsync()
    await nextTick()
    expect(keypad.querySelector('[aria-live]').textContent.trim()).toBe(
      '1'.repeat(24),
    )
  })

  it('clears keypad between calls and does not drag when a digit is pressed', async () => {
    await openKeypad()
    const ancestor = vi.fn()
    root.addEventListener('pointerdown', ancestor)
    button('1').dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(ancestor).not.toHaveBeenCalled()
    button('1').click()
    listeners.disconnect()
    await nextTick()
    expect(root.querySelector('[aria-label="Call keypad"]')).toBeNull()
    await ui.makeOutgoingCall('+15555550123')
    listeners.accept()
    listeners.messageReceived({ content: { CallStatus: 'in-progress' } })
    await nextTick()
    expect(root.querySelector('[aria-label="Call keypad"]')).toBeNull()
    await openKeypad()
    expect(root.querySelector('[aria-live]').textContent).toContain(
      'Enter menu option',
    )
  })

  it('does not start the actual popup drag listener from the keypad', async () => {
    await openKeypad()
    const popup = root.querySelector('.fixed')
    const initial = popup.style.cssText
    function pointer(target, type, x, y) {
      const event = new Event(type, { bubbles: true, cancelable: true })
      Object.assign(event, {
        pointerType: 'mouse',
        button: 0,
        clientX: x,
        clientY: y,
      })
      target.dispatchEvent(event)
    }
    pointer(button('1'), 'pointerdown', 10, 10)
    pointer(window, 'pointermove', 100, 100)
    await nextTick()
    expect(popup.style.cssText).toBe(initial)
    pointer(window, 'pointerup', 100, 100)
  })
})
