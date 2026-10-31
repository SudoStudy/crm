import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, reactive } from 'vue'
const api = vi.hoisted(() => ({
  call: vi.fn(),
  deferUpload: false,
  finishUpload: null,
}))
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))
vi.mock('frappe-ui', () => ({
  call: api.call,
  Button: defineComponent({
    props: {
      label: String,
      disabled: Boolean,
      loading: Boolean,
      type: { type: String, default: 'button' },
    },
    emits: ['click'],
    setup(props, { emit }) {
      return () =>
        h(
          'button',
          {
            type: props.type,
            disabled: props.disabled || props.loading,
            onClick: () => emit('click'),
          },
          props.label,
        )
    },
  }),
  Badge: defineComponent({
    props: ['label'],
    setup: (p) => () => h('span', p.label),
  }),
  FileUploader: defineComponent({
    props: ['validateFile'],
    emits: ['success', 'failure'],
    setup(props, { slots, emit }) {
      return () =>
        slots.default({
          openFileSelector: async () => {
            const error = await props.validateFile?.({ name: 'upload.pdf' })
            if (error) return
            const finish = () => emit('success', { name: 'uploaded-file' })
            if (api.deferUpload) api.finishUpload = finish
            else finish()
          },
        })
    },
  }),
}))
vi.mock('@/components/RichTextField.vue', () => ({
  default: defineComponent({
    props: ['content'],
    emits: ['change'],
    setup:
      (p, { emit }) =>
      () =>
        h('textarea', {
          value: p.content,
          'aria-label': 'Message',
          onInput: (e) => emit('change', e.target.value),
        }),
  }),
}))
import EmailWorkspace from '@/components/EmailWorkspace/EmailWorkspace.vue'

const tick = async () => {
  for (let i = 0; i < 5; i++) {
    await Promise.resolve()
    await nextTick()
  }
}
const baseDraft = {
  name: 'draft-1',
  modified: 'v1',
  reference_doctype: 'CRM Deal',
  reference_name: 'deal-1',
  status: 'Draft',
  sender: 'rep@example.com',
  recipients: 'customer@example.com',
  cc: 'cc@example.com',
  bcc: 'bcc@example.com',
  subject: 'Saved subject',
  content: '<p>Saved message</p>',
  attachments: ['file-1'],
  stop_on_reply: true,
}
const data = (drafts = []) => ({
  drafts,
  sequences: [],
  senders: [{ email: 'rep@example.com', label: 'Rep' }],
  timezone: 'Europe/London',
})

