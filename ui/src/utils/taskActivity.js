import { createTaskWorkflow } from '@/task-workflow/model'

const definitions = [
  ['base', '基建排班'],
  ['runorder'],
  ['drone'],
  ['reload', '制造站补货'],
  ['dorm', '宿舍安排'],
  ['fiammetta', '菲亚梅塔充能'],
  ['clue', null, 'enable_party'],
  ['workshop'],
  ['training', null, 'enable_mastery'],
  ['trust', null, 'trust_rotation_enable'],
  ['recruit', null, 'recruit_enable'],
  ['depot', null, 'maa_depot_enable'],
  ['shop', null, 'maa_mall_enable'],
  ['stage-plan', null, 'stage_plan_enable'],
  ['annihilation', '剿灭'],
  ['mission', '领取任务奖励'],
  ['long']
]

const outcomeLabels = {
  checked: '最近检查',
  completed: '最近完成',
  incomplete: '最近未完成',
  error: '最近出错',
  stopped: '已停止',
  reward_full: '奖励已满',
  agency_locked: '代理指挥已锁定'
}

const reasonLabels = {
  stopped_by_deadline: '已到本轮截止时间',
  target_reached: '已达到本轮目标',
  navigation: '关卡导航未完成',
  inventory_unconfirmed: '库存尚未确认',
  annihilation_agency_locked: '剿灭代理指挥尚未解锁',
  annihilation_reward_full: '剿灭奖励已满',
  sanity_drain: '理智不足',
  stopped_by_inventory: '已达到库存条件',
  returned: '本轮处理已返回',
  plan_checked: '已检查当前作战计划',
  cloud_sync: '云端库存同步未完成',
  scan_unconfirmed: '仓库扫描结果未确认',
  interrupted: '执行已中断',
  exception: '执行异常',
  cancelled: '执行已取消',
  restored: '来自恢复记录',
  queue_ended: 'MAA 队列已结束'
}

const timeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
})

function time(value, gameDay) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/iu.test(value)) return null
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return null
  const parts = Object.fromEntries(
    timeFormatter.formatToParts(date).map(({ type, value }) => [type, value])
  )
  const day = `${parts.year}-${parts.month}-${parts.day}`
  const clock = `${parts.hour}:${parts.minute}`
  return {
    short: day === gameDay ? clock : `${parts.month}-${parts.day} ${clock}`,
    full: `${day} ${clock}`
  }
}

const count = (value) => Number.isInteger(value) && value >= 0

function hasFacts(entry, gameDay, id) {
  return (
    ['last_checked_at', 'next_eligible_at', 'next_task_at', 'exchange_ends_at'].some((key) =>
      time(entry[key], gameDay)
    ) ||
    (count(entry.scheduled_count) && entry.scheduled_count > 0) ||
    (count(entry.blocked_count) && entry.blocked_count > 0) ||
    Boolean(time(entry.last_observation?.at, gameDay)) ||
    Boolean(
      id === 'long' &&
      entry.progress &&
      count(entry.progress.completed) &&
      count(entry.progress.total)
    )
  )
}

function isSelected(config, id, switchKey, entry, gameDay) {
  if (switchKey) return Boolean(config[switchKey])
  if (id === 'long') return config.maa_rg_enable === true || config.maa_rg_enable === 1
  if (id === 'workshop')
    return (config.workshop_manual_settings ?? config.workshop_settings ?? []).some(
      (item) => item.enabled
    )
  if (id === 'annihilation')
    return (
      Boolean(config.stage_plan_enable) &&
      (hasFacts(entry, gameDay, id) ||
        (config.maa_weekly_plan ?? []).some((day) => day.stage?.includes('Annihilation')))
    )
  if (id === 'mission') return Boolean(config.stage_plan_enable) || hasFacts(entry, gameDay, id)
  return hasFacts(entry, gameDay, id)
}

