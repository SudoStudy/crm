/* eslint-disable vue/one-component-per-file, vue/require-prop-types, vue/no-reserved-component-names -- lightweight Vue test doubles */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
const state = vi.hoisted(() => ({
  upload: vi.fn(),
  validate: null,
  success: null,
  failure: null,
  inline: null,
}))
vi.mock('@/components/editor/config', () => ({
  buildEditorExtensions: () => [],
  fullToolbar: [],
  uploadFile: state.upload,
}))
vi.mock('@/components/IconPicker.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/Controls/MultiSelectEmailInput.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/Modals/EmailTemplateSelectorModal.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/data/document', () => ({
  useDocument: () => ({ document: { doc: { user_emails: [] } } }),
}))
vi.mock('@/utils', () => ({
  validateEmail: () => true,
  submitShortcutLabel: 'Ctrl+Enter',
}))
vi.mock('frappe-ui/frappe', () => ({
  useTelemetry: () => ({ capture: vi.fn() }),
}))
vi.mock('frappe-ui', () => ({
  call: vi.fn(),
  FormControl: { render: () => null },
  FileUploader: defineComponent({
    props: ['validateFile'],
    emits: ['success', 'failure'],
    setup(p, { emit, slots }) {
      state.validate = () => p.validateFile({ name: 'a.pdf' })
      state.success = () =>
        emit('success', { name: 'file-1', file_name: 'a.pdf' })
      state.failure = () => emit('failure', new Error('upload failed'))
      return () => slots.default({ openFileSelector: vi.fn() })
    },
  }),
}))
vi.mock('frappe-ui/editor', () => ({
  Editor: defineComponent({
    props: ['uploadFunction'],
    setup(p, { expose, slots }) {
      state.inline = (file) => p.uploadFunction(file)
      expose({ editor: {} })
      return () => slots.default()
    },
  }),
  EditorContent: { render: () => null },
  EditorFixedMenu: { render: () => null },
  EditorTableMenu: { render: () => null },
}))
import EmailEditor from '@/components/EmailEditor.vue'
const tick = async () => {
  await Promise.resolve()
  await nextTick()
}
describe('existing email editor scheduling actions and uploads', () => {
  let app, root, uploading, attachments, busy
  function mount() {
    uploading = []
    attachments = ref([])
    busy = ref(false)
    root = document.createElement('div')
    document.body.appendChild(root)
    app = createApp({
      render: () =>
        h(
          EmailEditor,
          {
            modelValue: { name: 'deal-1', email: 'customer@example.com' },
            attachments: attachments.value,
            'onUpdate:attachments': (v) => {
              attachments.value = v
            },
            onUploading: (v) => uploading.push(v),
            busy: busy.value,
            submitLabel: 'Schedule',
          },
          { 'secondary-actions': () => h('button', 'Send now') },
        ),
    })
    app.provide('session', { user: 'rep@example.com' })
    app.component(
      'Button',
      defineComponent({
        props: ['label'],
        setup: (p) => () => h('button', p.label),
      }),
    )
    app.config.globalProperties.__ = globalThis.__
    app.mount(root)
  }
  afterEach(() => {
    app.unmount()
    root.remove()
    state.upload.mockReset()
  })
  it('renders the customized primary action and a separate immediate-send action', () => {
    mount()
    expect(root.textContent).toContain('Schedule (Ctrl+Enter)')
    expect(root.textContent).toContain('Send now')
  })
  it('tracks real attachment validation through success and failure, rejecting another upload while busy', async () => {
    mount()
    expect(state.validate()).toBeNull()
    expect(uploading).toEqual([true])
    expect(state.validate()).toBeInstanceOf(Error)
    state.success()
    await tick()
    expect(attachments.value.map((f) => f.name)).toEqual(['file-1'])
    expect(uploading).toEqual([true, false])
    state.validate()
    state.failure()
    await tick()
    expect(uploading).toEqual([true, false, true, false])
    expect(root.querySelector('[role=alert]').textContent).toContain(
      'could not be uploaded',
    )
    busy.value = true
    await tick()
    expect(state.validate()).toBeInstanceOf(Error)
  })
  it('tracks inline image uploads through completion and failure', async () => {
    mount()
    let finish
    state.upload.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const pending = state.inline({ name: 'image.png' })
    expect(uploading).toEqual([true])
    finish({ file_url: '/private/files/image.png' })
    await pending
    expect(uploading).toEqual([true, false])
    state.upload.mockRejectedValueOnce(new Error('rejected'))
    await expect(state.inline({ name: 'bad.png' })).rejects.toThrow('rejected')
    await tick()
    expect(uploading).toEqual([true, false, true, false])
    expect(root.querySelector('[role=alert]').textContent).toContain(
      'image could not be uploaded',
    )
  })
})