describe('customer email workspace', () => {
  let app, root, state
  function mount() {
    root = document.createElement('div')
    document.body.appendChild(root)
    state = reactive({
      referenceDoctype: 'CRM Deal',
      referenceName: 'deal-1',
      defaultRecipient: 'customer@example.com',
    })
    app = createApp({ render: () => h(EmailWorkspace, state) })
    app.config.globalProperties.__ = globalThis.__
    app.mount(root)
  }
  function button(label) {
    return [...root.querySelectorAll('button')].find(
      (b) => b.textContent === label,
    )
  }
  async function click(label) {
    const item = button(label)
    expect(item, label).toBeTruthy()
    item.click()
    await tick()
  }
  function field(label) {
    const el = [...root.querySelectorAll('label')].find(
      (el) => el.firstChild?.textContent.trim() === label,
    )
    expect(el, label).toBeTruthy()
    return el.querySelector('input,select')
  }
  async function fill(input, value) {
    input.value = value
    input.dispatchEvent(
      new Event(input.tagName === 'SELECT' ? 'change' : 'input', {
        bubbles: true,
      }),
    )
    await tick()
  }
  beforeEach(() => {
    api.call.mockReset()
    api.deferUpload = false
    api.finishUpload = null
    window.confirm = vi.fn(() => true)
  })
  afterEach(() => {
    app?.unmount()
    root?.remove()
    vi.restoreAllMocks()
  })

  it('loads only on open and restores complete server-saved draft fields', async () => {
    api.call.mockResolvedValue(data([baseDraft]))
    mount()
    expect(api.call).not.toHaveBeenCalled()
    await click('Drafts & scheduled emails')
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.get_workspace',
      { reference_doctype: 'CRM Deal', reference_name: 'deal-1' },
    )
    await click('Edit email')
    expect(field('To').value).toBe('customer@example.com')
    expect(field('CC').value).toBe('cc@example.com')
    expect(field('BCC').value).toBe('bcc@example.com')
    expect(field('Subject').value).toBe('Saved subject')
    expect(root.querySelector('textarea').value).toBe('<p>Saved message</p>')
    expect(root.textContent).toContain('file-1')
  })

  it('saves complete edits and attachments using the optimistic revision', async () => {
    api.call.mockImplementation(async (method, params) =>
      method.endsWith('save_draft')
        ? { ...params.data, modified: 'v2' }
        : data([baseDraft]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Subject'), 'Revised subject')
    await fill(field('BCC'), 'private@example.com')
    await click('Attach a file')
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.save_draft',
      {
        data: expect.objectContaining({
          name: 'draft-1',
          modified: 'v1',
          sender: 'rep@example.com',
          recipients: 'customer@example.com',
          cc: 'cc@example.com',
          bcc: 'private@example.com',
          subject: 'Revised subject',
          content: '<p>Saved message</p>',
          attachments: ['file-1', 'uploaded-file'],
        }),
      },
    )
    expect(root.textContent).toContain('Draft saved.')
  })

  it('preserves local changes after an optimistic conflict', async () => {
    api.call.mockImplementation(async (method) => {
      if (method.endsWith('save_draft'))
        throw { messages: ['This email changed in another tab.'] }
      return data([baseDraft])
    })
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Subject'), 'Unsaved revision')
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(root.textContent).toContain('This email changed in another tab.')
    expect(field('Subject').value).toBe('Unsaved revision')
  })

  it('rejects an ambiguous DST time before saving or scheduling', async () => {
    api.call.mockResolvedValue(data([baseDraft]))
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Send at'), '2030-10-27T01:30')
    await click('Schedule email')
    expect(root.textContent).toContain('occurs twice')
    expect(api.call).toHaveBeenCalledTimes(1)
  })

  it('saves then schedules with UTC timestamp and the returned revision', async () => {
    api.call.mockImplementation(async (method, params) =>
      method.endsWith('save_draft')
        ? { ...params.data, modified: 'v2' }
        : method.endsWith('schedule_draft')
          ? { ...baseDraft, status: 'Scheduled', modified: 'v3' }
          : data([baseDraft]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Send at'), '2030-07-15T09:00')
    await click('Schedule email')
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.schedule_draft',
      {
        name: 'draft-1',
        modified: 'v2',
        send_at: '2030-07-15T08:00:00.000Z',
        timezone: 'Europe/London',
      },
    )
    expect(root.textContent).toContain('Email scheduled.')
  })

  it('never offers edit, delete or retry for an ambiguous delivery error', async () => {
    api.call.mockResolvedValue(
      data([
        {
          ...baseDraft,
          status: 'Error',
          last_error: 'Delivery outcome unknown.',
        },
      ]),
    )
    mount()
    await click('Drafts & scheduled emails')
    expect(button('Edit email')).toBeUndefined()
    expect(button('Delete draft')).toBeUndefined()
    expect(root.textContent).toContain('will not retry automatically')
  })

  it('saves an incomplete draft without requiring a connected mailbox or recipient', async () => {
    api.call.mockImplementation(async (method, params) =>
      method.endsWith('save_draft')
        ? { ...params.data, name: 'incomplete', modified: 'v1' }
        : { ...data(), senders: [] },
    )
    mount()
    state.defaultRecipient = ''
    await click('Drafts & scheduled emails')
    await click('New saved draft')
    expect(root.querySelector('select').required).toBe(false)
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.save_draft',
      {
        data: expect.objectContaining({
          sender: '',
          recipients: '',
          subject: '',
          content: '',
        }),
      },
    )
    expect(button('Send now').disabled).toBe(true)
  })

  it('saves then queues an exact draft to send now only after confirmation', async () => {
    api.call.mockImplementation(async (method, params) =>
      method.endsWith('save_draft')
        ? { ...params.data, modified: 'v2' }
        : method.endsWith('send_draft_now')
          ? { ...baseDraft, status: 'Scheduled' }
          : data([baseDraft]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await click('Send now')
    expect(window.confirm).toHaveBeenCalledWith(
      'Send this email now to customer@example.com?',
    )
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.send_draft_now',
      { name: 'draft-1', modified: 'v2' },
    )
    expect(root.textContent).toContain('Email queued to send now')
  })

  it('cancels remaining enrollment steps and reports an in-flight email', async () => {
    api.call.mockImplementation(async (method) =>
      method.endsWith('cancel_enrollment')
        ? { canceled_count: 2, already_sending: true }
        : data([
            {
              ...baseDraft,
              status: 'Scheduled',
              enrollment_id: 'enrollment-1',
            },
          ]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Cancel remaining sequence')
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.cancel_enrollment',
      { enrollment_id: 'enrollment-1' },
    )
    expect(root.textContent).toContain('already sending cannot be recalled')
  })

  it('previews sequence dates in its chosen timezone then enrolls the customer', async () => {
    const sequence = {
      name: 'sequence-1',
      modified: 'seq-v1',
      title: 'Proposal follow-up',
      steps: [
        { day_offset: 0, subject: 'First', content: '<p>First</p>' },
        { day_offset: 3, subject: 'Second', content: '<p>Second</p>' },
      ],
    }
    api.call.mockImplementation(async (method) =>
      method.endsWith('enroll_sequence')
        ? { drafts: [] }
        : { ...data(), sequences: [sequence] },
    )
    mount()
    await click('Drafts & scheduled emails')
    await fill(field('Sequence'), 'sequence-1')
    await fill(field('Send at'), '2030-10-25T09:00')
    expect(root.textContent).toContain('2030-10-25 09:00 Europe/London')
    expect(root.textContent).toContain('2030-10-28 09:00 Europe/London')
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.enroll_sequence',
      {
        reference_doctype: 'CRM Deal',
        reference_name: 'deal-1',
        sequence_name: 'sequence-1',
        start_at: '2030-10-25T08:00:00.000Z',
        timezone: 'Europe/London',
        sender: 'rep@example.com',
        recipients: 'customer@example.com',
      },
    )
  })

  it('enrolls using the chosen start before applying a nonzero first step offset', async () => {
    const sequence = {
      name: 'sequence-1',
      modified: 'seq-v1',
      title: 'Delayed follow-up',
      steps: [
        { day_offset: 3, subject: 'First', content: '<p>First</p>' },
        { day_offset: 7, subject: 'Second', content: '<p>Second</p>' },
      ],
    }
    api.call.mockImplementation(async (method) =>
      method.endsWith('enroll_sequence')
        ? { drafts: [] }
        : { ...data(), sequences: [sequence] },
    )
    mount()
    await click('Drafts & scheduled emails')
    await fill(field('Sequence'), 'sequence-1')
    await fill(field('Send at'), '2030-07-15T09:00')
    expect(root.textContent).toContain('2030-07-18 09:00 Europe/London')
    expect(root.textContent).toContain('2030-07-22 09:00 Europe/London')
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.enroll_sequence',
      expect.objectContaining({ start_at: '2030-07-15T08:00:00.000Z' }),
    )
  })

  it('creates a reusable template with explicit ordered day offsets', async () => {
    api.call.mockImplementation(async (method, params) =>
      method.endsWith('save_sequence')
        ? { ...params.data, name: 'sequence-new', modified: 'seq-v1' }
        : data(),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('New sequence')
    await fill(field('Sequence name'), 'My follow-up')
    await fill(field('Subject'), 'Following up')
    await fill(root.querySelector('textarea'), '<p>Any thoughts?</p>')
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.save_sequence',
      {
        data: {
          name: undefined,
          modified: undefined,
          title: 'My follow-up',
          steps: [
            {
              day_offset: 0,
              subject: 'Following up',
              content: '<p>Any thoughts?</p>',
            },
          ],
        },
      },
    )
  })

  it('pauses a scheduled email before opening it for editing', async () => {
    const scheduled = {
      ...baseDraft,
      status: 'Scheduled',
      send_at: '2030-07-15T08:00:00.000Z',
      timezone: 'Europe/London',
    }
    api.call.mockImplementation(async (method) =>
      method.endsWith('unschedule_draft')
        ? { ...scheduled, status: 'Draft', modified: 'v2', send_at: null }
        : data([scheduled]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    expect(api.call).toHaveBeenCalledWith(
      'crm.api.scheduled_email.unschedule_draft',
      { name: 'draft-1', modified: 'v1' },
    )
    expect(root.textContent).toContain('Email paused.')
    expect(field('Send at').value).toBe('2030-07-15T09:00')
    expect(
      [...root.querySelectorAll('li span')].some(
        (item) => item.textContent === 'Scheduled',
      ),
    ).toBe(false)
  })

  it('keeps the existing editor when pausing another scheduled email conflicts', async () => {
    const scheduled = {
      ...baseDraft,
      name: 'scheduled-2',
      status: 'Scheduled',
      subject: 'Scheduled second',
    }
    api.call.mockImplementation(async (method) => {
      if (method.endsWith('unschedule_draft'))
        throw { messages: ['Email is already sending.'] }
      return data([baseDraft, scheduled])
    })
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Subject'), 'Keep my local changes')
    root.querySelectorAll('li')[1].querySelector('button').click()
    await tick()
    expect(root.textContent).toContain('Email is already sending.')
    expect(field('Subject').value).toBe('Keep my local changes')
    expect(root.textContent).not.toContain('Email paused.')
  })

  it('updates the visible draft after save even when scheduling fails', async () => {
    api.call.mockImplementation(async (method, params) => {
      if (method.endsWith('save_draft'))
        return {
          ...params.data,
          status: 'Draft',
          name: 'draft-new',
          modified: 'v2',
        }
      if (method.endsWith('schedule_draft'))
        throw { messages: ['Mailbox was disconnected.'] }
      return data()
    })
    mount()
    await click('Drafts & scheduled emails')
    await click('New saved draft')
    await fill(field('Subject'), 'Saved but not scheduled')
    await fill(field('Send at'), '2030-07-15T09:00')
    await click('Schedule email')
    expect(root.querySelector('li').textContent).toContain(
      'Saved but not scheduled',
    )
    expect(root.textContent).toContain(
      'Your draft was saved, but scheduling was not confirmed.',
    )
    expect(field('Subject').value).toBe('Saved but not scheduled')
  })

  it('blocks saving, sending and switching drafts while an attachment uploads', async () => {
    api.deferUpload = true
    api.call.mockResolvedValue(
      data([baseDraft, { ...baseDraft, name: 'draft-2' }]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await click('Attach a file')
    expect(button('Save draft').disabled).toBe(true)
    expect(button('Send now').disabled).toBe(true)
    expect(button('New saved draft').disabled).toBe(true)
    expect(
      [...root.querySelectorAll('li button')]
        .filter((item) => item.textContent === 'Edit email')
        .every((item) => item.disabled),
    ).toBe(true)
    api.finishUpload()
    await tick()
    expect(button('Save draft').disabled).toBe(false)
    expect(root.textContent).toContain('uploaded-file')
  })

  it('ignores a stale attachment upload after the customer/editor is replaced', async () => {
    api.deferUpload = true
    api.call.mockImplementation(async (_, params) =>
      data([{ ...baseDraft, name: params.reference_name, attachments: [] }]),
    )
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await click('Attach a file')
    state.referenceName = 'deal-2'
    await tick()
    await click('Edit email')
    api.finishUpload()
    await tick()
    expect(root.textContent).not.toContain('uploaded-file')
    expect(field('Subject').value).toBe('Saved subject')
  })

  it('does not overwrite an unsaved sequence through the selector or Edit button', async () => {
    const sequence = {
      name: 'seq-1',
      modified: 'v1',
      title: 'Template',
      steps: [{ day_offset: 0, subject: 'First', content: '<p>Hello</p>' }],
    }
    api.call.mockResolvedValue({ ...data(), sequences: [sequence] })
    mount()
    await click('Drafts & scheduled emails')
    await fill(field('Sequence'), 'seq-1')
    await click('Edit sequence')
    await fill(field('Sequence name'), 'Unsaved template changes')
    expect(field('Sequence').disabled).toBe(true)
    expect(button('Edit sequence').disabled).toBe(true)
    window.confirm.mockReturnValue(false)
    await click('New sequence')
    expect(field('Sequence name').value).toBe('Unsaved template changes')
  })

  it('warns about leaving after only the schedule time changes', async () => {
    api.call.mockResolvedValue(data([baseDraft]))
    mount()
    await click('Drafts & scheduled emails')
    await click('Edit email')
    await fill(field('Send at'), '2030-07-15T09:00')
    window.confirm.mockReturnValue(false)
    await click('Hide drafts & scheduled emails')
    expect(window.confirm).toHaveBeenCalledWith(
      'Leave without saving your email changes?',
    )
    expect(field('Send at').value).toBe('2030-07-15T09:00')
  })

  it('does not replace a new customer list with an older in-flight response', async () => {
    let resolveOld
    api.call
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve
          }),
      )
      .mockResolvedValue(
        data([{ ...baseDraft, name: 'new', subject: 'New customer email' }]),
      )
    mount()
    await click('Drafts & scheduled emails')
    state.referenceName = 'deal-2'
    await tick()
    resolveOld(data([baseDraft]))
    await tick()
    expect(root.textContent).toContain('New customer email')
    expect(root.textContent).not.toContain('Saved subject')
  })
})
