/* eslint-disable vue/one-component-per-file, vue/require-prop-types, vue/no-reserved-component-names -- lightweight Vue test doubles */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createApp,
  defineComponent,
  h,
  nextTick,
  reactive,
  ref,
  watch,
} from 'vue'
const api = vi.hoisted(() => ({
  call: vi.fn(),
  addScheduled: vi.fn(),
  upload: null,
  storage: new Map(),
  toastSuccess: vi.fn(),
}))
const Button = defineComponent({
  props: ['label', 'disabled', 'loading', 'type'],
  emits: ['click'],
  setup:
    (p, { emit }) =>
    () =>
      h(
        'button',
        {
          type: p.type || 'button',
          disabled: p.disabled || p.loading,
          onClick: () => emit('click'),
        },
        p.label,
      ),
})
vi.mock('@vueuse/core', () => ({
  useStorage: (key, initial) => {
    const value = ref(api.storage.has(key) ? api.storage.get(key) : initial)
    watch(value, (v) => api.storage.set(key, v), { deep: true, flush: 'sync' })
    return value
  },
}))
vi.mock('frappe-ui', () => ({
  call: api.call,
  createResource: () => ({ data: null }),
  toast: { promise: vi.fn(), success: api.toastSuccess },
}))
vi.mock('frappe-ui/frappe', () => ({
  useOnboarding: () => ({ updateOnboardingStep: vi.fn() }),
  useTelemetry: () => ({ capture: vi.fn() }),
}))
vi.mock('@/utils', () => ({ isContentEmpty: (v) => !v || v === '<p></p>' }))
vi.mock('@/stores/users', () => ({
  usersStore: () => ({
    getUser: () => ({ email: 'rep@example.com', time_zone: 'UTC' }),
  }),
}))
vi.mock('@/components/CommentBox.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/EmailWorkspace/EmailWorkspace.vue', () => ({
  default: defineComponent({
    setup(_, { expose }) {
      expose({ addScheduled: api.addScheduled })
      return () => null
    },
  }),
}))
vi.mock('@/components/EmailEditor.vue', () => ({
  default: defineComponent({
    props: [
      'content',
      'submitLabel',
      'submitButtonProps',
      'discardButtonProps',
      'editable',
      'busy',
    ],
    emits: ['update:content', 'update:attachments', 'uploading'],
    setup(p, { emit, expose, slots }) {
      const fields = reactive({
        fromEmail: 'rep@example.com',
        subject: 'Composer subject',
        toEmails: ['customer@example.com'],
        ccEmails: ['cc@example.com'],
        bccEmails: ['bcc@example.com'],
        editor: { commands: { focus: vi.fn() }, getHTML: () => p.content },
      })
      expose(fields)
      api.editor = fields
      api.upload = (v) => emit('uploading', v)
      return () =>
        h('div', [
          h('textarea', {
            value: p.content,
            disabled: !p.editable,
            onInput: (e) => emit('update:content', e.target.value),
          }),
          h(Button, { ...p.submitButtonProps, label: p.submitLabel }),
          h(Button, { ...p.discardButtonProps, label: 'Discard' }),
          slots['secondary-actions']?.(),
        ])
    },
  }),
}))
import CommunicationArea from '@/components/CommunicationArea.vue'
const tick = async () => {
  for (let i = 0; i < 5; i++) {
    await Promise.resolve()
    await nextTick()
  }
}
describe('schedule from the existing customer email composer', () => {
  let app, root
  const button = (label) =>
    [...root.querySelectorAll('button')].find((b) => b.textContent === label)
  async function click(label) {
    expect(button(label), label).toBeTruthy()
    button(label).click()
    await tick()
  }
  async function compose() {
    await click('Reply')
    const textarea = root.querySelector('textarea')
    textarea.value = '<p>Original composer body</p>'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    await tick()
  }
  async function selectTime(value = '2099-10-31T15:00') {
    const input = root.querySelector('input[type=datetime-local]')
    input.value = value
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await tick()
  }
  function mount() {
    app = createApp({
      setup: () => {
        const doc = ref({ name: 'deal-1', email: 'customer@example.com' })
        return () =>
          h(CommunicationArea, {
            ref: (value) => {
              api.composer = value
            },
            modelValue: doc.value,
            doctype: 'CRM Deal',
          })
      },
    })
    app.component('Button', Button)
    app.config.globalProperties.__ = globalThis.__
    app.mount(root)
  }
  beforeEach(() => {
    api.storage.clear()
    api.call.mockReset()
    api.addScheduled.mockReset()
    api.toastSuccess.mockReset()
    api.call.mockResolvedValue({
      name: 'scheduled-1',
      reference_doctype: 'CRM Deal',
      reference_name: 'deal-1',
      status: 'Scheduled',
    })
    root = document.createElement('div')
    document.body.appendChild(root)
    mount()
  })
  afterEach(() => {
    app.unmount()
    root.remove()
  })
  it('opens scheduling from the primary button and submits the composer email with cancellation on by default', async () => {
    await compose()
    await click('Schedule')
    expect(api.call).not.toHaveBeenCalled()
    expect(root.querySelector('input[type=checkbox]').checked).toBe(true)
    await selectTime()
    await click('Schedule email')
    expect(api.call).toHaveBeenCalledTimes(1)
    expect(api.call.mock.calls[0]).toEqual([
      'crm.api.scheduled_email.schedule_email',
      {
        data: {
          reference_doctype: 'CRM Deal',
          reference_name: 'deal-1',
          sender: 'rep@example.com',
          recipients: 'customer@example.com',
          cc: 'cc@example.com',
          bcc: 'bcc@example.com',
          subject: 'Composer subject',
          content: '<p>Original composer body</p>',
          attachments: [],
          stop_on_reply: true,
        },
        send_at: '2099-10-31T15:00:00.000Z',
        timezone: 'UTC',
        request_id: expect.any(String),
      },
    ])
    expect(api.addScheduled).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'scheduled-1' }),
    )
    expect(root.querySelector('textarea').value).toBe('')
  })
  it('supports opting out and retries an uncertain result with the same request ID while preserving the email', async () => {
    api.call.mockRejectedValueOnce(new Error('Connection interrupted'))
    await compose()
    await click('Schedule')
    await selectTime()
    const toggle = root.querySelector('input[type=checkbox]')
    toggle.checked = false
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await click('Schedule email')
    const first = api.call.mock.calls[0][1]
    expect(first.data.stop_on_reply).toBe(false)
    expect(root.querySelector('[role=alert]').textContent).toContain(
      'Connection interrupted',
    )
    expect(root.querySelector('textarea').value).toBe(
      '<p>Original composer body</p>',
    )
    expect(button('Send now').disabled).toBe(true)
    expect(button('Discard').disabled).toBe(true)
    expect(api.composer.openEmailBox()).toBe(false)
    expect(root.querySelector('textarea').disabled).toBe(true)
    await click('Retry scheduling')
    expect(api.call.mock.calls[1][1]).toEqual(first)
  })
  it('recovers the original immutable request after reload', async () => {
    api.call.mockRejectedValueOnce(new Error('Connection interrupted'))
    await compose()
    await click('Schedule')
    await selectTime()
    await click('Schedule email')
    const first = api.call.mock.calls[0][1]
    app.unmount()
    mount()
    await tick()
    expect(api.editor.subject).toBe(first.data.subject)
    expect(api.editor.toEmails.join(', ')).toBe(first.data.recipients)
    expect(api.editor.ccEmails.join(', ')).toBe(first.data.cc)
    expect(root.querySelector('textarea').value).toBe(first.data.content)
    expect(root.querySelector('textarea').disabled).toBe(true)
    expect(button('Send now').disabled).toBe(true)
    await click('Retry scheduling')
    expect(api.call.mock.calls[1][1]).toEqual(first)
  })
  it('unlocks edits after a confirmed server validation failure', async () => {
    api.call.mockRejectedValueOnce(
      Object.assign(new Error('Choose a future time'), {
        exc_type: 'ValidationError',
        status: 417,
      }),
    )
    await compose()
    await click('Schedule')
    await selectTime()
    await click('Schedule email')
    expect(root.querySelector('[role=alert]').textContent).toContain(
      'Choose a future time',
    )
    expect(root.querySelector('textarea').disabled).toBe(false)
    expect(button('Send now').disabled).toBe(false)
    expect(button('Schedule email')).toBeTruthy()
  })
  it('keeps structured server errors locked and reports the existing canceled state on retry', async () => {
    api.call.mockRejectedValueOnce(
      Object.assign(new Error('Server failed after commit'), {
        exc_type: 'ValidationError',
        status: 500,
      }),
    )
    await compose()
    await click('Schedule')
    await selectTime()
    await click('Schedule email')
    expect(button('Send now').disabled).toBe(true)
    expect(api.composer.openEmailBox()).toBe(false)
    api.call.mockResolvedValueOnce({ name: 'scheduled-1', status: 'Canceled' })
    await click('Retry scheduling')
    expect(api.toastSuccess).toHaveBeenCalledWith('Email status: Canceled')
    expect(api.toastSuccess).not.toHaveBeenCalledWith('Email scheduled')
  })
  it('does not submit twice or send now while scheduling is pending', async () => {
    let finish
    api.call.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    await compose()
    await click('Schedule')
    await selectTime()
    await click('Schedule email')
    expect(button('Retry scheduling').disabled).toBe(true)
    expect(button('Send now').disabled).toBe(true)
    await click('Retry scheduling')
    expect(api.call).toHaveBeenCalledTimes(1)
    finish({ name: 'scheduled-1' })
    await tick()
  })
  it('blocks primary and shortcut scheduling while an attachment is uploading', async () => {
    await compose()
    api.upload(true)
    await tick()
    expect(button('Schedule').disabled).toBe(true)
    expect(button('Send now').disabled).toBe(true)
    root.querySelector('textarea').dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        ctrlKey: true,
        bubbles: true,
      }),
    )
    await tick()
    expect(root.querySelector('input[type=datetime-local]')).toBeNull()
    api.upload(false)
    await tick()
    root.querySelector('textarea').dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        ctrlKey: true,
        bubbles: true,
      }),
    )
    await tick()
    expect(root.querySelector('input[type=datetime-local]')).toBeTruthy()
    expect(api.call).not.toHaveBeenCalled()
  })
  it('retains native Send now and keeps a failed send editable', async () => {
    api.call.mockRejectedValueOnce(new Error('Send rejected'))
    await compose()
    await click('Send now')
    expect(api.call).toHaveBeenCalledWith(
      'frappe.core.doctype.communication.email.make',
      expect.objectContaining({ send_email: 1 }),
    )
    expect(root.querySelector('textarea').disabled).toBe(false)
    expect(root.querySelector('textarea').value).toBe(
      '<p>Original composer body</p>',
    )
  })
})
