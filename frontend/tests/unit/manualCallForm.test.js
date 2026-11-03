import { describe, it, expect, vi } from 'vitest'
import { CRMCallLog } from '@/doctypes/crm_call_log/form'

describe('manual call form', () => {
  function form(doc = {}) {
    const controller = new CRMCallLog()
    controller.doc = doc
    controller.call = vi.fn().mockResolvedValue({
      type: 'Outgoing',
      status: 'Completed',
      caller: 'rep@example.com',
      from: '+442079460001',
      to: '+85223456789',
    })
    return controller
  }

  it('prefills new call numbers and caller from the linked customer', async () => {
    const f = form({
      reference_doctype: 'CRM Lead',
      reference_docname: 'LEAD-1',
    })
    await f.onRender()
    expect(f.call).toHaveBeenCalledWith(
      'crm.fcrm.doctype.crm_call_log.crm_call_log.get_manual_call_defaults',
      { reference_doctype: 'CRM Lead', reference_docname: 'LEAD-1' },
    )
    expect(f.doc).toMatchObject({
      to: '+85223456789',
      from: '+442079460001',
      caller: 'rep@example.com',
    })
  })

  it('preserves existing calls and explicit form values', async () => {
    const saved = form({ name: 'CALL-1' })
    await saved.onRender()
    expect(saved.call).not.toHaveBeenCalled()
    const f = form({ to: '+123456789', status: 'No Answer' })
    await f.onRender()
    expect(f.doc.to).toBe('+123456789')
    expect(f.doc.status).toBe('No Answer')
  })

  it('reverses numbers and user when changing the call direction', () => {
    const f = form({
      type: 'Incoming',
      from: '+111',
      to: '+222',
      caller: 'rep@example.com',
    })
    f.oldValue = 'Outgoing'
    f.type()
    expect(f.doc).toMatchObject({
      from: '+222',
      to: '+111',
      caller: null,
      receiver: 'rep@example.com',
    })
  })
})
