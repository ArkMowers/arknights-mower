function messageBody(line, row) {
  return row.stamp ? line.text.slice(row.stamp.length) : line.text.replace(/^INFO\s+/u, '')
}

export function orderCollectionCompleted(start, next) {
  if (
    start.line.group !== 'base-scheduler' ||
    next?.line.group !== start.line.group ||
    !start.line.room ||
    next.line.room !== start.line.room ||
    start.row.level !== 'INFO' ||
    next.row.level !== 'INFO' ||
    start.line.parent ||
    next.line.parent ||
    start.line.event ||
    next.line.event
  )
    return false
  const label = /^(?:贸易站 )?B[1-3]0[1-3](?=：正在收取订单$)/u.exec(
    messageBody(start.line, start.row)
  )?.[0]
  return Boolean(label && messageBody(next.line, next.row) === `${label}：已收取订单`)
}

const RECRUIT_SLOT = /^([1-4])号(?:招募|公招)位[：:]/u
const RECRUIT_ACTION =
  /^(?:准备领取干员|检查招募标签|招募获得[：:]|识别标签[：:]|发现稀有标签[：:]|开始招募(?:[，,]|$)|招募券\d+张[，,]|保留标签[，,])/u
const RECRUIT_TICKET_SKIP = /^招募券\d+张[，,]低于三星招募阈值\d+张[，,]本次跳过$/u
const RECRUIT_TERMINAL_PHASES = ['completed', 'failed', 'stopped']

function recruitmentSlotRef(value) {
  return value?.type === 'recruitment-slot' &&
    typeof value.id === 'string' &&
    value.id.trim() &&
    value.id.length <= 128 &&
    Number.isInteger(value.slot) &&
    value.slot >= 1 &&
    value.slot <= 4
    ? value
    : null
}

function recruitmentSlotEvent(value) {
  const ref = recruitmentSlotRef(value)
  return ref &&
    (ref.phase === undefined ||
      ref.phase === 'started' ||
      RECRUIT_TERMINAL_PHASES.includes(ref.phase))
    ? ref
    : null
}

export function recruitmentSlotDetails(rows, rowDates) {
  const groups = []
  const explicit = new Map()
  const ambiguous = new Set()
  const makeGroup = (slot, index, event = null) => ({
    slot,
    index,
    id: event?.id ?? null,
    phase: event?.phase ?? null,
    startPhase: event?.phase ?? null,
    indices: [],
    prefixes: new Map(),
    important: new Set(),
    operator: null,
    decision: null
  })
  for (const { line, row, index } of rows) {
    const event = recruitmentSlotEvent(line.event)
    const parent = recruitmentSlotRef(line.parent)
    const prefix = event && RECRUIT_SLOT.exec(messageBody(line, row))
    if (
      row.level !== 'INFO' ||
      !event ||
      RECRUIT_TERMINAL_PHASES.includes(event.phase) ||
      event.id !== parent?.id ||
      event.slot !== parent.slot ||
      (prefix && Number(prefix[1]) !== event.slot)
    )
      continue
    if (explicit.has(event.id)) ambiguous.add(event.id)
    explicit.set(event.id, makeGroup(event.slot, index, event))
  }
  for (const id of ambiguous) explicit.delete(id)
  groups.push(...explicit.values())

  const append = (group, index, prefix, body) => {
    group.indices.push(index)
    if (prefix) group.prefixes.set(index, prefix[0])
    if (rows[index].line.recruitment?.event === 'rare' || /^发现稀有标签[：:]/u.test(body)) {
      group.important.add(index)
    }
    const result = /^招募获得[：:]([^\r\n]+)$/u.exec(body)
    if (result) group.operator = result[1].trim()
    if (RECRUIT_TICKET_SKIP.test(body)) group.decision = '招募券不足，跳过'
    else if (/^开始招募(?:[，,]|$)/u.test(body)) group.decision = '已开始招募'
    else if (/^保留标签[，,]等待手动选择$/u.test(body)) group.decision = body
  }

  let legacy = null
  let pending = []
  const terminals = new Set()
  for (const { line, row, index } of rows) {
    const message = messageBody(line, row)
    const prefix = RECRUIT_SLOT.exec(message)
    const body = prefix ? message.slice(prefix[0].length) : message
    const parent = recruitmentSlotRef(line.parent)
    const attempt = parent ? explicit.get(parent.id) : null
    const ordinary = row.level === 'INFO' || (row.level == null && line.group === 'recruitment')
    if (!ordinary || line.parent || line.event) {
      legacy = null
      pending = []
      if (
        attempt &&
        parent.slot === attempt.slot &&
        index >= attempt.index &&
        !RECRUIT_TERMINAL_PHASES.includes(attempt.phase) &&
        (!prefix || Number(prefix[1]) === attempt.slot)
      ) {
        if (line.event?.type === 'recruitment-slot' && index !== attempt.index) {
          const event = recruitmentSlotEvent(line.event)
          if (
            row.level !== 'INFO' ||
            attempt.phase !== 'started' ||
            event?.id !== parent.id ||
            event.slot !== parent.slot ||
            !RECRUIT_TERMINAL_PHASES.includes(event.phase)
          )
            continue
          attempt.phase = event.phase
          terminals.add(index)
        }
        append(attempt, index, prefix, body)
        if (!ordinary) attempt.important.add(index)
      }
      continue
    }
    if (legacy && rowDates[index] !== rowDates[legacy.index]) {
      legacy = null
      pending = []
    }
    const slot = Number(prefix?.[1])
    const slotRecord =
      prefix && (line.group === 'recruitment' || (!line.group && RECRUIT_ACTION.test(body)))
    if (slotRecord) {
      if (!legacy || legacy.slot !== slot) {
        legacy = makeGroup(slot, index)
        groups.push(legacy)
      } else {
        for (const observation of pending) append(legacy, observation, null, '')
      }
      pending = []
      append(legacy, index, prefix, body)
      if (legacy.decision) legacy = null
      continue
    }
    const technical =
      !line.room &&
      !line.task &&
      !line.recruitment &&
      !line.backups &&
      !line.inventory &&
      (['recognition', 'device-control'].includes(line.group) ||
        (!line.group && /^Scene:?\s+-?\d+:/u.test(message)))
    if (legacy && technical) pending.push(index)
    else {
      legacy = null
      pending = []
    }
  }

  const byAnchor = new Map()
  const members = new Map()
  for (const group of groups) {
    if (!group.id && !rows[group.index].line.group && group.prefixes.size < 2) continue
    byAnchor.set(group.index, group)
    for (const index of group.indices) members.set(index, group)
  }
  return { byAnchor, members, terminals }
}

