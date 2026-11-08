import { formatFacilityLabel } from './base_facilities.js'

const ROOM_ID =
  /^(?:room_[1-3]_[1-3]|dormitory_[1-4](?:_low)?|gaming_[1-3]|central|meeting|factory|contact|train|recycle)$/u
const FIAMMETTA_TITLE = '菲亚梅塔充能'
const FIAMMETTA_TARGET_PREFIX = '肥鸭 充 '

function compareFacilityIds(left, right) {
  if (left === right) return 0
  return left < right ? -1 : 1
}

export function taskPresentation(value, forecast = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  if (forecast && (typeof value.header !== 'string' || !value.header.trim())) return null
  if (typeof value.title !== 'string') return null
  const rooms = value.rooms ?? []
  const targets = value.targets ?? []
  const backups = value.backups ?? []
  const actions = value.actions ?? []
  if (![rooms, targets, backups, actions].every(Array.isArray)) return null
  const room = (entry) => entry && typeof entry.id === 'string' && typeof entry.label === 'string'
  if (
    !rooms.every(
      (entry) =>
        room(entry) &&
        Array.isArray(entry.agents) &&
        entry.agents.every((name) => typeof name === 'string')
    )
  )
    return null
  if (!targets.every(room)) return null
  if (
    !backups.every(
      (entry) => entry && typeof entry.name === 'string' && typeof entry.active === 'boolean'
    )
  )
    return null
  if (
    !actions.every(
      (entry) =>
        entry &&
        ['group', 'operator'].includes(entry.kind) &&
        typeof entry.subject === 'string' &&
        entry.subject.trim() &&
        ['上班', '下班', '休息', '转为空闲'].includes(entry.action) &&
        (entry.members === undefined ||
          (Array.isArray(entry.members) && entry.members.every((name) => typeof name === 'string')))
    )
  )
    return null
  const displayHeader = forecast
    ? value.header.replace(/^休息 ((?:\d+ *(?:小时|分|秒) *)+)，至 /u, (_, duration) => {
        const units = [...duration.matchAll(/(\d+) *(小时|分|秒)/gu)]
        return `休息 ${units.map((match) => `${match[1]} ${match[2]}`).join(' ')}，至 `
      })
    : value.header
  const header =
    forecast &&
    value.title.trim() &&
    /^休息 (?:\d+ *(?:小时|分|秒) *)+，至 (?:\d{2}-\d{2} )?\d{2}:\d{2}:\d{2}$/u.test(displayHeader)
      ? `${displayHeader}，随后执行「${value.title}」`
      : displayHeader
  return {
    ...value,
    ...(forecast ? { header } : {}),
    rooms: forecast
      ? [...rooms].sort((left, right) => compareFacilityIds(left.id, right.id))
      : rooms,
    targets,
    backups,
    actions
  }
}

const PLACEHOLDERS = new Set(['', '_', 'Current', 'Free'])
const distinctNames = (names) =>
  [...new Set(names)].filter(
    (name) => typeof name === 'string' && name.trim() && !PLACEHOLDERS.has(name)
  )

export function groupActionMembers(action, facilityPlan = {}) {
  if (Array.isArray(action.members)) return distinctNames(action.members)
  return distinctNames(
    Object.values(facilityPlan).flatMap((room) =>
      (Array.isArray(room?.plans) ? room.plans : [])
        .filter((slot) =>
          [slot, ...(slot.group_bindings ?? [])].some((binding) => binding.group === action.subject)
        )
        .map((slot) => slot.agent)
    )
  )
}

export function actionSubjectRuns(actions = [], facilityPlan = {}) {
  const runs = []
  for (const action of actions) {
    let run = runs.find((entry) => entry.action === action.action)
    if (!run) {
      run = { action: action.action, subjects: [], parts: [], operators: [] }
      runs.push(run)
    }
    if (
      run.subjects.some((entry) => entry.kind === action.kind && entry.subject === action.subject)
    )
      continue
    run.subjects.push(action)
    if (action.kind === 'group') {
      run.parts.push({
        kind: 'group',
        subject: action.subject,
        members: groupActionMembers(action, facilityPlan)
      })
    } else if (action.kind === 'operator') {
      run.operators.push(action.subject)
      const last = run.parts.at(-1)
      if (last?.kind === 'operators') last.members.push(action.subject)
      else run.parts.push({ kind: 'operators', members: [action.subject] })
    }
  }
  for (const run of runs) {
    let budget = 1
    const personalParts = run.parts.filter((part) => part.kind === 'operators')
    for (const part of personalParts) {
      part.preview = part.members.slice(0, budget)
      budget -= part.preview.length
      part.overflow = part === personalParts[0] ? Math.max(0, run.operators.length - 1) : 0
      part.tail = part.overflow ? run.operators.slice(1, 3) : []
    }
    run.text = [...new Set(run.subjects.map((subject) => subject.subject))].join('、') + run.action
  }
  return runs
}

