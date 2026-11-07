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
  if (badge.state === 'unknown') return `${title}\n当前资源未提供有效的活动或卡池结束时间`

  const event = `${badge.kind}${badge.name ? `「${badge.name}」` : ''}`
  const end = `${event}结束：${gameTime.format(badge.end)}（北京时间）`
  if (badge.state === 'ended') return `${title}\n${end}\n${badge.kind}已结束`
  if (badge.state === 'upcoming')
    return `${title}\n${badge.kind}开始：${gameTime.format(badge.start)}（北京时间）\n${end}`

  const minutes = Math.ceil(badge.remaining / 60000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const rest = minutes % 60
  const remaining = days
    ? `${days} 天 ${hours} 小时`
    : hours
      ? `${hours} 小时 ${rest} 分钟`
      : `${rest} 分钟`
  return `${title}\n${end}\n距结束还有 ${remaining}`
}