function hasFacilityRosterFields(event) {
  const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit
  return (
    text(event.id, 128) &&
    text(event.room, 128) &&
    text(event.label, 128) &&
    (event.summary === undefined ||
      (text(event.summary, 1024) && !/[\r\n]/u.test(event.summary))) &&
    Array.isArray(event.agents) &&
    event.agents.length <= 5 &&
    event.agents.every((name) => text(name, 256))
  )
}

export function facilityArrangement(event) {
  return event?.type === 'facility-arrangement' &&
    hasFacilityRosterFields(event) &&
    ['started', 'updated', 'completed', 'failed'].includes(event.phase) &&
    (event.anchor === undefined || typeof event.anchor === 'boolean') &&
    (event.phase !== 'updated' || event.anchor === false) &&
    (event.anchor === undefined || event.anchor === (event.phase === 'started'))
    ? event
    : null
}

export function facilityObservation(event) {
  return event?.type === 'facility-observation' &&
    hasFacilityRosterFields(event) &&
    typeof event.summary === 'string' &&
    ['started', 'completed', 'failed'].includes(event.phase) &&
    event.anchor === (event.phase === 'started')
    ? event
    : null
}

function moodCalculation(event) {
  const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit
  return event?.type === 'mood-calculation' &&
    text(event.id, 128) &&
    text(event.label, 128) &&
    text(event.summary, 1024) &&
    !/[\r\n]/u.test(event.summary) &&
    ['started', 'updated', 'completed', 'failed'].includes(event.phase) &&
    event.anchor === (event.phase === 'started')
    ? event
    : null
}

function depotScan(event) {
  return event?.type === 'depot-scan' &&
    typeof event.id === 'string' &&
    event.id.trim() &&
    event.id.length <= 128 &&
    typeof event.summary === 'string' &&
    event.summary.trim() &&
    event.summary.length <= 1024 &&
    !/[\r\n]/u.test(event.summary) &&
    ['started', 'updated', 'completed', 'failed', 'stopped'].includes(event.phase) &&
    event.anchor === (event.phase === 'started')
    ? event
    : null
}

const operationDetailTypes = new Set([
  'depot-scan',
  'facility-observation',
  'mood-calculation',
  'production-switch',
  'order-read'
])