export function queueTaskTitle(task) {
  const title =
    masteryTaskTitle(task) ??
    [
      taskPresentation(task.presentation)?.title,
      task.display_name,
      typeof task.type === 'string' ? task.type : task.type?.display_value
    ].find((value) => typeof value === 'string' && value.trim()) ??
    '空任务'
  if (title === '肥鸭' || title.startsWith(FIAMMETTA_TARGET_PREFIX)) return FIAMMETTA_TITLE
  if (title === '趴体') return '线索交流'
  return title
}

export function queueTaskRoom(task, room, plan) {
  return (
    taskPresentation(task.presentation)?.rooms.find((entry) => entry.id === room)?.label ??
    formatFacilityLabel(room, plan)
  )
}

export function queueTaskTarget(task, plan) {
  const targets = taskPresentation(task.presentation)?.targets
  if (targets?.length) return targets.map((entry) => entry.label).join('、')
  const value = typeof task.meta_data === 'string' ? task.meta_data : ''
  return ROOM_ID.test(value) ? formatFacilityLabel(value, plan) : value
}

export function queueTaskText(task, plan) {
  const title = queueTaskTitle(task)
  if (title === FIAMMETTA_TITLE) return title
  const target = queueTaskTarget(task, plan)
  if (!target || title === target) return title
  const suffix = title.slice(0, -target.length)
  if (title.endsWith(target) && /[\s：:·]$/u.test(suffix)) return title
  const separated =
    taskPresentation(task.presentation)?.targets.length || ROOM_ID.test(task.meta_data ?? '')
  return title + (target ? `${separated ? ' · ' : ' '}${target}` : '')
}

export function queueTaskTokens(task, operatorNames = [], plan = {}) {
  const title = queueTaskTitle(task)
  if (masteryTaskTitle(task)) return [{ type: 'text', text: title }]
  if (title === FIAMMETTA_TITLE) {
    const tokens = [{ type: 'text', text: title }]
    const name = task.meta_data
    if (
      typeof name === 'string' &&
      name &&
      taskPresentation(task.presentation)?.title === FIAMMETTA_TARGET_PREFIX + name
    ) {
      tokens.push({ type: 'operator', text: name, name, showName: true })
    }
    return tokens
  }
  const text = Object.keys(task.plan ?? {}).length ? title : queueTaskText(task, plan)
  return taskTextTokens(text, task, operatorNames)
}

function refreshTaskTarget(task, plan) {
  const type =
    typeof task.type === 'string' ? task.type : (task.type?.value ?? task.type?.display_value)
  if (
    queueTaskTitle(task) !== '刷新跑单时间' ||
    (type && !['刷新跑单时间', '强制刷新任务时间'].includes(type)) ||
    task.recovery_observation_rooms?.length ||
    Object.keys(task.plan ?? {}).length ||
    typeof task.meta_data !== 'string' ||
    !ROOM_ID.test(task.meta_data)
  )
    return null
  const id = task.meta_data
  return {
    id,
    label:
      taskPresentation(task.presentation)?.targets.find((target) => target.id === id)?.label ??
      formatFacilityLabel(id, plan)
  }
}

function orderedQueueValue(value) {
  if (Array.isArray(value)) return value.map(orderedQueueValue)
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, orderedQueueValue(value[key])])
    )
  return value
}

function queueTaskIdentity(task) {
  const presentation = taskPresentation(task.presentation)
  return orderedQueueValue({
    time: task.time,
    type:
      typeof task.type === 'string' ? task.type : (task.type?.value ?? task.type?.display_value),
    label: queueTaskTitle(task),
    metadata: task.meta_data,
    rooms: Object.entries(task.plan ?? {}),
    presentation: presentation && {
      title: presentation.title,
      rooms: presentation.rooms,
      targets: presentation.targets,
      actions: presentation.actions,
      backups: presentation.backups
    },
    flags: [task.emergency_recovery_release, task.emergency_staffing, task.emergency_dorm]
  })
}

function refreshTaskInstant(time) {
  if (typeof time !== 'string') return null
  const match = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?$/u.exec(
    time
  )
  if (!match) return null
  const [, fraction = '', offset] = match
  // 调度时间没有偏移量时，按原有时钟读数比较，避免浏览器的夏令时合并两个时间。
  const milliseconds = Date.parse(offset ? time : `${time}Z`)
  if (!Number.isFinite(milliseconds)) return null
  return `${offset ? 'absolute' : 'local'}:${milliseconds}:${fraction.padEnd(6, '0').slice(3)}`
}