function present(entry, response, id) {
  const facts = {}
  const details = []
  const saved = response.source === 'saved'
  let tone = 'neutral'
  const addTime = (key, label) => {
    const value = time(entry[key], response.game_day)
    if (value) {
      facts[key] = `${label} ${value.short}`
      details.push(`${label} ${value.full}（北京时间）`)
    }
  }
  addTime('last_checked_at', '上次检查')
  addTime('next_eligible_at', '最早可检查')
  addTime('exchange_ends_at', '交流结束')
  const minimum = entry.queue_truncated === true ? '至少' : ''
  if (count(entry.scheduled_count) && entry.scheduled_count > 0)
    facts.scheduled_count = `待执行${minimum} ${entry.scheduled_count} 项`
  if (count(entry.blocked_count) && entry.blocked_count > 0) {
    facts.blocked_count = `暂不可执行${minimum} ${entry.blocked_count} 项`
    details.push('暂不可执行项包括待处理失败或尚未满足执行条件的任务')
  }
  addTime('next_task_at', '计划')
  const progress = id === 'long' ? entry.progress : null
  if (progress && count(progress.completed) && count(progress.total)) {
    facts.progress = `队列 ${progress.completed}/${progress.total}`
    if (progress.failed === true) {
      facts.progress += '，当前项失败待处理'
      tone = 'warning'
    }
    if (count(progress.rounds))
      facts.rounds = `当前项 ${progress.rounds}${count(progress.round_total) ? `/${progress.round_total}` : ''} 轮`
  }
  if (typeof entry.week_start === 'string' && /^\d{4}-\d{2}-\d{2}$/u.test(entry.week_start))
    details.push(`周起始日 ${entry.week_start}`)
  const observation = entry.last_observation
  const observedAt = time(observation?.at, response.game_day)
  if (observedAt) {
    const outcome = observation.outcome
    const running = outcome === 'running' && response.source === 'live'
    let label = running
      ? '运行中'
      : outcome === 'running'
        ? '已中断'
        : Object.hasOwn(outcomeLabels, outcome)
          ? outcomeLabels[outcome]
          : '结果未确认'
    if (outcome === 'reward_full' && entry.week_start) {
      const day = new Date(`${response.game_day}T00:00:00Z`)
      if (Number.isFinite(day.getTime())) {
        day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7))
        if (entry.week_start === day.toISOString().slice(0, 10)) label = '本周奖励已满'
      }
    }
    facts.observation = `${label} ${observedAt.short}`
    if (count(observation.executed_runs))
      facts.observation += `，本次 ${observation.executed_runs} 次`
    if (running) tone = 'active'
    else if (outcome === 'error' || outcome === 'incomplete') tone = 'warning'
    details.push(`最近记录 ${observedAt.full}（北京时间）：${label}`)
    if (observation.runner === 'maa') details.push('执行方式 MAA')
    if (observation.runner === 'mower') details.push('执行方式 Mower')
    if (typeof observation.stage === 'string' && observation.stage)
      details.push(`关卡 ${observation.stage}`)
    if (count(observation.executed_runs)) details.push(`实际执行 ${observation.executed_runs} 次`)
    if (typeof observation.reason === 'string' && observation.reason)
      details.push(
        Object.hasOwn(reasonLabels, observation.reason)
          ? reasonLabels[observation.reason]
          : '详细原因未确认'
      )
  }
  const priority = [
    'observation',
    'progress',
    'scheduled_count',
    'blocked_count',
    'last_checked_at',
    'next_eligible_at',
    'next_task_at',
    'exchange_ends_at',
    'rounds'
  ]
  const allFacts = priority.map((key) => facts[key]).filter(Boolean)
  const summary = allFacts.slice(0, 2).join(' · ') || '暂无执行记录'
  return {
    text: saved ? `上次记录：${summary}` : summary,
    detail: [
      saved ? '上次保存的记录' : '',
      ...details,
      ...allFacts,
      allFacts.length ? '' : summary,
      entry.queue_truncated === true ? '队列统计已截断，实际数量至少为当前显示数量' : ''
    ]
      .filter(Boolean)
      .join('；'),
    tone
  }
}

// 周期任务使用检查、计划与最近观测的事实，不转换成当天永久完成的状态。
export function getTaskActivityItems(config, response) {
  if (!['live', 'saved'].includes(response?.source)) return []
  const activities = response.activities
  if (!activities || typeof activities !== 'object' || Array.isArray(activities)) return []
  const titles = Object.fromEntries(
    createTaskWorkflow(config).editors.map(({ id, title }) => [id, title])
  )
  return definitions.flatMap(([id, fallback, switchKey]) => {
    const entry = activities[id]
    if (
      !entry ||
      typeof entry !== 'object' ||
      Array.isArray(entry) ||
      !isSelected(config, id, switchKey, entry, response.game_day)
    )
      return []
    return [{ id, title: fallback ?? titles[id], ...present(entry, response, id) }]
  })
}
