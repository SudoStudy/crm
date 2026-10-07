import { describe, it, expect } from 'vitest'
import {
  normalizeFilters,
  shiftPeriod,
  periodMonths,
  periodLabel,
  money,
  targetAmount,
  recordRoute,
  sourceLink,
  activityTime,
} from '@/utils/performance'

const rep = {
  user: 'rep@example.com',
  manager: false,
  today: '2026-10-07',
  users: [{ name: 'rep@example.com', full_name: 'Rep' }],
}

describe('Performance filters and presentation', () => {
  it('locks rep selection to their identity and validates route filters', () => {
    expect(
      normalizeFilters(
        {
          salesperson: 'team',
          anchor: 'broken',
          period: 'year',
          mode: 'anything',
        },
        rep,
      ),
    ).toEqual({
      salesperson: rep.user,
      anchor: '2026-10-01',
      period: 'month',
      mode: 'performed_by',
      kind: 'all',
    })
    expect(
      normalizeFilters(
        { salesperson: 'unknown', anchor: '2026-13-01' },
        { ...rep, manager: true },
      ).salesperson,
    ).toBe(rep.user)
  })
  it('accepts team only for managers and aligns quarters', () => {
    const manager = { ...rep, manager: true, team_users: ['other@example.com'] }
    expect(normalizeFilters({}, manager).salesperson).toBe('team')
    expect(
      normalizeFilters({ salesperson: rep.user }, manager).salesperson,
    ).toBe(rep.user)
    expect(
      normalizeFilters({}, { ...manager, team_users: [rep.user] }).salesperson,
    ).toBe(rep.user)
    expect(
      normalizeFilters(
        {
          salesperson: 'team',
          anchor: '2026-11-01',
          period: 'quarter',
          mode: 'owned_records',
        },
        { ...rep, manager: true },
      ),
    ).toEqual({
      salesperson: 'team',
      anchor: '2026-10-01',
      period: 'quarter',
      mode: 'owned_records',
      kind: 'all',
    })
    expect(periodMonths('2026-10-01', 'quarter')).toEqual([
      '2026-10-01',
      '2026-11-01',
      '2026-12-01',
    ])
    expect(shiftPeriod('2026-10-01', 'quarter', 1)).toBe('2027-01-01')
    expect(shiftPeriod('2026-01-01', 'month', -1)).toBe('2025-12-01')
    expect(periodLabel('2026-10-01', 'quarter')).toBe('Q4 2026')
  })
  it('keeps zero and missing money distinct and rejects nonfinite/negative target values', () => {
    expect(money(0)).toBe('$0')
    expect(money(null)).toBe('Not set')
    expect(money(120.5)).toBe('$120.50')
    expect(targetAmount('0')).toBe(0)
    for (const value of ['', '-1', 'Infinity', 'NaN'])
      expect(() => targetAmount(value)).toThrow()
  })
  it('links actual CRM records and formats site-local timestamps without browser shifts', () => {
    expect(recordRoute('CRM Deal', 'DEAL-1')).toEqual({
      name: 'Deal',
      params: { dealId: 'DEAL-1' },
    })
    expect(recordRoute('CRM Lead', 'LEAD-1')).toEqual({
      name: 'Lead',
      params: { leadId: 'LEAD-1' },
    })
    expect(recordRoute('Version', 'v1')).toBeNull()
    expect(sourceLink('Version', 'v1', '/crm/deals/DEAL-1')).toBe(
      '/crm/deals/DEAL-1',
    )
    expect(sourceLink('Version', 'v1')).toBeNull()
    expect(sourceLink('Version', 'v1', 'javascript:alert(1)')).toBeNull()
    expect(activityTime('2026-10-07 10:42:00', 'Asia/Karachi')).toBe('10:42')
    expect(activityTime('2026-10-07T05:42:00Z', 'Asia/Karachi')).toBe('10:42')
  })
})
