import { formatFacilityLabel } from './base_facilities'
import { groupMeta } from './logGroups'
import {
  facilityLogDetails,
  lifecycleKey,
  rescueGroups,
  logLifecycles,
  orderCollectionCompleted,
  operationLogDetails,
  recruitmentSlotDetails,
  idleResetName,
  inventoryItems,
  trainingPositions
} from './logStructured'

// Only explicit operation references associate a record with an earlier summary.
export function analyzeLogTimeline(lines) {
  const lifecycle = logLifecycles(lines)
  return {
    lines,
    lifecycle,
    rescue: rescueGroups(lines, lifecycle),
    facility: facilityLogDetails(lines, lifecycle),
    operations: operationLogDetails(lines, lifecycle)
  }
}

export function buildLogTimeline(analysis, options) {
  const items = buildTimelineItems(analysis, options)
  return { items, blocks: buildTimelineBlocks(analysis, options, items) }
}

// Initial and technical sections need two lines unless there is an explicit business change.
const MIN_GROUP_LINES = 2

const isTechnicalGroup = (group) => ['recognition', 'device-control'].includes(group)
const isOrdinary = (entry) => !['WARNING', 'ERROR', 'CRITICAL'].includes(entry.row.level)

function groupLogRows(rows, rowDates, ownerOf) {
  const groups = rows.map((entry) => {
    const owner = isOrdinary(entry) ? ownerOf(entry.index) : undefined
    return rows[owner]?.line.group ?? entry.line.group
  })
  const technical = rows.map(
    (entry, index) =>
      isTechnicalGroup(groups[index]) &&
      isOrdinary(entry) &&
      !entry.line.room &&
      !entry.line.task &&
      !entry.line.recruitment &&
      !entry.line.backups
  )

  // Keep technical observations inside the same business group when both sides agree.
  const bridged = new Set()
  let businessContext = null
  for (let index = 0; index < rows.length;) {
    if (index && rowDates[index] !== rowDates[index - 1]) businessContext = null
    if (!technical[index]) {
      businessContext = isTechnicalGroup(groups[index]) ? null : groups[index]
      index += 1
      continue
    }
    let end = index + 1
    while (end < rows.length && rowDates[end] === rowDates[index] && technical[end]) end += 1
    if (businessContext && groups[end] === businessContext && rowDates[end] === rowDates[index]) {
      for (let current = index; current < end; current += 1) {
        groups[current] = businessContext
        bridged.add(current)
      }
    } else {
      businessContext = null
    }
    index = end
  }
  return { groups, technical, bridged }
}

