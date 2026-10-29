import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'

const api = vi.hoisted(() => ({ call: vi.fn(), reload: vi.fn() }))
vi.mock('frappe-ui', () => ({
  call: api.call,
  getCachedDocumentResource: () => ({ reload: api.reload }),
  Button: defineComponent({
    inheritAttrs: false,
    props: {
      label: { type: { type: String, default: 'button' }, default: '' },
      disabled: Boolean,
      loading: Boolean,
      type: { type: String, default: 'button' },
    },
    emits: ['click'],
    setup(props, { emit, attrs }) {
      return () =>
        h(
          'button',
          {
            ...attrs,
            type: props.type || 'button',
            disabled: props.disabled || props.loading,
            onClick: () => emit('click'),
          },
          props.label,
        )
    },
  }),
}))
import PersonalAPISettings from '@/components/Settings/Profile/PersonalAPISettings.vue'
import PersonalMailboxSettings from '@/components/Settings/Profile/PersonalMailboxSettings.vue'

const status = (extra = {}) => ({
  api_configured: false,
  mailbox: {
    email_id: 'rep@example.com',
    connected: false,
    can_manage: true,
    ...extra,
  },
})
const tick = async () => {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('personal CRM settings', () => {
  let app, root
  const button = (label) =>
    [...root.querySelectorAll('button')].find((b) => b.textContent === label)
  function mount(component, props = {}) {
    root = document.createElement('div')
    document.body.appendChild(root)
    app = createApp(component, props)
    app.config.globalProperties.__ = globalThis.__
    app.mount(root)
  }
  beforeEach(() => {
    api.call.mockReset()
    api.reload.mockReset()
  })
  afterEach(() => {
    app?.unmount()
    root?.remove()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('generates own credentials only on click, masks them, and copies only on request', async () => {
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    api.call
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce({ api_key: 'test-key', api_secret: 'test-secret' })
    mount(PersonalAPISettings)
    await tick()
    expect(api.call).toHaveBeenCalledTimes(1)
    button('Generate API credentials').click()
    await tick()
    expect(api.call).toHaveBeenLastCalledWith(
      'crm.api.personal_settings.generate_personal_api_keys',
      { confirm_replace: false },
    )
    const inputs = [...root.querySelectorAll('input[readonly]')]
    expect(inputs.map((i) => i.type)).toEqual(['password', 'password'])
    expect(writeText).not.toHaveBeenCalled()
    button('Copy API secret').click()
    await tick()
    expect(writeText).toHaveBeenCalledWith('test-secret')
    button('Reveal credentials').click()
    await tick()
    expect(inputs.map((i) => i.type)).toEqual(['text', 'text'])
    expect(button('Replace API secret').disabled).toBe(true)
    app.unmount()
    app = null
    expect(root.textContent).not.toContain('test-secret')
    vi.unstubAllGlobals()
  })

  it('emits navigation when Back to profile is clicked', async () => {
    const onUpdateStep = vi.fn()
    api.call.mockResolvedValueOnce(status())
    mount(PersonalAPISettings, { onUpdateStep })
    await tick()
    button('Back to profile').click()
    await tick()
    expect(onUpdateStep).toHaveBeenCalledWith('profile-settings')
  })

  it('requires explicit confirmation to replace existing credentials', async () => {
    api.call
      .mockResolvedValueOnce({ ...status(), api_configured: true })
      .mockResolvedValueOnce({
        api_key: 'test-key',
        api_secret: 'new-test-secret',
      })
    mount(PersonalAPISettings)
    await tick()
    expect(button('Replace API secret').disabled).toBe(true)
    const checkbox = root.querySelector('input[type=checkbox]')
    checkbox.checked = true
    checkbox.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    button('Replace API secret').click()
    await tick()
    expect(api.call).toHaveBeenLastCalledWith(
      'crm.api.personal_settings.generate_personal_api_keys',
      { confirm_replace: true },
    )
  })

  it('refreshes credential status after an interrupted generation before allowing another attempt', async () => {
    api.call
      .mockResolvedValueOnce(status())
      .mockRejectedValueOnce(new Error('interrupted'))
      .mockResolvedValueOnce({ ...status(), api_configured: true })
    mount(PersonalAPISettings)
    await tick()
    button('Generate API credentials').click()
    await tick()
    await tick()
    expect(root.querySelector('input[type=checkbox]')).toBeTruthy()
    expect(button('Replace API secret').disabled).toBe(true)
    expect(root.querySelector('input[readonly]')).toBeNull()
  })

  it('prevents generation after a status load failure', async () => {
    api.call.mockRejectedValueOnce(new Error('test failure'))
    mount(PersonalAPISettings)
    await tick()
    expect(root.querySelector('[role=alert]')).toBeTruthy()
    expect(button('Generate API credentials')).toBeUndefined()
  })

  it('does not show a late generation response after leaving the page', async () => {
    let resolve
    api.call.mockResolvedValueOnce(status()).mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    mount(PersonalAPISettings)
    await tick()
    button('Generate API credentials').click()
    await tick()
    app.unmount()
    app = null
    resolve({ api_key: 'late-key', api_secret: 'late-secret' })
    await tick()
    expect(root.textContent).toBe('')
  })

  it('connects only the readonly account address and clears the password after success', async () => {
    api.call
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(status({ connected: true }).mailbox)
    mount(PersonalMailboxSettings)
    await tick()
    expect(root.querySelector('input[type=email]').readOnly).toBe(true)
    const input = root.querySelector('input[type=password]')
    input.value = 'test-app-password'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await tick()
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(api.call).toHaveBeenLastCalledWith(
      'crm.api.personal_settings.connect_personal_mailbox',
      { email_id: 'rep@example.com', password: 'test-app-password' },
    )
    expect(input.value).toBe('')
    expect(root.textContent).toContain('Your mailbox is connected')
    expect(api.reload).toHaveBeenCalledOnce()
  })

  it('does not echo provider errors or retain passwords after connection failure', async () => {
    api.call
      .mockResolvedValueOnce(status())
      .mockRejectedValueOnce(new Error('test-app-password'))
    mount(PersonalMailboxSettings)
    await tick()
    const input = root.querySelector('input[type=password]')
    input.value = 'test-app-password'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await tick()
    root
      .querySelector('form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(input.value).toBe('')
    expect(root.textContent).not.toContain('test-app-password')
    expect(root.querySelector('[role=alert]')).toBeTruthy()
  })

  it('keeps administrator-managed and shared mailboxes readonly', async () => {
    api.call.mockResolvedValueOnce(status({ can_manage: false }))
    mount(PersonalMailboxSettings)
    await tick()
    expect(root.querySelector('input[type=password]')).toBeNull()
    expect(button('Connect mailbox')).toBeUndefined()
    expect(root.textContent).toContain('managed by an administrator or shared')
  })
})
