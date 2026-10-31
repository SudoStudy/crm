import { describe, expect, it } from 'vitest'
import {
  addScheduleDays,
  draftFields,
  emailStatusActions,
  scheduleInstant,
  scheduleWallTime,
  sequencePreview,
} from '@/utils/emailSchedule'

describe('explicit email schedule timezone', () => {
  it.each([
    ['2026-11-03T09:00', 'Europe/London', '2026-11-03T09:00:00.000Z'],
    ['2026-07-03T09:00', 'Europe/London', '2026-07-03T08:00:00.000Z'],
    ['2026-11-03T09:00', 'America/Los_Angeles', '2026-11-03T17:00:00.000Z'],
    ['2026-11-03T09:00', 'Asia/Kathmandu', '2026-11-03T03:15:00.000Z'],
    ['2026-11-03T23:30', 'Pacific/Honolulu', '2026-11-04T09:30:00.000Z'],
  ])(
    'converts %s in %s independently of the computer timezone',
    (wall, zone, expected) => {
      expect(scheduleInstant(wall, zone)).toBe(expected)
      expect(scheduleWallTime(expected, zone)).toBe(wall)
    },
  )
  it.each([
    ['2026-03-29T01:30', 'Europe/London', 'does not exist'],
    ['2026-10-25T01:30', 'Europe/London', 'occurs twice'],
    ['2027-03-14T02:30', 'America/New_York', 'does not exist'],
    ['2026-11-01T01:30', 'America/New_York', 'occurs twice'],
  ])('rejects ambiguous or nonexistent %s in %s', (wall, zone, error) => {
    expect(() => scheduleInstant(wall, zone)).toThrow(error)
  })
  it.each([
    '',
    '2026-02-30T09:00',
    '2026-13-02T09:00',
    '2026-11-03T25:00',
    '2026-11-03T09:60',
    '2026-11-03',
  ])('rejects invalid wall time %s', (wall) => {
    expect(() => scheduleInstant(wall, 'UTC')).toThrow()
  })
  it('rejects invalid zones and tolerates missing historical dates', () => {
    expect(() => scheduleInstant('2026-11-03T09:00', 'Moon/Base')).toThrow(
      'timezone',
    )
    expect(scheduleWallTime('', 'UTC')).toBe('')
    expect(scheduleWallTime('invalid', 'UTC')).toBe('')
  })
  it('keeps each sequence step at the same local hour across daylight saving', () => {
    const steps = sequencePreview(
      [{ day_offset: 0 }, { day_offset: 3 }],
      '2026-10-23T09:00',
      'Europe/London',
    )
    expect(steps.map((step) => step.send_at)).toEqual([
      '2026-10-23T08:00:00.000Z',
      '2026-10-26T09:00:00.000Z',
    ])
    expect(addScheduleDays('2026-12-31T09:00', 1)).toBe('2027-01-01T09:00')
  })
  it.each([[[0, 0]], [[3, 2]], [[-1]], [[0.5]]])(
    'rejects unordered offsets %s',
    (offsets) => {
      expect(() =>
        sequencePreview(
          offsets.map((day_offset) => ({ day_offset })),
          '2026-12-01T09:00',
          'UTC',
        ),
      ).toThrow('Step days')
    },
  )
})

describe('saved email state', () => {
  it('restores every saved draft field without sharing attachment mutations', () => {
    const source = {
      name: 'email-1',
      modified: 'revision',
      sender: 'rep@example.com',
      recipients: 'customer@example.com',
      cc: 'cc@example.com',
      bcc: 'bcc@example.com',
      subject: 'Proposal',
      content: '<p>Hello</p>',
      attachments: ['file-1'],
      stop_on_reply: 0,
    }
    const draft = draftFields(source, {
      reference_doctype: 'CRM Deal',
      reference_name: 'deal-1',
    })
    expect(draft).toMatchObject({
      ...source,
      stop_on_reply: false,
      reference_doctype: 'CRM Deal',
      reference_name: 'deal-1',
    })
    draft.attachments.push('file-2')
    expect(source.attachments).toEqual(['file-1'])
  })
  it('keeps intentionally empty saved addresses instead of adding defaults', () => {
    expect(
      draftFields(
        { sender: '', recipients: '' },
        { sender: 'rep@example.com', recipients: 'customer@example.com' },
      ),
    ).toMatchObject({ sender: '', recipients: '' })
  })
  it.each(['Sending', 'Sent', 'Error', 'Canceled'])(
    'never offers retry/edit for %s',
    (status) => {
      expect(emailStatusActions(status).edit).toBe(false)
    },
  )
  it('allows deletion only before sending or after cancellation', () => {
    expect(emailStatusActions('Draft').remove).toBe(true)
    expect(emailStatusActions('Canceled').remove).toBe(true)
    expect(emailStatusActions('Scheduled').remove).toBe(false)
    expect(emailStatusActions('Error').remove).toBe(false)
  })
})