function buildTimelineItems(
  { lifecycle, rescue, facility: details, operations: scopedDetails },
  {
    rows,
    present,
    facilityPlan,
    compact,
    concise,
    running,
    detailsVisible,
    waitDurations,
    waitingIndex,
    interruptedLifecycleKeys,
    interruptedRecruitmentIds,
    animatedLineKeys
  }
) {
  let knownDate = null
  const rowDates = rows.map((entry) => {
    knownDate = entry.row.stamp?.date ?? knownDate
    return knownDate
  })
  const facilityOwner = (index) => {
    const owner = details.members.get(index)
    return owner !== undefined && owner < index && rowDates[owner] === rowDates[index]
      ? owner
      : undefined
  }
  const {
    groups: effectiveGroups,
    technical,
    bridged: bridgedObservations
  } = groupLogRows(
    rows,
    rowDates,
    (index) => facilityOwner(index) ?? scopedDetails.members.get(index)
  )
  const recruitment = recruitmentSlotDetails(rows, rowDates)
  const recruitKey = (group) => `recruit-slot:${rows[group.index].key}`
  const operationKey = (entry) => `operation:${entry.key}`
  const recruitDetailKey = (group) =>
    group.startPhase === 'started' ? `operation:${recruitKey(group)}` : recruitKey(group)
  const latestRecruit = [...recruitment.byAnchor.values()].findLast(
    (group) => group.startPhase === 'started'
  )
  const foldableDetail = (index) =>
    rows[index]?.row.level === 'INFO' &&
    !lifecycle.sourceOnly.has(index) &&
    !details.idleResults.has(index) &&
    !recruitment.terminals.has(index)
  const detailOwner = (index) => {
    if (!foldableDetail(index) || waitingIndex === index) return undefined
    const slot = recruitment.members.get(index)
    if (slot && !slot.important.has(index)) return recruitDetailKey(slot)
    const owner = rows[facilityOwner(index) ?? scopedDetails.members.get(index)]
    return owner ? operationKey(owner) : undefined
  }
  const latestHiddenDetail = (indices, key, anchor, prefix) => {
    if (detailsVisible(key)) return null
    const index = indices?.findLast((source) => source > anchor && detailOwner(source) === key)
    if (index === undefined) return null
    return previewLog(rows[index], (tokens) => prefix(index, tokens))
  }
  const hiddenDetail = (entry) => {
    const owner = detailOwner(entry.index)
    return (
      details.idleResults.has(entry.index) ||
      (owner !== undefined && !detailsVisible(owner)) ||
      (concise &&
        rowDates[entry.index] === rowDates[entry.index + 1] &&
        orderCollectionCompleted(entry, rows[entry.index + 1]))
    )
  }
  const activeRescue = [...rescue.groups.values()]
    .filter((group) => group.event.phase === 'started')
    .sort((a, b) => Math.max(...a.indices) - Math.max(...b.indices))
    .at(-1)?.event.id
  const arrangementStarts = new Map(
    [...lifecycle.anchors].map(([index, event]) => [
      index,
      {
        ...event,
        inProgress:
          (event.type === 'rescue-staffing'
            ? event.phase === 'started' && event.id === activeRescue
            : ['started', 'waiting', 'updated'].includes(event.phase) &&
              lifecycleKey(event) === lifecycle.latestKey) &&
          !interruptedLifecycleKeys.has(lifecycleKey(event))
      }
    ])
  )
  const facilityRuns = new Map()
  const facilityLabel = (entry) => {
    if (
      !isOrdinary(entry) ||
      lifecycle.sourceOnly.has(entry.index) ||
      rescue.members.has(entry.index) ||
      facilityOwner(entry.index) !== undefined ||
      hiddenDetail(entry)
    )
      return null
    if (arrangementStarts.has(entry.index)) {
      const event = arrangementStarts.get(entry.index)
      return ['order-read', 'rescue-staffing', 'mood-calculation', 'depot-scan'].includes(
        event.type
      )
        ? null
        : event.label
    }
    if (typeof entry.line.room !== 'string') return null
    const forecast = entry.row.forecast
    if (
      forecast &&
      (forecast.rooms.length !== 1 ||
        forecast.rooms[0].id !== entry.line.room ||
        forecast.targets.some((target) => target.id !== entry.line.room))
    )
      return null
    const label = forecast?.rooms[0].label ?? formatFacilityLabel(entry.line.room, facilityPlan)
    if (label === entry.line.room || /^B[1-3]0[1-3]$/u.test(label)) return null
    return label
  }
  for (let first = 0; first < rows.length; first += 1) {
    const label = facilityLabel(rows[first])
    if (!label) continue
    const room = rows[first].line.room
    let last = first
    let count = 1
    for (let index = first + 1; index < rows.length; index += 1) {
      const entry = rows[index]
      if (!isOrdinary(entry)) break
      if (lifecycle.sourceOnly.has(index)) continue
      if (arrangementStarts.has(index)) break
      if (effectiveGroups[index] !== effectiveGroups[first]) break
      if (rowDates[first] && rowDates[index] && rowDates[first] !== rowDates[index]) break
      if (entry.line.room === room && facilityLabel(entry) === label) {
        count += 1
        last = index
        continue
      }
      const incidental = bridgedObservations.has(index)
      if (!incidental) break
    }
    if (count < 2) continue
    for (let index = first; index <= last; index += 1)
      facilityRuns.set(index, { room, label, first: index === first })
    first = last
  }
  const result = []
  const dateRuns = new Map()
  let currentDate = null
  let sectionGroup = null
  let sectionDate = null
  let cursor = 0
  while (cursor < rows.length) {
    let end = cursor + 1
    while (
      end < rows.length &&
      effectiveGroups[end] === effectiveGroups[cursor] &&
      rowDates[end] === rowDates[cursor]
    )
      end += 1
    const group = effectiveGroups[cursor]
    const businessSwitch =
      cursor > 0 &&
      group &&
      !isTechnicalGroup(group) &&
      rows[cursor].line.group === group &&
      effectiveGroups[cursor - 1] &&
      effectiveGroups[cursor - 1] !== group
    const framed =
      group !== null &&
      (end - cursor >= MIN_GROUP_LINES || businessSwitch || !isOrdinary(rows[cursor])) &&
      rows
        .slice(cursor, end)
        .some(
          (entry) =>
            recruitment.byAnchor.has(entry.index) ||
            (!lifecycle.sourceOnly.has(entry.index) &&
              !rescue.members.has(entry.index) &&
              (facilityOwner(entry.index) === undefined || !isOrdinary(entry)) &&
              !hiddenDetail(entry))
        )
    if (sectionDate !== rowDates[cursor]) sectionGroup = null
    if (framed && sectionGroup !== group) {
      // 分组用一条淡淡的隔断线标出，线上只写业务或技术来源名。
      result.push({
        key: `group:${group}:${rows[cursor].key}`,
        groupBar: group,
        meta: groupMeta(group)
      })
    }
    if (framed) {
      sectionGroup = group
      sectionDate = rowDates[cursor]
    } else if (technical.slice(cursor, end).some((observation) => !observation)) {
      // 无标题的普通技术观察不重复隔开同一段；未知来源和实际业务仍保留边界。
      sectionGroup = null
    }
    for (let index = cursor; index < end; index += 1) {
      const entry = rows[index]
      const date = entry.row.stamp?.date
      if (!compact && date && date !== currentDate) {
        const run = dateRuns.get(date) ?? 0
        dateRuns.set(date, run + 1)
        result.push({ key: `\u0001date\u0000${date}\u0000${run}`, date })
      }
      if (date) currentDate = date
      const recruit = recruitment.byAnchor.get(index)
      if (recruit) {
        const recruitActive =
          running &&
          recruit === latestRecruit &&
          recruit.phase === 'started' &&
          !interruptedRecruitmentIds.has(recruit.id)
        const key = recruitKey(recruit)
        const detailKey = recruitDetailKey(recruit)
        result.push({
          key,
          detailKey,
          recruitSlot: recruit,
          recruitActive,
          recruitStatus: recruitmentStatus(recruit, recruitActive),
          headingStamp: entry.row.stamp,
          expandable: recruit.indices.some((member) => detailOwner(member) === detailKey),
          lifecycleDetail: recruitActive
            ? latestHiddenDetail(recruit.indices, detailKey, index, (source) =>
                recruit.prefixes.get(source)
              )
            : null
        })
      }
      if (
        lifecycle.sourceOnly.has(index) ||
        recruitment.terminals.has(index) ||
        hiddenDetail(entry)
      ) {
        result.push({ key: entry.key, row: entry.row, sourceIndex: index, sourceOnly: true })
        continue
      }
      const arrangement = arrangementStarts.get(index)
      if (arrangement) {
        const detail = details.byAnchor.get(index)
        const scoped = scopedDetails.byAnchor.get(index)
        const scopedOperation = Boolean(
          scoped || lifecycleKey(entry.line.parent) === lifecycleKey(arrangement)
        )
        const detailIndices = detail?.indices ?? scoped
        const observation = arrangement.type === 'facility-observation' ? arrangement : null
        const calculation = arrangement.type === 'mood-calculation' ? arrangement : null
        const depot = arrangement.type === 'depot-scan' ? arrangement : null
        const detailKey = operationKey(entry)
        const customSummary =
          arrangement.type === 'facility-arrangement' &&
          arrangement.summary &&
          (!['started', 'updated'].includes(arrangement.phase) ||
            (arrangement.inProgress && running))
        result.push({
          key: entry.key,
          detailKey,
          row: entry.row,
          sourceIndex: index,
          facilityCopy: detail?.indices.length > 1 ? index : null,
          expandable: detailIndices?.some((source) => detailOwner(source) === detailKey),
          idleNames: concise ? detail?.idle : undefined,
          rescue: arrangement.type === 'rescue-staffing' ? arrangement : null,
          facilityHeading:
            calculation || depot
              ? null
              : ['order-read', 'rescue-staffing'].includes(arrangement.type)
                ? arrangement.rooms.map((room) => room.label).join('、')
                : arrangement.label,
          headingStamp: entry.row.stamp,
          arrangement: arrangement.type === 'facility-arrangement' ? arrangement : null,
          arrangementTokens: customSummary
            ? present(
                arrangement.summary,
                arrangement.room,
                arrangement.agents,
                null,
                null,
                null,
                arrangement
              ).tokens
            : null,
          production: arrangement.type === 'production-switch' ? arrangement : null,
          orderRead: arrangement.type === 'order-read' ? arrangement : null,
          observation,
          calculation,
          depot,
          observationTokens: observation
            ? present(
                observation.phase === 'started' && !(observation.inProgress && running)
                  ? `${observation.label}：干员心情读取尚未完成`
                  : observation.summary,
                observation.room,
                observation.agents,
                null,
                null,
                null,
                observation
              ).tokens
            : null,
          orderTokens:
            arrangement.type === 'order-read'
              ? orderReadTokens(arrangement, scopedOperation, running)
              : null,
          productionTokens:
            arrangement.type === 'production-switch'
              ? productionTokens(arrangement, scopedOperation, running, present)
              : null,
          lifecycleDetail:
            arrangement.detail && !scopedOperation
              ? {
                  key: rows[lifecycle.details.get(index)].key,
                  text: arrangement.detail,
                  tokens: present(arrangement.detail).tokens
                }
              : arrangement.inProgress && running
                ? latestHiddenDetail(detailIndices, detailKey, index, (_, tokens) =>
                    facilityPrefix(tokens, arrangement.room)
                  )
                : null
        })
        continue
      }
      const parts = stampParts(entry.row)
      const tokens = parts ? entry.row.message : entry.row.tokens
      const facility = facilityRuns.get(index)
      if (facility?.first)
        result.push({
          key: `facility:${entry.key}`,
          facilityHeading: facility.label,
          headingStamp: entry.row.stamp
        })
      const recruitGroup = recruitment.members.get(index)
      const forecastTokens = entry.row.forecast?.actionPrefix ?? entry.row.forecast?.tokens
      const owner = facilityOwner(index)
      const facilityRoom = rows[owner]?.line.event?.room ?? facility?.room
      const roomPrefix = facilityRoom
        ? facilityPrefix(forecastTokens ?? tokens, facilityRoom)
        : null
      const hiddenPrefix = recruitGroup?.prefixes.get(index) ?? roomPrefix
      const sourceTokens = hiddenPrefix ? skipTokenText(tokens, hiddenPrefix.length) : tokens
      const displayTokens = expandDisplayTokens(sourceTokens)
      result.push({
        key: entry.key,
        row: entry.row,
        sourceIndex: index,
        detailOwner: detailOwner(index),
        inventory: inventoryItems(entry.line, entry.row),
        resetName: rescue.members.has(index) ? null : idleResetName(entry.line, entry.row),
        resetContext: JSON.stringify([entry.line.group, entry.line.room, rowDates[index], owner]),
        parts,
        hiddenPrefix,
        facility: facility?.room ?? null,
        nested:
          Boolean(trainingPositions(entry.line.event)) ||
          Boolean(facilityRoom || recruitGroup || scopedDetails.members.has(index)),
        displayTokens,
        forecastTokens:
          roomPrefix && forecastTokens
            ? skipTokenText(forecastTokens, roomPrefix.length)
            : forecastTokens,
        waitMs: waitDurations.get(index) ?? null,
        sceneWaiting: waitingIndex === index,
        animate: animatedLineKeys.has(entry.key)
      })
    }
    cursor = end
  }
  for (let first = 0; first < result.length; first += 1) {
    const entry = result[first]
    if (!entry.resetName) continue
    let end = first + 1
    while (result[end]?.resetName && result[end].resetContext === entry.resetContext) end += 1
    if (end - first < 2) continue
    const records = result.slice(first, end)
    result.splice(first, end - first, {
      key: `reset:${entry.key}`,
      row: entry.row,
      resetRows: records,
      nested: records.every((record) => record.nested),
      detailOwner: records.every((record) => record.detailOwner === entry.detailOwner)
        ? entry.detailOwner
        : undefined,
      source: records.map((record) => record.row.text).join('\n')
    })
  }
  // 日期分隔属于整天，排在分组名之前，避免分组名像是贴在日期上面。
  for (let index = 0; index < result.length - 1; index += 1) {
    if (result[index].groupBar && result[index + 1]?.date) {
      const dateItem = result[index + 1]
      result.splice(index, 2, dateItem, result[index])
      index += 1
    }
  }
  return result
}

