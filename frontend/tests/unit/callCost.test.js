import { createApp, nextTick } from 'vue'
import { describe, it, expect, vi, afterEach } from 'vitest'
const mocks = vi.hoisted(() => ({ call: vi.fn() }))
vi.mock('frappe-ui', () => ({ call: mocks.call }))
import CallCost from '@/components/Activities/CallCost.vue'
let app, root
const settle = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}
async function mount(result) {
  mocks.call.mockReset().mockResolvedValue(result)
  root = document.createElement('div')
  document.body.append(root)
  app = createApp(CallCost, { name: 'CALL-1' })
  app.config.globalProperties.__ = globalThis.__
  app.mount(root)
  await settle()
}
afterEach(() => {
  app?.unmount()
  root?.remove()
})
describe('Platform call voice charge', () => {
  it('shows an actual complete charge including zero', async () => {
    await mount({ status: 'Complete', amount: 0, currency: 'USD' })
    expect(root.textContent).toContain('$0.0000')
    expect(mocks.call).toHaveBeenCalledWith(
      'crm.api.performance.get_call_cost',
      { name: 'CALL-1' },
    )
  })
  it('does not pretend an unpriced call is free', async () => {
    await mount({ status: 'Pending', amount: null })
    expect(root.textContent).toContain('Pending')
    expect(root.textContent).not.toContain('$0')
  })
  it('marks known partial charges and keeps currency explicit', async () => {
    await mount({ status: 'Partial', amount: 0.07, currency: 'USD' })
    expect(root.textContent).toContain('$0.0700')
    expect(root.textContent).toContain('billing pending')
  })
  it('hides nonplatform calls', async () => {
    await mount({ status: 'Excluded' })
    expect(root.textContent).toBe('')
  })
})
