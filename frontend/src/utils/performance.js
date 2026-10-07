export function normalizeFilters(query, context) {
  const fallback = context.today.slice(0, 7) + '-01'
  const period = query.period === 'quarter' ? 'quarter' : 'month'
  const anchor =
    typeof query.anchor === 'string' &&
    /^\d{4}-(0[1-9]|1[0-2])-01$/.test(query.anchor)
      ? query.anchor
      : fallback
  const allowed = context.users.map((user) => user.name)
  const defaultSalesperson =
    context.manager &&
    Array.isArray(context.team_users) &&
    !context.team_users.includes(context.user)
      ? 'team'
      : context.user
  const salesperson =
    context.manager &&
    (query.salesperson === 'team' || allowed.includes(query.salesperson))
      ? query.salesperson
      : defaultSalesperson
  return {
    salesperson,
    period,
    anchor: periodMonths(anchor, period)[0],
    mode: query.mode === 'owned_records' ? 'owned_records' : 'performed_by',
    kind: [
      'call',
      'change',
      'note',
      'task',
      'communication',
      'comment',
    ].includes(query.kind)
      ? query.kind
      : 'all',
  }
}

function monthDate(anchor) {
  return new Date(anchor + 'T12:00:00Z')
}

export function shiftPeriod(anchor, period, direction) {
  const date = monthDate(anchor)
  date.setUTCMonth(
    date.getUTCMonth() + direction * (period === 'quarter' ? 3 : 1),
  )
  return date.toISOString().slice(0, 10)
}

export function periodMonths(anchor, period) {
  if (period !== 'quarter') return [anchor]
  const date = monthDate(anchor)
  date.setUTCMonth(Math.floor(date.getUTCMonth() / 3) * 3)
  const start = date.toISOString().slice(0, 10)
  return [start, shiftPeriod(start, 'month', 1), shiftPeriod(start, 'month', 2)]
}

export function periodLabel(anchor, period = 'month') {
  const date = monthDate(anchor)
  return period === 'quarter'
    ? `Q${Math.floor(date.getUTCMonth() / 3) + 1} ${date.getUTCFullYear()}`
    : date.toLocaleDateString('en-US', {
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC',
      })
}

export function money(value) {
  if (value == null || !Number.isFinite(Number(value))) return 'Not set'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: Number(value) % 1 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value)
}

export function targetAmount(value) {
  if (
    String(value).trim() === '' ||
    !Number.isFinite(Number(value)) ||
    Number(value) < 0
  )
    throw new Error('Enter a finite, nonnegative USD amount.')
  return Number(value)
}

export function recordRoute(doctype, name) {
  if (!name) return null
  if (doctype === 'CRM Deal') return { name: 'Deal', params: { dealId: name } }
  if (doctype === 'CRM Lead') return { name: 'Lead', params: { leadId: name } }
  return null
}

export function sourceLink(doctype, name, url) {
  if (
    typeof url === 'string' &&
    /^\/(crm|app)\//.test(url) &&
    !url.includes('\\')
  )
    return url
  const sources = {
    'CRM Call Log': 'crm-call-log',
    'CRM Task': 'crm-task',
    'FCRM Note': 'fcrm-note',
    Communication: 'communication',
    'CRM Lead': 'crm-lead',
    'CRM Deal': 'crm-deal',
  }
  return sources[doctype] && name
    ? `/app/${sources[doctype]}/${encodeURIComponent(name)}`
    : null
}

export function activityTime(timestamp, timezone) {
  if (!timestamp) return '—'
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(timestamp)) return timestamp.slice(11, 16)
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: timezone,
      })
}

export function detailEntries(details) {
  if (!details) return []
  if (typeof details === 'string') return [['Details', details]]
  return Object.entries(details).map(([key, value]) => [
    key.replaceAll('_', ' '),
    typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—'),
  ])
}