function buildTimelineBlocks(
  { lines, rescue },
  { rows, present, running, detailsVisible, waitDurations, waitingIndex },
  items
) {
  if (!rescue.groups.size) return items.map((item) => ({ key: item.key, items: [item] }))
  const byIndex = new Map(
    items.filter((item) => item.sourceIndex !== undefined).map((item) => [item.sourceIndex, item])
  )
  const plain = (index) => {
    const item = byIndex.get(index)
    if (!item) return null
    if (!item.sourceOnly && !item.arrangement && !item.rescue) return item
    const parts = stampParts(item.row)
    return {
      key: item.key,
      row: item.row,
      sourceIndex: index,
      parts,
      inventory: inventoryItems(lines[index], item.row),
      displayTokens: expandDisplayTokens(parts ? item.row.message : item.row.tokens),
      forecastTokens: item.row.forecast?.actionPrefix ?? item.row.forecast?.tokens,
      waitMs: waitDurations.get(index) ?? null,
      sceneWaiting: waitingIndex === index
    }
  }
  const mirror = (item, history = false) =>
    item && {
      ...item,
      key: `rescue-display:${item.key}`,
      sourceKey: item.key,
      mirror: true,
      history,
      nested: !item.arrangement,
      animate: false
    }
  const result = []
  for (const item of items) {
    if (item.rescue) {
      const group = rescue.groups.get(item.rescue.id)
      const content = []
      for (const index of group.indices) {
        const event = lines[index].event
        if (event?.type !== 'rescue-staffing' || event.phase !== 'failed') continue
        const record = plain(index)
        if (!record) continue
        const detail = event.detail
          ? {
              ...record,
              row: { ...record.row, forecast: null },
              displayTokens: present(event.detail).tokens
            }
          : record
        content.push(mirror(detail, item.rescue.phase !== 'failed'))
      }
      for (const room of item.rescue.rooms) {
        content.push({
          key: `rescue-room:${item.rescue.id}:${room.room}`,
          rescueRoom: room,
          staticParentKey: item.key,
          sourceIndex: item.sourceIndex
        })
        const attempts = [...group.attempts.values()]
          .filter((attempt) => attempt.room === room.room)
          .sort((a, b) => a.index - b.index)
        const current = attempts.at(-1)
        if (current) {
          const entry = byIndex.get(current.index)
          content.push(
            mirror({
              ...entry,
              arrangement: {
                ...entry.arrangement,
                inProgress: item.rescue.inProgress && entry.arrangement.inProgress
              }
            })
          )
        }
        for (const attempt of attempts) {
          if (attempt !== current)
            content.push(
              mirror(
                {
                  ...byIndex.get(attempt.index),
                  arrangement: { ...attempt.event, inProgress: false }
                },
                true
              )
            )
          for (const index of attempt.indices) {
            if (index === attempt.index) continue
            const record = byIndex.get(index)
            if (record?.sourceOnly) {
              if (['WARNING', 'WARN', 'ERROR', 'CRITICAL'].includes(record.row.level))
                content.push(mirror(plain(index), attempt !== current))
            } else content.push(mirror(record, attempt !== current))
          }
        }
        for (const index of group.unanchored.get(room.room) ?? [])
          content.push(mirror(plain(index)))
      }
      for (const index of group.roots) content.push(mirror(plain(index)))
      const expanded = detailsVisible(item.detailKey)
      const previewIndex =
        !expanded && item.rescue.inProgress && running
          ? [...group.indices].reverse().find((index) => {
              const record = byIndex.get(index)
              return (
                index > item.sourceIndex &&
                record?.row.level === 'INFO' &&
                !lines[index].event &&
                waitingIndex !== index
              )
            })
          : undefined
      const preview =
        previewIndex === undefined
          ? []
          : [{ key: `${item.key}:preview`, lifecycleDetail: previewLog(plain(previewIndex)) }]
      const sources = [...group.indices]
        .sort((a, b) => a - b)
        .map((index) => ({ key: rows[index].key, index, text: rows[index].line.text }))
      result.push({
        key: `rescue:${item.rescue.id}`,
        parent: item,
        items: [
          ...preview,
          ...content.filter(
            (record) =>
              record &&
              (expanded ||
                record.sceneWaiting ||
                ['WARNING', 'WARN', 'ERROR', 'CRITICAL'].includes(record.row?.level))
          )
        ],
        sources
      })
    } else if (rescue.members.has(item.sourceIndex)) {
      result.push({
        key: item.key,
        items: [{ key: item.key, row: item.row, sourceIndex: item.sourceIndex, sourceOnly: true }]
      })
    } else result.push({ key: item.key, items: [item] })
  }
  return result
}