export function productionSwitch(event) {
  const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit
  return event?.type === 'production-switch' &&
    text(event.id, 128) &&
    text(event.room, 128) &&
    text(event.label, 128) &&
    ['started', 'waiting', 'completed', 'failed'].includes(event.phase) &&
    typeof event.anchor === 'boolean' &&
    event.anchor === (event.phase === 'started') &&
    ['manufacture', 'trade'].includes(event.facility) &&
    text(event.product, 256) &&
    (event.previous === undefined || text(event.previous, 256)) &&
    (event.phase !== 'waiting' || event.detail !== undefined) &&
    (event.detail === undefined ||
      (['waiting', 'failed'].includes(event.phase) && text(event.detail, 2048)))
    ? event
    : null
}

export function orderRead(event) {
  const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit
  if (
    event?.type !== 'order-read' ||
    !text(event.id, 128) ||
    !['started', 'updated', 'completed', 'failed'].includes(event.phase) ||
    typeof event.anchor !== 'boolean' ||
    event.anchor !== (event.phase === 'started') ||
    typeof event.after_switch !== 'boolean' ||
    !Array.isArray(event.rooms) ||
    !event.rooms.length ||
    event.rooms.length > 32 ||
    event.rooms.some(
      (room) =>
        !room ||
        !text(room.room, 128) ||
        !text(room.label, 128) ||
        !['pending', 'read', 'paused'].includes(room.status)
    ) ||
    new Set(event.rooms.map((room) => room.room)).size !== event.rooms.length ||
    (event.detail !== undefined && (event.phase !== 'failed' || !text(event.detail, 2048)))
  )
    return null
  const pending = event.rooms.some((room) => room.status === 'pending')
  return (event.phase === 'completed' && pending) ||
    (['started', 'updated'].includes(event.phase) && !pending)
    ? null
    : event
}

export function rescueStaffing(event) {
  const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit
  if (
    event?.type !== 'rescue-staffing' ||
    !text(event.id, 128) ||
    !['queued', 'started', 'completed', 'failed'].includes(event.phase) ||
    typeof event.anchor !== 'boolean' ||
    event.anchor !== (event.phase === 'queued') ||
    !Array.isArray(event.rooms) ||
    !event.rooms.length ||
    event.rooms.length > 32 ||
    event.rooms.some(
      (room) =>
        !room ||
        !text(room.room, 128) ||
        !text(room.label, 128) ||
        !Array.isArray(room.agents) ||
        room.agents.length > 5 ||
        room.agents.some((name) => typeof name !== 'string' || name.length > 256) ||
        !['pending', 'active', 'completed', 'unconfirmed'].includes(room.status)
    ) ||
    new Set(event.rooms.map((room) => room.room)).size !== event.rooms.length ||
    (event.phase === 'completed' && event.rooms.some((room) => room.status !== 'completed')) ||
    (event.detail !== undefined && (event.phase !== 'failed' || !text(event.detail, 2048)))
  )
    return null
  return event
}

export function rescueParent(value) {
  const text = (entry) => typeof entry === 'string' && entry.trim() && entry.length <= 128
  if (value?.type !== 'rescue-staffing' || !text(value.id)) return null
  const room = value.room !== undefined,
    attempt = value.attempt !== undefined
  return room === attempt && (!room || (text(value.room) && text(value.attempt))) ? value : null
}

export function rescueGroups(lines, lifecycle) {
  const groups = new Map()
  for (const [index, event] of lifecycle.anchors) {
    if (event.type === 'rescue-staffing')
      groups.set(event.id, {
        index,
        event,
        indices: new Set([index]),
        roots: [],
        unanchored: new Map(),
        attempts: new Map()
      })
  }
  for (const [index, event] of lifecycle.anchors) {
    const parent = rescueParent(lines[index].parent)
    const group = parent && groups.get(parent.id)
    if (
      event.type !== 'facility-arrangement' ||
      !group ||
      index < group.index ||
      parent.room !== event.room ||
      parent.attempt !== event.id ||
      !group.event.rooms.some((room) => room.room === parent.room)
    )
      continue
    group.attempts.set(event.id, { index, event, room: parent.room, indices: [] })
  }
  const members = new Map()
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (line.event?.type === 'rescue-staffing') {
      const group = groups.get(line.event.id)
      if (
        group &&
        (index === group.index || lifecycle.sourceOnly.has(index)) &&
        rescueStaffing(line.event)
      )
        group.indices.add(index)
      continue
    }
    const parent = rescueParent(line.parent),
      group = parent && groups.get(parent.id)
    if (!group || index < group.index) continue
    if (parent.room === undefined) {
      group.roots.push(index)
    } else {
      if (!group.event.rooms.some((room) => room.room === parent.room)) continue
      const attempt = group.attempts.get(parent.attempt)
      if (!attempt || attempt.room !== parent.room) {
        if (!group.unanchored.has(parent.room)) group.unanchored.set(parent.room, [])
        group.unanchored.get(parent.room).push(index)
        group.indices.add(index)
        members.set(index, group.event.id)
        continue
      }
      if (
        line.event?.type === 'facility-arrangement' &&
        (line.event.id !== attempt.event.id ||
          line.event.room !== attempt.event.room ||
          line.event.label !== attempt.event.label)
      )
        continue
      attempt.indices.push(index)
    }
    group.indices.add(index)
    members.set(index, group.event.id)
  }
  return { groups, members }
}