export function queueTaskRows(tasks, operatorNames = [], plan = {}, showNames = false) {
  const rows = []
  let lastRefreshKey = null
  for (const task of tasks) {
    if (showNames) {
      rows.push({ task, tasks: [task], roomEntries: Object.entries(task.plan ?? {}) })
      continue
    }
    const target = refreshTaskTarget(task, plan)
    const refreshKey = target ? refreshTaskInstant(task.time) : null
    const existing = refreshKey !== null && refreshKey === lastRefreshKey ? rows.at(-1) : null
    lastRefreshKey = refreshKey
    if (existing) {
      existing.tasks.push(task)
      existing.refreshTargets.push(target)
      continue
    }
    const presentation = taskPresentation(task.presentation)
    const row = {
      task,
      tasks: [task],
      roomEntries: Object.entries(task.plan ?? {}).sort(([left], [right]) =>
        compareFacilityIds(left, right)
      ),
      actions: presentation?.actions ?? [],
      heading: target
        ? [{ type: 'text', text: '刷新跑单时间' }]
        : queueTaskTokens(task, operatorNames, plan),
      mastery: queueMasteryDetails(task, operatorNames),
      refreshTargets: target ? [target] : []
    }
    rows.push(row)
  }
  const occurrences = new Map()
  const datedRows = rows.map((row) => {
    const identity = JSON.stringify(row.tasks.map(queueTaskIdentity))
    const occurrence = occurrences.get(identity) ?? 0
    occurrences.set(identity, occurrence + 1)
    const [date, clock] = String(row.task.time ?? '').split('T')
    const day = clock && /^\d{4}-\d{2}-\d{2}$/u.test(date) ? date : null
    return {
      ...row,
      clock: clock?.slice(0, 8) ?? date,
      day,
      key: `${identity}\u0000${occurrence}`
    }
  })
  if (!showNames) return datedRows
  return datedRows.flatMap((row) =>
    row.roomEntries.length
      ? row.roomEntries.map(([roomId, roomAgents], roomIndex) => ({
          ...row,
          roomId,
          roomAgents,
          roomIndex,
          key: roomIndex ? `${row.key}\u0000${roomIndex}` : row.key
        }))
      : [row]
  )
}

function masteryTaskTitle(task) {
  const labels = [
    task.display_name,
    task.presentation?.title,
    typeof task.type === 'string' ? task.type : task.type?.display_value
  ]
  if (labels.some((label) => ['换协助位', '自动专精换协助位'].includes(label)))
    return '自动专精换协助位'
  if (labels.some((label) => ['技能专精', '自动专精'].includes(label))) return '自动专精'
  return null
}

export function queueMasteryDetails(task, operatorNames = []) {
  const title = masteryTaskTitle(task)
  if (!title) return null
  const text = typeof task.meta_data === 'string' ? task.meta_data : ''
  const training =
    title === '自动专精换协助位' ||
    text.includes('训练室') ||
    operatorNames.some(
      (name) =>
        typeof name === 'string' &&
        name &&
        text.startsWith(name) &&
        /^[\s（(]/u.test(text.slice(name.length))
    )
  return {
    room: training ? 'train' : null,
    label: training ? '训练室' : null,
    tokens: taskTextTokens(text, task, operatorNames, true)
  }
}

function taskTextTokens(text, task, operatorNames, mastery = false) {
  const actions = taskPresentation(task.presentation)?.actions ?? []
  const subjects = new Map()
  for (const name of operatorNames) {
    if (typeof name === 'string' && name.trim()) subjects.set(name, 'operator')
  }
  for (const entry of actions) subjects.set(entry.subject, entry.kind)
  const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const names = [...subjects.keys()].sort((left, right) => right.length - left.length)
  const patterns = names.length ? [names.map(escape).join('|')] : []
  if (mastery) {
    const tier = '专[一二三123](?!\\d)'
    patterns.push(`(?:未专精\\s*→\\s*)?${tier}(?:\\s*→\\s*${tier})?`)
  }
  if (!patterns.length) return [{ type: 'text', text }]
  const matcher = new RegExp(patterns.join('|'), 'gu')
  const result = []
  let cursor = 0
  for (const match of text.matchAll(matcher)) {
    const value = match[0]
    const prefix = text.slice(0, match.index)
    const suffix = text.slice(match.index + value.length)
    const kind = subjects.get(value)
    if (
      kind &&
      !(
        (!prefix || /[\s：:、，；（「]$/u.test(prefix) || prefix.endsWith('换入')) &&
        (!suffix || /^[\s：:、，；）」。]|^(?:上班|下班|休息|转为空闲)/u.test(suffix))
      )
    )
      continue
    if (match.index > cursor) result.push({ type: 'text', text: text.slice(cursor, match.index) })
    if (kind) result.push({ type: kind, text: value, name: value })
    else {
      const levels = [...value.matchAll(/未专精|专([一二三123])/gu)].map((match) =>
        match[0] === '未专精' ? 0 : '一二三'.indexOf(match[1]) + 1 || Number(match[1])
      )
      result.push({ type: 'mastery', text: value, levels })
    }
    cursor = match.index + value.length
  }
  if (cursor < text.length) result.push({ type: 'text', text: text.slice(cursor) })
  return result
}

export function backupChangeText(backups, active) {
  return backups
    .filter((entry) => entry.active === active)
    .map((entry) => entry.name)
    .join('、')
}
