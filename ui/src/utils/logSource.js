export const LOG_DATE = String.raw`\d{4}-\d{2}-\d{2}`
export const LOG_TIME = String.raw`\d{2}:\d{2}:\d{2}(?:[,.]\d{1,6})?`
export const LOG_LEVEL = 'CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG'

const levels = new Set(LOG_LEVEL.split('|'))
const leadingDate = new RegExp(`^${LOG_DATE}`, 'u')
const stampPattern = new RegExp(
  String.raw`^(?:(?<date>${LOG_DATE})(?<dateGap>[ \t]+))?(?<time>\d{2}:\d{2}:\d{2})(?<fraction>[,.]\d{1,6})?(?![\d,.])(?:(?<levelGap>[ \t]+)(?<level>${LOG_LEVEL})(?![\p{L}\p{N}_]))?(?<gap>[ \t]*)`,
  'u'
)
const legacyHeader = new RegExp(
  String.raw`^\s*(?:${LOG_DATE}\s+)?(?:${LOG_TIME}\s+)?(?:(?<source>\S+:\d+)\s+)?(?:${LOG_LEVEL})\s+`,
  'u'
)
const sourceHeaders = new WeakMap()

function readStamp(text) {
  const match = stampPattern.exec(text)
  if (!match) return null
  const { date, dateGap, time, fraction, levelGap, level, gap } = match.groups
  return {
    length: match[0].length,
    date: date ?? null,
    dateGap: dateGap ?? '',
    time,
    fraction: fraction ?? '',
    levelGap: levelGap ?? '',
    level: level ?? null,
    gap
  }
}

function structuredStamp(t, level, msg, text) {
  if (typeof t !== 'string' || !levels.has(level) || typeof msg !== 'string') return null
  if (text !== `${t} ${level} ${msg}`) return null
  const stamp = readStamp(t)
  if (!stamp || stamp.length !== t.length || stamp.level || stamp.gap) return null
  const gap = ` ${/^[ \t]*/u.exec(msg)[0]}`
  return { ...stamp, length: t.length + level.length + 1 + gap.length, levelGap: ' ', level, gap }
}

function legacyMessage(text, stamp) {
  if (stamp?.level && stamp.gap) return text.slice(stamp.length).trimStart()
  const header = legacyHeader.exec(text)
  if (!header) return text.trim()
  const message = text.slice(header[0].length)
  return header.groups.source ? message.replace(/^[A-Za-z_][\w.]*:\s*/u, '') : message
}

function readSourceHeader(record, text) {
  const { t, level, msg } = record
  const cached = sourceHeaders.get(record)
  if (cached?.text === text && cached.t === t && cached.level === level && cached.msg === msg)
    return cached
  const structured = structuredStamp(t, level, msg, text)
  const stamp = structured ?? readStamp(text)
  const header = { text, t, level, msg, stamp, body: structured ? msg : legacyMessage(text, stamp) }
  sourceHeaders.set(record, header)
  return header
}

export function normalizeLogSource(line) {
  const record = typeof line === 'object' && line !== null ? line : { text: line }
  const text = String(record.text ?? '')
  const { stamp, body } = readSourceHeader(record, text)
  return {
    id: record.id ?? null,
    at: Number.isFinite(record.at) ? record.at : null,
    text,
    stamp,
    level: stamp?.level ?? null,
    msg: body,
    group: record.group ?? null,
    room: record.room ?? null,
    agents: record.agents ?? null,
    task: record.task ?? null,
    backups: record.backups ?? null,
    recruitment: record.recruitment ?? null,
    event: record.event ?? null,
    inventory: record.inventory ?? null,
    parent: record.parent ?? null
  }
}

export function latestLogDate(lines) {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const { text, stamp } = normalizeLogSource(lines[index])
    const date = stamp?.date ?? leadingDate.exec(text)?.[0]
    if (date) return date
  }
  return ''
}