export function lifecycleKey(event) {
  return (operationDetailTypes.has(event?.type) ||
    ['facility-arrangement', 'rescue-staffing'].includes(event?.type)) &&
    typeof event.id === 'string'
    ? JSON.stringify([event.type, event.id])
    : null
}

function collectLifecycles(lines, accept) {
  const operations = new Map()
  const sourceOnly = new Set()
  for (let index = 0; index < lines.length; index += 1) {
    const event = accept(lines[index].event)
    if (!event) continue
    const parent = lines[index].parent
    if (
      operationDetailTypes.has(event.type) &&
      parent?.type === event.type &&
      parent.id !== event.id
    )
      continue
    if (
      event.type === 'facility-arrangement' &&
      parent?.type === 'facility-arrangement' &&
      (parent.id !== event.id || parent.room !== event.room)
    )
      continue
    const key = lifecycleKey(event)
    const existing = operations.get(key)
    const production = event.type === 'production-switch'
    const summaryOnly = ['mood-calculation', 'depot-scan'].includes(event.type)
    const order = event.type === 'order-read'
    const rescue = event.type === 'rescue-staffing'
    const context = rescueParent(parent)
    const contextKey = (value) =>
      value
        ? JSON.stringify([value.type, value.id, value.room ?? null, value.attempt ?? null])
        : null
    const matches =
      existing &&
      (event.type !== 'facility-arrangement' ||
        contextKey(existing.context) === contextKey(context)) &&
      (rescue
        ? JSON.stringify(
            existing.event.rooms.map(({ room, label, agents }) => [room, label, agents])
          ) === JSON.stringify(event.rooms.map(({ room, label, agents }) => [room, label, agents]))
        : order
          ? existing.event.after_switch === event.after_switch &&
            JSON.stringify(existing.event.rooms.map(({ room, label }) => [room, label])) ===
              JSON.stringify(event.rooms.map(({ room, label }) => [room, label]))
          : (summaryOnly || existing.event.room === event.room) &&
            existing.event.label === event.label &&
            (!production ||
              (existing.event.facility === event.facility &&
                existing.event.product === event.product)))
    if (event.anchor === true && event.phase === (rescue ? 'queued' : 'started')) {
      if (matches) {
        sourceOnly.add(index)
        if (
          (production || order) &&
          ['started', 'waiting', 'updated'].includes(existing.event.phase)
        ) {
          existing.event = production
            ? {
                ...existing.event,
                ...event,
                previous: existing.event.previous ?? event.previous,
                detail: undefined
              }
            : event
          existing.detailIndex = null
          existing.lastIndex = index
        }
      } else if (!existing)
        operations.set(key, { index, event, key, context, lastIndex: index, detailIndex: null })
    } else if (
      event.anchor === false &&
      (rescue ? event.phase !== 'queued' : event.phase !== 'started') &&
      matches
    ) {
      if (rescue && existing.event.phase === 'completed' && event.phase !== 'completed') continue
      if (summaryOnly && ['completed', 'failed', 'stopped'].includes(existing.event.phase)) {
        sourceOnly.add(index)
        continue
      }
      if (
        (production || order || event.type === 'facility-arrangement') &&
        !['started', 'waiting', 'updated'].includes(existing.event.phase) &&
        ['waiting', 'updated'].includes(event.phase)
      )
        continue
      existing.event = production
        ? {
            ...existing.event,
            ...event,
            previous: existing.event.previous ?? event.previous,
            detail: event.detail
          }
        : event
      existing.detailIndex = event.detail ? index : null
      existing.lastIndex = index
      sourceOnly.add(index)
    }
  }
  const values = [...operations.values()]
  const pending = values.filter(({ event }) =>
    ['started', 'waiting', 'updated'].includes(event.phase)
  )
  return {
    anchors: new Map(values.map(({ index, event }) => [index, event])),
    details: new Map(
      values
        .filter(({ detailIndex }) => detailIndex !== null)
        .map(({ index, detailIndex }) => [index, detailIndex])
    ),
    sourceOnly,
    latestKey: pending.sort((left, right) => left.lastIndex - right.lastIndex).at(-1)?.key ?? null,
    pendingKeys: new Set(pending.map(({ key }) => key)),
    latestId: pending.at(-1)?.event.id ?? null,
    pendingIds: new Set(pending.map(({ event }) => event.id))
  }
}

