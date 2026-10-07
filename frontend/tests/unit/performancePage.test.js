import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'

const mocks = vi.hoisted(() => ({ call: vi.fn() }))
vi.mock('frappe-ui', async () => ({
  Button: (
    await import('../../node_modules/frappe-ui/src/components/Button/Button.vue')
  ).default,
  Dialog: (
    await import('../../node_modules/frappe-ui/src/components/Dialog/Dialog.vue')
  ).default,
  call: mocks.call,
}))
import Performance from '@/pages/Performance.vue'

const context = {
  user: 'rep@example.com',
  manager: false,
  today: '2026-10-07',
  timezone: 'Asia/Karachi',
  users: [
    { name: 'rep@example.com', full_name: 'Rep' },
    { name: 'other@example.com', full_name: 'Other' },
  ],
}
const summary = {
  period: { start: '2026-10-01', end: '2026-11-01', months: ['2026-10-01'] },
  target: 300,
  actual: 120,
  remaining: 180,
  progress: 40,
  weighted_pipeline: 450,
  coverage: 2.5,
  warnings: [],
  targets: [{ month: '2026-10-01', amount: 300, source: 'monthly' }],
  deals: [
    {
      name: 'DEAL-1',
      title: 'Riverside Academy',
      kind: 'won',
      amount: 120,
      weighted: 0,
      expected_mrr: 500,
      probability: 100,
      status: 'Won',
      won_at: '2026-10-05',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}
const activity = {
  days: [
    {
      date: '2026-10-07',
      events: [
        {
          id: 'call-1',
          kind: 'call',
          timestamp: '2026-10-07 10:42:00',
          title: 'Connected',
          details: 'Reached department',
          actor: 'Rep',
          source_doctype: 'CRM Call Log',
          source_name: 'CALL-1',
          parent_doctype: 'CRM Deal',
          parent_name: 'DEAL-1',
        },
      ],
    },
  ],
  page: 1,
  page_size: 50,
  total: 1,
}
const settle = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

describe('Native Performance page', () => {
  let app, root, router, header
  const button = (label) =>
    [...document.querySelectorAll('button')].find(
      (b) =>
        b.textContent.trim() === label ||
        b.getAttribute('aria-label') === label,
    )
  async function mount(query = {}) {
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/performance', name: 'Performance', component: Performance },
        {
          path: '/deals/:dealId',
          name: 'Deal',
          component: { template: '<div />' },
        },
        {
          path: '/leads/:leadId',
          name: 'Lead',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push({ name: 'Performance', query })
    await router.isReady()
    root = document.createElement('div')
    header = document.createElement('div')
    header.id = 'app-header'
    document.body.append(header, root)
    app = createApp(Performance)
    app.use(router)
    app.config.globalProperties.__ = globalThis.__
    app.mount(root)
    await settle()
  }
  beforeEach(() => {
    mocks.call
      .mockReset()
      .mockImplementation((method) =>
        Promise.resolve(
          method.endsWith('get_context')
            ? context
            : method.endsWith('get_activity')
              ? activity
              : summary,
        ),
      )
  })
  afterEach(() => {
    app?.unmount()
    root?.remove()
    header?.remove()
    app = null
  })

  it('renders real summary and linked activity while locking a rep to self', async () => {
    await mount({ salesperson: 'other@example.com' })
    expect(root.textContent).toContain('Riverside Academy')
    expect(root.textContent).toContain('Expected MRR (USD)')
    const cells = [...root.querySelectorAll('tbody tr td')].map((cell) =>
      cell.textContent.trim(),
    )
    expect(cells).toEqual([
      'Riverside Academy',
      'Won',
      '$500',
      '100%',
      '$120 actual',
      '2026-10-05',
    ])
    expect(root.querySelector('a[href="/deals/DEAL-1"]')).not.toBeNull()
    expect(button('Edit target')).toBeUndefined()
    expect(root.querySelector('[aria-label="Salesperson"]')).toBeNull()
    expect(
      mocks.call.mock.calls.find(([m]) => m.endsWith('get_summary'))[1]
        .salesperson,
    ).toBe(context.user)
    expect(root.querySelector('details').textContent).toContain('CRM Call Log')
    expect(root.querySelector('details').textContent).toContain(
      'Reached department',
    )
  })
  it('persists quarter navigation and does not refetch independent daily activity', async () => {
    await mount()
    mocks.call.mockClear()
    button('Quarter').click()
    await settle()
    expect(router.currentRoute.value.query.period).toBe('quarter')
    button('Next period').click()
    await settle()
    expect(router.currentRoute.value.query.anchor).toBe('2027-01-01')
    expect(
      mocks.call.mock.calls.filter(([m]) => m.endsWith('get_activity')),
    ).toHaveLength(0)
    expect(mocks.call.mock.calls.at(-1)[1]).toMatchObject({
      period: 'quarter',
      anchor: '2027-01-01',
    })
  })
  it('discards a late response after a period change', async () => {
    let resolveOld
    mocks.call.mockImplementation((m, p) => {
      if (m.endsWith('get_context')) return Promise.resolve(context)
      if (m.endsWith('get_activity')) return Promise.resolve(activity)
      if (p.anchor === '2026-10-01')
        return new Promise((resolve) => {
          resolveOld = resolve
        })
      return Promise.resolve({ ...summary, actual: 999 })
    })
    await mount()
    button('Next period').click()
    await settle()
    resolveOld({ ...summary, actual: 1 })
    await settle()
    expect(root.querySelector('[data-testid="actual"]').textContent).toBe(
      '$999',
    )
  })

  it('filters activity on the server before pagination and keeps summary independent', async () => {
    await mount()
    mocks.call.mockClear()
    const kind = root.querySelector('[aria-label="Activity type"]')
    kind.value = 'call'
    kind.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    expect(router.currentRoute.value.query.kind).toBe('call')
    expect(mocks.call).toHaveBeenCalledWith(
      'crm.api.performance.get_activity',
      {
        salesperson: context.user,
        mode: 'performed_by',
        kind: 'call',
        page: 1,
        page_size: 50,
      },
    )
    expect(
      mocks.call.mock.calls.filter(([m]) => m.endsWith('get_summary')),
    ).toHaveLength(0)
  })

  it('paginates real deals and activity without hiding further records', async () => {
    mocks.call.mockImplementation((m, p) =>
      Promise.resolve(
        m.endsWith('get_context')
          ? context
          : m.endsWith('get_activity')
            ? { ...activity, total: 60, page: p.page }
            : { ...summary, total: 25, page: p.page },
      ),
    )
    await mount()
    button('Next deals').click()
    await settle()
    expect(mocks.call).toHaveBeenCalledWith(
      'crm.api.performance.get_summary',
      expect.objectContaining({ page: 2 }),
    )
    button('Next activity').click()
    await settle()
    expect(mocks.call).toHaveBeenCalledWith(
      'crm.api.performance.get_activity',
      expect.objectContaining({ page: 2 }),
    )
    expect(button('Next deals').disabled).toBe(true)
    expect(button('Next activity').disabled).toBe(true)
  })

  it('shows team roster and warnings without allowing edits of an aggregate target', async () => {
    mocks.call.mockImplementation((m) =>
      Promise.resolve(
        m.endsWith('get_context')
          ? { ...context, manager: true, team_users: ['rep@example.com'] }
          : m.endsWith('get_activity')
            ? { ...activity, warnings: ['Activity history unavailable.'] }
            : {
                ...summary,
                target: null,
                warnings: ['Monthly targets are missing.'],
              },
      ),
    )
    await mount({ salesperson: 'team' })
    expect(button('Edit target').disabled).toBe(true)
    expect(root.textContent).toContain('Monthly targets are missing.')
    expect(root.textContent).toContain('Activity history unavailable.')
    expect(root.textContent).toContain('Team includes: Rep')
    expect(root.textContent).toContain('Not set')
  })
  it('does not call a zero target met when coverage is undefined', async () => {
    mocks.call.mockImplementation((m) =>
      Promise.resolve(
        m.endsWith('get_context')
          ? context
          : m.endsWith('get_activity')
            ? activity
            : {
                ...summary,
                target: 0,
                remaining: 0,
                progress: null,
                coverage: null,
                warnings: [
                  'Target is zero; progress and coverage are not calculated.',
                ],
              },
      ),
    )
    await mount()
    expect(root.textContent).not.toContain('Target met')
    expect(root.textContent).toContain('Target is zero')
  })
  it('shows section errors with a working retry and empty states', async () => {
    mocks.call.mockImplementation((m) =>
      m.endsWith('get_context')
        ? Promise.resolve(context)
        : m.endsWith('get_activity')
          ? Promise.resolve({ ...activity, days: [], total: 0 })
          : Promise.reject(new Error('Service unavailable')),
    )
    await mount()
    expect(root.textContent).toContain('Service unavailable')
    expect(root.textContent).toContain('No recorded activity')
    mocks.call.mockImplementation((m) =>
      Promise.resolve(
        m.endsWith('get_activity')
          ? activity
          : { ...summary, deals: [], total: 0 },
      ),
    )
    button('Retry summary').click()
    await settle()
    expect(root.textContent).toContain('No contributing deals')
  })
  it('lets managers edit an explicitly selected quarter month and recurring effective month', async () => {
    mocks.call.mockImplementation((m) =>
      Promise.resolve(
        m.endsWith('get_context')
          ? { ...context, manager: true }
          : m.endsWith('get_activity')
            ? activity
            : {
                ...summary,
                period: {
                  ...summary.period,
                  months: ['2026-10-01', '2026-11-01', '2026-12-01'],
                },
              },
      ),
    )
    await mount({ period: 'quarter' })
    button('Edit target').click()
    await settle()
    const month = document.querySelector('[aria-label="Target month"]')
    month.value = '2026-11-01'
    month.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    const amount = document.querySelector(
      '[aria-label="Monthly new MRR target (USD)"]',
    )
    amount.value = '450'
    amount.dispatchEvent(new Event('input', { bubbles: true }))
    const recur = document.querySelector(
      '[aria-label="Repeat for future months"]',
    )
    recur.checked = true
    recur.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    expect(document.body.textContent).toContain('November 2026')
    button('Save target').click()
    await settle()
    expect(mocks.call).toHaveBeenCalledWith('crm.api.performance.set_target', {
      salesperson: context.user,
      month: '2026-11-01',
      amount: 450,
      recurring: true,
    })
  })
  it('disables recurrence for a historical month while allowing its explicit target edit', async () => {
    mocks.call.mockImplementation((m) =>
      Promise.resolve(
        m.endsWith('get_context')
          ? { ...context, manager: true }
          : m.endsWith('get_activity')
            ? activity
            : summary,
      ),
    )
    await mount({ anchor: '2026-09-01' })
    button('Edit target').click()
    await settle()
    expect(
      document.querySelector('[aria-label="Repeat for future months"]')
        .disabled,
    ).toBe(true)
    expect(document.body.textContent).toContain(
      'Recurring targets must start in the current or a future month.',
    )
    expect(button('Save target').disabled).toBe(false)
  })
})