function orderReadTokens(event, scoped, running) {
  const names = (rooms) =>
    rooms.flatMap((room, index) => [
      ...(index ? [{ type: 'text', text: '、' }] : []),
      { type: 'order-room', text: room.label }
    ])
  const prefix = event.after_switch ? [{ type: 'text', text: '产物切换和驻员安排已完成，' }] : []
  if (event.rooms.some((room) => room.status !== 'pending') || event.phase === 'failed') {
    const read = event.rooms.filter((room) => room.status === 'read')
    const paused = event.rooms.filter((room) => room.status === 'paused')
    const pending = event.rooms.filter((room) => room.status === 'pending')
    const outcomes = []
    if (read.length)
      outcomes.push([
        { type: 'text', text: '已读取' },
        ...names(read),
        { type: 'text', text: ' 的订单倒计时' }
      ])
    if (paused.length) outcomes.push([...names(paused), { type: 'text', text: ' 的订单暂停获取' }])
    if (pending.length)
      outcomes.push([
        { type: 'text', text: event.inProgress && running ? '正在读取' : '尚未完成读取' },
        ...names(pending),
        { type: 'text', text: ' 的订单倒计时' }
      ])
    return [
      ...prefix,
      ...outcomes.flatMap((tokens, index) => [
        ...(index ? [{ type: 'text', text: '；' }] : []),
        ...tokens
      ]),
      ...(scoped && event.phase === 'failed' && event.detail
        ? [{ type: 'text', text: `。原因：${event.detail}` }]
        : [])
    ]
  }
  return [
    ...prefix,
    { type: 'text', text: event.inProgress && running ? '正在读取' : '尚未完成读取' },
    ...names(event.rooms),
    { type: 'text', text: ' 的订单倒计时' }
  ]
}