export function facilityLifecycle(lines) {
  return collectLifecycles(lines, facilityArrangement)
}

export function facilityLogDetails(lines, lifecycle) {
  const attempts = new Map()
  const members = new Map()
  const idleResults = new Set()
  for (const [index, event] of lifecycle.anchors) {
    if (
      event.type === 'facility-arrangement' &&
      lines[index].event.phase === 'started' &&
      !rescueParent(lines[index].parent)
    ) {
      attempts.set(event.id, { index, event, indices: [], completed: false, idle: [] })
    }
  }
  for (let index = 0; index < lines.length; index += 1) {
    const { event, parent, room } = lines[index]
    const scoped = parent?.type === 'facility-arrangement'
    const attempt = attempts.get(scoped ? parent.id : event?.id)
    if (!attempt || rescueParent(parent)) continue
    if (index === attempt.index) {
      attempt.indices.push(index)
      continue
    }
    if (scoped && (parent.room !== attempt.event.room || (room && room !== parent.room))) continue
    if (event?.type === 'facility-arrangement') {
      if (
        index < attempt.index ||
        !lifecycle.sourceOnly.has(index) ||
        event.id !== attempt.event.id ||
        event.room !== attempt.event.room
      )
        continue
      attempt.completed = event.phase === 'completed'
    } else {
      if (!scoped) continue
      if (event?.type === 'facility-idle') {
        if (
          !attempt.completed ||
          attempt.event.phase !== 'completed' ||
          event.id !== parent.id ||
          event.room !== parent.room ||
          !Array.isArray(event.agents) ||
          !event.agents.length ||
          event.agents.length > 5 ||
          new Set(event.agents).size !== event.agents.length ||
          event.agents.some(
            (name) =>
              typeof name !== 'string' ||
              !name.trim() ||
              name.length > 256 ||
              ['', '_', 'Current', 'Free'].includes(name) ||
              attempt.event.agents.includes(name)
          )
        )
          continue
        attempt.idle = event.agents
        idleResults.add(index)
      } else if (event && !['operator-reset-idle', 'training-selection'].includes(event.type)) {
        continue
      }
    }
    attempt.indices.push(index)
    members.set(index, attempt.index)
  }
  return {
    byAnchor: new Map([...attempts.values()].map((attempt) => [attempt.index, attempt])),
    members,
    idleResults
  }
}

export function logLifecycles(lines) {
  return collectLifecycles(
    lines,
    (event) =>
      facilityArrangement(event) ??
      facilityObservation(event) ??
      moodCalculation(event) ??
      depotScan(event) ??
      productionSwitch(event) ??
      orderRead(event) ??
      rescueStaffing(event)
  )
}

export function operationLogDetails(lines, lifecycle) {
  const anchors = new Map()
  const byAnchor = new Map()
  const members = new Map()
  for (const [index, event] of lifecycle.anchors) {
    if (operationDetailTypes.has(event.type)) anchors.set(lifecycleKey(event), index)
  }
  for (let index = 0; index < lines.length; index += 1) {
    const { parent, event } = lines[index]
    if (event || !operationDetailTypes.has(parent?.type)) continue
    const anchor = anchors.get(lifecycleKey(parent))
    if (anchor === undefined || index <= anchor) continue
    if (!byAnchor.has(anchor)) byAnchor.set(anchor, [])
    byAnchor.get(anchor).push(index)
    members.set(index, anchor)
  }
  return { byAnchor, members }
}

