import { i18n } from '@/i18n'

export function softwareVersionBadge(version, deployment = null) {
  if (deployment === 'source') return 'source'
  if (/-alpha\.\d+\.g[0-9a-f]{8}(?:\+.*)?$/.test(version)) return 'nightly'
  if (/-alpha(?:\.|$|\+)/.test(version)) return 'alpha'
  if (
    /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*)?$/.test(
      version
    )
  )
    return 'stable'
  return ''
}

function timestamp(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null
  const milliseconds = value * 1000
  return Number.isFinite(new Date(milliseconds).getTime()) ? milliseconds : null
}

export function resourceVersionBadge(metadata, now = Date.now()) {
  const activity = metadata?.activity || {}
  const gacha = metadata?.gacha || {}
  const isGacha = (timestamp(gacha.time) || 0) > (timestamp(activity.time) || 0)
  const event = isGacha ? gacha : activity
  const start = timestamp(event.time)
  const end = timestamp(event.endTime)
  const base = { name: event.name || '', kind: isGacha ? '卡池' : '活动' }
  if (!start || !end || end <= start) return { ...base, state: 'unknown', refresh: false }

  const remaining = Math.max(0, Math.min(1, (end - now) / (end - start)))
  return {
    ...base,
    start,
    end,
    hue: Math.round(140 * remaining),
    state: now >= end ? 'ended' : now < start ? 'upcoming' : 'active',
    remaining: Math.max(0, end - now),
    refresh: now < end
  }
}

const gameTimeOptions = {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
}

export function resourceVersionHint(version, badge) {
  const { t, locale } = i18n.global
  const gameTime = new Intl.DateTimeFormat(locale.value, gameTimeOptions)
  const title = t('updates.resourceVersion', { version })
  if (badge.state === 'unknown') return `${title}\n${t('updates.noResourceTiming')}`

  const kind = t(badge.kind === '卡池' ? 'updates.gacha' : 'updates.activity')
  const event = `${kind}${badge.name ? `「${badge.name}」` : ''}`
  const end = t('updates.eventEnd', { event, time: gameTime.format(badge.end) })
  if (badge.state === 'ended') return `${title}\n${end}\n${t('updates.eventEnded', { kind })}`
  if (badge.state === 'upcoming')
    return `${title}\n${t('updates.eventStart', { kind, time: gameTime.format(badge.start) })}\n${end}`

  const minutes = Math.ceil(badge.remaining / 60000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const rest = minutes % 60
  const remaining = days
    ? t('updates.daysHours', { days, hours })
    : hours
      ? t('updates.hoursMinutes', { hours, minutes: rest })
      : t('updates.minutes', { minutes: rest })
  return `${title}\n${end}\n${t('updates.untilEnd', { remaining })}`
}