function productionTokens(event, scoped, running, present) {
  const room = { type: 'production-room', text: event.label }
  const target = present(event.product).tokens
  const subject = event.facility === 'trade' ? '订单类型' : '产物'
  if (event.phase === 'completed')
    return [
      { type: 'text', text: '已将' },
      room,
      { type: 'text', text: ` 的${subject}切换为` },
      ...target
    ]
  if (!event.inProgress || !running)
    return [
      { type: 'text', text: '尚未完成将' },
      room,
      { type: 'text', text: ` 的${subject}切换为` },
      ...target,
      ...(scoped && event.phase === 'failed' && event.detail
        ? [{ type: 'text', text: `。原因：${event.detail}` }]
        : [])
    ]
  const waiting = scoped && event.phase === 'waiting'
  return event.previous
    ? [
        { type: 'text', text: waiting ? '等待切换' : '正在切换' },
        room,
        { type: 'text', text: ` 的${subject} ` },
        ...present(event.previous).tokens,
        { type: 'text', text: ' → ' },
        ...target
      ]
    : [
        { type: 'text', text: waiting ? '等待将' : '正在将' },
        room,
        { type: 'text', text: ` 的${subject}切换为` },
        ...target
      ]
}

function skipTokenText(tokens, length) {
  const result = []
  for (const token of tokens) {
    if (length >= token.text.length) length -= token.text.length
    else {
      result.push(length ? { ...token, text: token.text.slice(length) } : token)
      length = 0
    }
  }
  return result
}