export function trainingPositions(event) {
  const positions = event?.positions
  if (
    !['facility-arrangement', 'training-selection'].includes(event?.type) ||
    (event.type === 'facility-arrangement' && event.room !== 'train') ||
    !Array.isArray(positions) ||
    !positions.length ||
    positions.length > 2 ||
    positions.some(
      (entry) =>
        !entry ||
        typeof entry.agent !== 'string' ||
        !entry.agent.trim() ||
        entry.agent.length > 256 ||
        ![0, 1].includes(entry.index)
    ) ||
    new Set(positions.map((entry) => entry.index)).size !== positions.length
  )
    return null
  return positions
}

function validStageDrops(drops) {
  return (
    Array.isArray(drops) &&
    drops.length <= 64 &&
    Array.from(drops).every((name) => typeof name === 'string' && name.trim() && name.length <= 256)
  )
}

function stagePlanMatches(text, stages) {
  if (!Array.isArray(stages) || !stages.length || stages.length > 128) return []
  for (const stage of stages) {
    if (
      !stage ||
      typeof stage.code !== 'string' ||
      stage.code.length > 64 ||
      typeof stage.label !== 'string' ||
      !stage.label.trim() ||
      stage.label.length > 64 ||
      !validStageDrops(stage.drops)
    )
      return []
    const alias = stage.code === '' ? '上次作战' : stage.code === 'Annihilation' ? '当期剿灭' : null
    if (alias ? stage.label !== alias || stage.drops.length !== 0 : stage.label !== stage.code)
      return []
  }
  const suffix = stages.map((stage) => stage.label).join(' → ')
  if (!text.endsWith(suffix)) return []
  const matches = []
  let start = text.length - suffix.length
  for (const stage of stages) {
    if (stage.code && stage.code !== 'Annihilation')
      matches.push({
        type: 'stage',
        start,
        end: start + stage.label.length,
        text: stage.label,
        code: stage.code,
        drops: [...new Set(stage.drops)]
      })
    start += stage.label.length + 3
  }
  return matches
}

export function stageLogMatches(text, event) {
  if (event?.type === 'stage-inventory-plan') return stagePlanMatches(text, event.stages)
  if (!['stage-inventory-limit', 'stage-inventory-ratio'].includes(event?.type)) return []
  const stage = event.stage
  if (
    !stage ||
    typeof stage.code !== 'string' ||
    !stage.code.trim() ||
    stage.code.length > 64 ||
    !validStageDrops(stage.drops)
  )
    return []
  const ratio = event.type === 'stage-inventory-ratio'
  const start = ratio ? text.length - stage.code.length : text.indexOf(stage.code)
  if (ratio ? !text.endsWith(stage.code) : start < 0 || start !== text.lastIndexOf(stage.code))
    return []
  return [
    {
      type: 'stage',
      start,
      end: start + stage.code.length,
      text: stage.code,
      code: stage.code,
      drops: [...new Set(stage.drops)]
    }
  ]
}

export function idleResetName(line, row) {
  if (
    row.level !== 'INFO' ||
    line.event?.type !== 'operator-reset-idle' ||
    !Array.isArray(line.agents) ||
    line.agents.length !== 1
  )
    return null
  const name = line.agents[0]
  return typeof name === 'string' &&
    name &&
    messageBody(line, row) === `重设 [[operator:${name}]] 至空闲`
    ? name
    : null
}

export function inventoryItems(line, row) {
  let items = line.inventory?.items
  if (line.inventory == null && line.group === 'depot-recognition') {
    const [header, ...entries] = messageBody(line, row).split('\n')
    const count = /^仓库扫描：已识别([1-9]\d*)种物品$/u.exec(header)
    if (!count || Number(count[1]) !== entries.length || entries.length > 512) return null
    items = entries.map((entry) => {
      const match = /^(?<name>[^：:\r\n]{1,256})：(?<count>0|[1-9]\d*)$/u.exec(entry)
      return match ? { name: match.groups.name, count: Number(match.groups.count) } : null
    })
  }
  if (!Array.isArray(items) || !items.length || items.length > 512) return null
  if (
    items.some(
      (item) =>
        !item ||
        typeof item.name !== 'string' ||
        !item.name ||
        item.name.length > 256 ||
        !Number.isSafeInteger(item.count) ||
        item.count < 0
    )
  )
    return null
  const expected = `仓库扫描：已识别${items.length}种物品\n${items.map((item) => `${item.name}：${item.count}`).join('\n')}`
  return messageBody(line, row) === expected ? items : null
}
