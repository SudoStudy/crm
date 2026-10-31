// Convert a wall-clock selection in an explicit IANA zone without using the
// computer's timezone. Reject DST gaps and overlaps rather than guess a send time.
function formatter(timezone) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    })
  } catch {
    throw new Error('Choose a valid timezone, such as Europe/London.')
  }
}

function partsAt(value, format) {
  return Object.fromEntries(
    format
      .formatToParts(value)
      .filter((p) => p.type !== 'literal')
      .map((p) => [p.type, Number(p.value)]),
  )
}

function wallEpoch(parts) {
  return Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second || 0,
  )
}

function parseWall(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(
    value || '',
  )
  if (!match) throw new Error('Choose a date and time.')
  const [, year, month, day, hour, minute, second = '0'] = match
  const parts = {
    year: +year,
    month: +month,
    day: +day,
    hour: +hour,
    minute: +minute,
    second: +second,
  }
  const date = new Date(wallEpoch(parts))
  if (
    parts.year < 2000 ||
    date.getUTCFullYear() !== parts.year ||
    date.getUTCMonth() + 1 !== parts.month ||
    date.getUTCDate() !== parts.day ||
    parts.hour > 23 ||
    parts.minute > 59 ||
    parts.second > 59
  ) {
    throw new Error('Choose a valid date and time.')
  }
  return parts
}

export function scheduleInstant(value, timezone) {
  const wall = wallEpoch(parseWall(value))
  const format = formatter(timezone)
  const offsets = new Set()
  for (let hours = -36; hours <= 36; hours += 3) {
    const instant = wall + hours * 3600000
    offsets.add(wallEpoch(partsAt(instant, format)) - instant)
  }
  const matches = [...offsets]
    .map((offset) => wall - offset)
    .filter((instant) => wallEpoch(partsAt(instant, format)) === wall)
  if (!matches.length)
    throw new Error(
      'This local time does not exist because the clocks change. Choose another time.',
    )
  if (matches.length > 1)
    throw new Error(
      'This local time occurs twice because the clocks change. Choose another time.',
    )
  return new Date(matches[0]).toISOString()
}

export function scheduleWallTime(instant, timezone) {
  if (!instant) return ''
  const value = new Date(instant)
  if (!Number.isFinite(value.getTime())) return ''
  const p = partsAt(value, formatter(timezone))
  const pad = (n) => String(n).padStart(2, '0')
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

export function addScheduleDays(value, days) {
  const parts = parseWall(value)
  if (!Number.isInteger(days) || days < 0)
    throw new Error('Step delays must be whole days, zero or greater.')
  const date = new Date(wallEpoch(parts) + days * 86400000)
  return date.toISOString().slice(0, 16)
}

export function sequencePreview(steps, start, timezone) {
  if (!steps.length || steps.length > 20)
    throw new Error('Add between 1 and 20 sequence steps.')
  let previous = -1
  return steps.map((step) => {
    const day = Number(step.day_offset)
    if (!Number.isInteger(day) || day < 0 || day > 365 || day <= previous)
      throw new Error('Step days must increase, for example 0, 3, 7.')
    previous = day
    const wall = addScheduleDays(start, day)
    return {
      ...step,
      day_offset: day,
      wall,
      send_at: scheduleInstant(wall, timezone),
    }
  })
}

export function emailStatusActions(status) {
  return {
    edit: ['Draft', 'Scheduled'].includes(status),
    cancel: ['Draft', 'Scheduled', 'Error'].includes(status),
    remove: ['Draft', 'Canceled'].includes(status),
  }
}

export function draftFields(draft = {}, defaults = {}) {
  return {
    name: draft.name || undefined,
    modified: draft.modified || undefined,
    reference_doctype: defaults.reference_doctype,
    reference_name: defaults.reference_name,
    sender: draft.sender ?? defaults.sender ?? '',
    recipients: draft.recipients ?? defaults.recipients ?? '',
    cc: draft.cc || '',
    bcc: draft.bcc || '',
    subject: draft.subject || '',
    content: draft.content || '',
    attachments: [...(draft.attachments || [])],
    stop_on_reply: draft.stop_on_reply !== false && draft.stop_on_reply !== 0,
  }
}