function expandDisplayTokens(tokens) {
  return tokens.some((token) => token.displayTokens)
    ? tokens.flatMap((token) => token.displayTokens ?? [token])
    : tokens
}

function facilityPrefix(tokens, room) {
  return tokens[0]?.type === 'room' &&
    (tokens[0].roomId ?? tokens[0].text) === room &&
    /^[：:]/u.test(tokens[1]?.text ?? '')
    ? tokens[0].text + tokens[1].text[0]
    : null
}

// 行首拆成隐藏与可见片段，依次拼接仍是原文。
function stampParts(row) {
  const stamp = row.stamp
  if (!stamp) return null
  const level = stamp.level ?? ''
  const quiet = !level || level === 'INFO'
  return {
    head: (stamp.date ?? '') + stamp.dateGap,
    time: stamp.time,
    tail: stamp.fraction + stamp.levelGap,
    quiet: quiet ? level + stamp.gap : '',
    quietGap: quiet ? stamp.gap : '',
    label: quiet ? '' : level,
    gap: quiet ? '' : stamp.gap
  }
}

function previewLog(entry, prefix = () => null) {
  const tokens = entry.row.forecast?.tokens ?? entry.row.message
  const newline = tokens.findIndex((token) => /[\r\n]/u.test(token.text))
  const firstLine =
    newline < 0
      ? tokens
      : [
          ...tokens.slice(0, newline),
          { ...tokens[newline], text: tokens[newline].text.split(/[\r\n]/u, 1)[0] }
        ]
  const hiddenPrefix = prefix(firstLine)
  return {
    key: entry.key,
    row: entry.row,
    parts: stampParts(entry.row),
    tokens: expandDisplayTokens(
      hiddenPrefix ? skipTokenText(firstLine, hiddenPrefix.length) : firstLine
    ),
    preview: true
  }
}

function recruitmentStatus(slot, active) {
  if (slot.phase === 'started') return active ? '检查中' : '检查结果未确认'
  if (slot.phase === 'completed' && !slot.operator && !slot.decision) return '检查完成'
  if (slot.phase === 'failed') return '检查未完成'
  if (slot.phase === 'stopped') return '已停止检查'
  return null
}
