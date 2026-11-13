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

function versionEventBadge(metadata, now) {
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

export function resourceActivityBadges(metadata, now = Date.now()) {
  const activities = Array.isArray(metadata?.activities)
    ? metadata.activities
    : [metadata?.activity]
  return activities
    .map((activity) => versionEventBadge({ activity }, now))
    .filter((badge) => badge.state === 'active' || badge.state === 'upcoming')
    .sort((left, right) => left.end - right.end || left.start - right.start)
}

export function resourceVersionBadge(metadata, now = Date.now()) {
  const badge = versionEventBadge(metadata, now)
  if (!Array.isArray(metadata?.activities)) return badge
  const activities = resourceActivityBadges(metadata, now)
  return { ...badge, activities, refresh: badge.refresh || activities.length > 0 }
}

const gameTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
})

export function resourceVersionHint(version, badge) {
  const title = `资源版本 ${version}`
  if (badge.activities) {
    const hints = badge.activities.map(resourceActivityHint)
    if (badge.kind === '卡池' && (badge.state === 'active' || badge.state === 'upcoming')) {
      hints.push(eventHint(badge))
    }
    return `${title}\n${hints.join('\n\n') || '当前资源中没有未结束的活动'}`
  }
  if (badge.state === 'unknown') return `${title}\n当前资源未提供有效的活动或卡池结束时间`
  return `${title}\n${eventHint(badge)}`
}

export function resourceActivityHint(badge) {
  return eventHint(badge, '作战关闭')
}

function eventHint(badge, ending = '结束') {
  const event = `${badge.kind}${badge.name ? `「${badge.name}」` : ''}`
  const end = `${event}${ending}：${gameTime.format(badge.end)}（北京时间）`
  if (badge.state === 'ended') return `${end}\n${badge.kind}已结束`
  if (badge.state === 'upcoming')
    return `${badge.kind}开始：${gameTime.format(badge.start)}（北京时间）\n${end}`

  const minutes = Math.ceil(badge.remaining / 60000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const rest = minutes % 60
  const remaining = days
    ? `${days} 天 ${hours} 小时`
    : hours
      ? `${hours} 小时 ${rest} 分钟`
      : `${rest} 分钟`
  return `${end}\n距${ending === '作战关闭' ? '作战关闭' : '结束'}还有 ${remaining}`
}
