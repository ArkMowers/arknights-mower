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

// 已发布的资源以此时间表示长期开放，不作为实际作战关闭日期。
const PERMANENT_ACTIVITY_END = 4092580799

function eventBadge(event, kind, now) {
  event ||= {}
  const start = timestamp(event.time)
  const end = timestamp(event.endTime)
  const base = { name: event.name || '', kind }
  if (!start || !end || end <= start) return { ...base, state: 'unknown', refresh: false }
  if (event.endTime === PERMANENT_ACTIVITY_END) {
    return {
      ...base,
      start,
      end,
      permanent: true,
      state: now < start ? 'upcoming' : 'permanent',
      refresh: now < start
    }
  }

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
    ? [...metadata.activities]
    : [metadata?.activity]
  // 常驻玩法的关卡没有有限窗口，版本信息仍可提供已知的长期开放活动。
  if (
    metadata?.activity?.endTime === PERMANENT_ACTIVITY_END &&
    !activities.some((activity) => activity?.name === metadata.activity.name)
  ) {
    activities.push(metadata.activity)
  }
  return activities
    .map((activity) => eventBadge(activity, '活动', now))
    .filter((badge) => ['active', 'upcoming', 'permanent'].includes(badge.state))
    .sort((left, right) => left.end - right.end || left.start - right.start)
}

export function resourceVersionBadge(metadata, now = Date.now()) {
  const activities = resourceActivityBadges(metadata, now)
  const badge = activities.find((activity) => activity.state === 'active') || {
    name: '',
    kind: '活动',
    state: 'unknown'
  }
  const gacha = eventBadge(metadata?.gacha, '卡池', now)
  return {
    ...badge,
    activities,
    gacha,
    refresh: activities.some((activity) => activity.refresh) || gacha.refresh
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
  const hints = badge.activities.map(resourceActivityHint)
  if (['active', 'upcoming', 'permanent'].includes(badge.gacha.state)) {
    hints.push(eventHint(badge.gacha))
  }
  return `${title}\n${hints.join('\n\n') || '当前资源中没有未结束的活动'}`
}

export function resourceActivityHint(badge) {
  return eventHint(badge, '作战关闭')
}

function eventHint(badge, ending = '结束') {
  const event = `${badge.kind}${badge.name ? `「${badge.name}」` : ''}`
  if (badge.permanent) {
    const opening =
      badge.state === 'upcoming'
        ? `${badge.kind}开始：${gameTime.format(badge.start)}（北京时间）\n`
        : ''
    return `${opening}${event}长期开放`
  }
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
