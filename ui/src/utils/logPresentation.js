import { formatFacilityLabel } from './base_facilities.js'
import { logItemMatches } from './logItems.js'
import { LOG_DATE, LOG_LEVEL, LOG_TIME, normalizeLogSource } from './logSource.js'
import { stageLogMatches } from './logStructured.js'
import { backupChangeText, taskPresentation } from './taskPresentation.js'

const IDENTIFIER = String.raw`[\p{L}\p{N}_]`
const SUBJECT_IDENTIFIER = String.raw`[\p{L}\p{N}_·]`
const ROOM = String.raw`(?:room_\d+_\d+|(?:dormitory|gaming)_\d+)(?:_[A-Za-z0-9]+)*|central|meeting|factory|contact|train|recycle`
const LEVEL_PRIORITY = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 }
const NUMBER = String.raw`-?\d+(?:\.\d+)?`
const POINT = String.raw`\(${NUMBER},\s*${NUMBER}\)`
const PROFESSION = 'ALL|PIONEER|WARRIOR|TANK|SNIPER|CASTER|MEDIC|SUPPORT|SPECIAL'
const OPERATIONS = new RegExp(
  String.raw`^(?:打开 (?:${PROFESSION}) 筛选|关闭职业筛选|等待动画|tap:\s*${POINT}|swipe:\s*${POINT}\s*->\s*${POINT},\s*duration=\d+|swipe_ext:\s*points=\[${POINT}(?:,\s*${POINT})*\],\s*durations=\[\d+(?:,\s*\d+)*\],\s*up_wait=\d+|keyevent:\s*(?:\d+|[A-Z][A-Z0-9_]*))\s*$`,
  'u'
)

function bounded(pattern, identifier = IDENTIFIER) {
  return String.raw`(?<!${identifier})(?:${pattern})(?!${identifier})`
}

function shiftSubject(pattern) {
  return String.raw`(?<!${SUBJECT_IDENTIFIER})(?:${pattern})(?=上班|下班|休息|转为空闲)`
}

function operatorPattern(names) {
  const pattern = names.map(escapePattern).join('|')
  return `${bounded(pattern, SUBJECT_IDENTIFIER)}|${shiftSubject(pattern)}`
}

function escapePattern(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function typedEntityPattern(text) {
  const fragments = []
  let consumed = 0
  for (const match of text.matchAll(/\[\[[\p{L}_][\p{L}\p{N}_-]*:/gu)) {
    if (match.index < consumed) continue
    let cursor = match.index + 2
    let depth = 1
    while (cursor < text.length && !/[\r\n]/u.test(text[cursor])) {
      if (text.startsWith('[[', cursor)) {
        depth += 1
        cursor += 2
      } else if (text.startsWith(']]', cursor)) {
        depth -= 1
        cursor += 2
        if (!depth) break
      } else cursor += 1
    }
    consumed = cursor
    fragments.push(text.slice(match.index, cursor))
  }
  return fragments.length
    ? `(?<typedEntity>${[...new Set(fragments)].map(escapePattern).join('|')})`
    : null
}

function tokensAfter(tokens, offset) {
  const result = []
  let remaining = offset
  for (const token of tokens) {
    if (remaining >= token.text.length) {
      remaining -= token.text.length
    } else {
      result.push(remaining ? { ...token, text: token.text.slice(remaining) } : token)
      remaining = 0
    }
  }
  return result
}

function insertLogItems(tokens, text, event) {
  let offset = 0
  const spans = tokens.map((token) => {
    const span = { token, start: offset, end: offset + token.text.length }
    offset = span.end
    return span
  })
  const matches = [...logItemMatches(text, event), ...stageLogMatches(text, event)]
    .sort((a, b) => a.start - b.start)
    .filter(
      (match) =>
        !spans.some(
          (span) =>
            (span.token.type === 'backup' || span.token.text.startsWith('[[')) &&
            match.start < span.end &&
            match.end > span.start
        )
    )
  if (!matches.length) return
  const result = []
  function append(start, end) {
    for (const span of spans) {
      if (span.end <= start || span.start >= end) continue
      const fragment = span.token.text.slice(
        Math.max(0, start - span.start),
        Math.min(span.end, end) - span.start
      )
      result.push(
        fragment.length === span.token.text.length ? span.token : { type: 'text', text: fragment }
      )
    }
  }
  let cursor = 0
  for (const match of matches) {
    append(cursor, match.start)
    result.push(match)
    cursor = match.end
  }
  append(cursor, text.length)
  tokens.splice(0, tokens.length, ...result)
}

function validRecruitTags(tags, limit) {
  return (
    Array.isArray(tags) &&
    tags.length > 0 &&
    tags.length <= limit &&
    tags.every(
      (tag) =>
        typeof tag === 'string' &&
        tag.trim() &&
        tag === tag.trim() &&
        tag.length <= 32 &&
        !/[、＋；\r\n]/u.test(tag)
    ) &&
    new Set(tags).size === tags.length
  )
}

function validRecruitRarity(rarity) {
  return Number.isInteger(rarity) && rarity >= 1 && rarity <= 6
}

function recruitmentPresentation(value, text) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const labels = {
    tags: '识别标签：',
    start: text.includes('选择标签：') ? '选择标签：' : '标签：',
    rare: '发现稀有标签：'
  }
  if (typeof value.event !== 'string' || !Object.hasOwn(labels, value.event)) return null
  if (value.rarity !== null && !validRecruitRarity(value.rarity)) return null
  let tags = null
  let combinations = null
  let joined
  if (Object.hasOwn(value, 'combinations')) {
    if (
      value.event !== 'rare' ||
      Object.hasOwn(value, 'tags') ||
      !validRecruitRarity(value.rarity) ||
      !Array.isArray(value.combinations) ||
      !value.combinations.length ||
      value.combinations.length > 25 ||
      value.combinations.some(
        (choice) =>
          !choice ||
          typeof choice !== 'object' ||
          Array.isArray(choice) ||
          !validRecruitTags(choice.tags, 3) ||
          !validRecruitRarity(choice.rarity)
      )
    )
      return null
    combinations = value.combinations.map((choice) => ({
      tags: [...choice.tags],
      rarity: choice.rarity
    }))
    joined = combinations.map((choice) => choice.tags.join('＋')).join('；')
  } else {
    if (!validRecruitTags(value.tags, 5)) return null
    tags = [...value.tags]
    joined = tags.join('、')
  }
  const label = labels[value.event]
  const source = label + joined
  if (!text.includes(source) || text.indexOf(source) !== text.lastIndexOf(source)) return null
  const suffix = text.slice(text.indexOf(source) + source.length)
  if (value.event === 'start' ? !suffix.startsWith('，时长：') : suffix.length > 0) return null
  return {
    event: value.event,
    tags,
    combinations,
    label,
    joined,
    duration: value.event === 'start' ? /^，(时长：\d+小时(?:\d+分)?)$/u.exec(suffix)?.[1] : null,
    rarity: value.event === 'tags' ? null : value.rarity
  }
}

export function createLogPresenter(
  operatorNames = [],
  facilityPlan = {},
  groupNames = [],
  { structuredGroups = false, backupNames = [] } = {}
) {
  const names = [...new Set(['Current', 'Free', ...operatorNames])]
    .filter((name) => typeof name === 'string' && name.trim() && name !== '_')
    .sort((left, right) => right.length - left.length)
  const groups = [...new Set(groupNames)]
    .filter((name) => typeof name === 'string' && name.trim())
    .sort((left, right) => right.length - left.length)
  const groupPattern = groups.map(escapePattern).join('|')
  const patterns = [
    String.raw`(?<date>(?<!\d)${LOG_DATE}(?!\d))`,
    String.raw`(?<time>(?<!\d)${LOG_TIME}(?!\d|[,.]\d))`,
    `(?<level>${bounded(LOG_LEVEL)})`,
    String.raw`(?<room>(?<![A-Za-z0-9_])(?:${ROOM})(?![A-Za-z0-9_]))`,
    `(?<group>${groups.length ? `${structuredGroups ? `${bounded(groupPattern, SUBJECT_IDENTIFIER)}|` : ''}${shiftSubject(groupPattern)}` : '(?!)'})`,
    `(?<operator>${operatorPattern(names)})`
  ]
  const matcher = new RegExp(patterns.join('|'), 'gu')

  return function presentLogLine(
    line,
    structuredRoom = line?.room ?? null,
    structuredAgents = line?.agents ?? null,
    structuredGroup = line?.group ?? null,
    structuredRecruitment = line?.recruitment ?? null,
    structuredBackups = line?.backups ?? null,
    structuredEvent = line?.event ?? null
  ) {
    const {
      text,
      stamp,
      level: declaredLevel,
      msg
    } = line?.stamp === undefined ? normalizeLogSource(line) : line
    const typedEntities = typedEntityPattern(text)
    const recruitment = recruitmentPresentation(structuredRecruitment, text)
    const sourceLevel = declaredLevel === 'WARN' ? 'WARNING' : declaredLevel
    const tokens = []
    let cursor = 0
    let level = sourceLevel ?? null

    const hasStructuredRoom = structuredRoom !== null && structuredRoom !== undefined
    const hasStructuredAgents = Array.isArray(structuredAgents) && structuredAgents.length > 0
    const snapshotLabel =
      ['facility-arrangement', 'facility-observation'].includes(structuredEvent?.type) &&
      structuredEvent.summary &&
      structuredEvent.room === structuredRoom
        ? structuredEvent.label
        : null
    const aliases = hasStructuredRoom
      ? [structuredRoom, snapshotLabel ?? formatFacilityLabel(structuredRoom, facilityPlan)]
      : []
    const production = /^room_([1-3])_([1-3])$/.exec(structuredRoom ?? '')
    if (production) aliases.push(`B${production[1]}0${production[2]}`)
    const dorm = /^dormitory_([1-4])$/.exec(structuredRoom ?? '')
    if (dorm) aliases.push(`${dorm[1]}层宿舍`)
    const roomAliases = [...new Set(aliases)]
      .filter((alias) => typeof alias === 'string' && alias)
      .sort((left, right) => right.length - left.length)
    const inlineNames = [...new Set([...names, ...(hasStructuredAgents ? structuredAgents : [])])]
      .filter((name) => typeof name === 'string' && name.trim() && name !== '_')
      .sort((left, right) => right.length - left.length)
    const inlinePatterns = [...patterns]
    const historicalBackups = Array.from(
      text.matchAll(/(?:已激活|已停用|预计激活|预计停用)的副表：([^；;\r\n]+)/gu),
      (match) => match[1].split('、').map((name) => name.trim())
    ).flat()
    const backups = [
      ...new Set([
        ...backupNames,
        ...(Array.isArray(structuredBackups) ? structuredBackups.map((entry) => entry?.name) : []),
        ...historicalBackups
      ])
    ]
      .filter((name) => typeof name === 'string' && name.trim())
      .sort((left, right) => right.length - left.length)
    if (roomAliases.length)
      inlinePatterns[3] = String.raw`(?<room>(?<![A-Za-z0-9_])(?:${roomAliases.map(escapePattern).join('|')}|${ROOM})(?![A-Za-z0-9_]))`
    if (hasStructuredAgents) inlinePatterns[5] = `(?<operator>${operatorPattern(inlineNames)})`
    if (typedEntities) inlinePatterns.unshift(typedEntities)
    if (recruitment) {
      inlinePatterns.unshift(
        `(?<recruitTags>(?<=${escapePattern(recruitment.label)})${escapePattern(recruitment.joined)})`
      )
      if (recruitment.event === 'rare')
        inlinePatterns.unshift(
          `(?<recruitNotice>发现稀有标签(?=：${escapePattern(recruitment.joined)}))`
        )
      if (recruitment.duration)
        inlinePatterns.unshift(`(?<recruitDuration>(?<=，)${escapePattern(recruitment.duration)}$)`)
    }
    if (backups.length) inlinePatterns.unshift(`(?<backup>${backups.map(escapePattern).join('|')})`)
    const inlineMatcher =
      hasStructuredRoom || hasStructuredAgents || recruitment || backups.length || typedEntities
        ? new RegExp(inlinePatterns.join('|'), 'gu')
        : matcher

    for (const match of text.matchAll(inlineMatcher)) {
      if (match.index > cursor) tokens.push({ type: 'text', text: text.slice(cursor, match.index) })
      const type = Object.keys(match.groups).find((key) => match.groups[key] !== undefined)

      const token = { type, text: match[0] }
      if (type === 'typedEntity') {
        const name = /^\[\[operator:([^[\]\r\n]+)\]\]$/u.exec(token.text)?.[1]
        if (name && name !== '_' && hasStructuredAgents && structuredAgents.includes(name)) {
          token.type = 'operator'
          token.name = name
        } else token.type = 'text'
      } else if (type === 'recruitTags') {
        if (recruitment.combinations) {
          token.type = 'recruit-combinations'
          token.combinations = recruitment.combinations
        } else {
          token.type = 'recruit-tags'
          token.tags = recruitment.tags
          token.rarity = recruitment.rarity
        }
      } else if (type === 'recruitNotice') {
        token.type = 'recruit-notice'
        token.rarity = recruitment.rarity
      } else if (type === 'recruitDuration') {
        token.type = 'recruit-duration'
      }
      if (type === 'room' && roomAliases.includes(token.text)) {
        token.roomId = structuredRoom
        if (token.text === snapshotLabel) token.roomLabel = snapshotLabel
      }
      if (type === 'operator') token.name = token.text
      if (type === 'level' && !sourceLevel) {
        const candidate = token.text === 'WARN' ? 'WARNING' : token.text
        if (!level || LEVEL_PRIORITY[candidate] > LEVEL_PRIORITY[level]) level = candidate
      }
      tokens.push(token)
      cursor = match.index + match[0].length
    }
    if (cursor < text.length) tokens.push({ type: 'text', text: text.slice(cursor) })
    insertLogItems(tokens, text, structuredEvent)
    const detail =
      (!level || LEVEL_PRIORITY[level] < LEVEL_PRIORITY.WARNING) && OPERATIONS.test(msg.trimStart())

    const result = {
      text,
      tokens,
      level,
      detail,
      classification: detail ? 'operations' : 'normal',
      stamp,
      message: stamp ? tokensAfter(tokens, stamp.length) : tokens
    }

    // 将结构化字段附加到结果中
    if (structuredGroup !== null && structuredGroup !== undefined)
      result.structuredGroup = structuredGroup
    if (hasStructuredRoom) result.structuredRoom = structuredRoom
    if (hasStructuredAgents) result.structuredAgents = structuredAgents

    return result
  }
}

export function createLogRowPresenter(operatorNames, facilityPlan) {
  const groupNames = Object.values(facilityPlan).flatMap((room) =>
    (Array.isArray(room?.plans) ? room.plans : []).flatMap((slot) => [
      slot.group,
      ...(slot.group_bindings ?? []).map((binding) => binding.group)
    ])
  )
  const presentationPlan = Object.fromEntries(
    Object.entries(facilityPlan).map(([room, facility]) => [room, { name: facility?.name }])
  )
  const present = createLogPresenter(operatorNames, presentationPlan, groupNames)
  let previousLines = new Map()

  function presentLines(sourceLines) {
    const rows = []
    const nextLines = new Map()
    const occurrences = new Map()
    for (let index = 0; index < sourceLines.length; index += 1) {
      const line = sourceLines[index]
      const cacheKey = JSON.stringify([
        line.text,
        line.stamp?.length,
        line.level,
        line.room,
        line.agents,
        line.group,
        line.task,
        line.backups,
        line.recruitment,
        line.event
      ])
      let row = nextLines.get(cacheKey) ?? previousLines.get(cacheKey)
      if (!row) {
        row = present(line)
        const forecast = taskPresentation(line.task, true)
        if (forecast) {
          const actions = forecast.actions ?? []
          const forecastPresenter = createLogPresenter(
            [
              ...operatorNames,
              ...actions
                .filter((action) => action.kind === 'operator')
                .map((action) => action.subject)
            ],
            presentationPlan,
            actions.length
              ? actions.filter((action) => action.kind === 'group').map((action) => action.subject)
              : groupNames,
            {
              structuredGroups: actions.length > 0,
              backupNames: forecast.backups.map((entry) => entry.name)
            }
          )
          const titleAt =
            actions.length && forecast.title ? forecast.header.indexOf(forecast.title) : -1
          row.forecast = {
            ...forecast,
            tokens: forecastPresenter(forecast.header, line.room, line.agents).tokens,
            actionPrefix:
              titleAt >= 0
                ? forecastPresenter(forecast.header.slice(0, titleAt), line.room, line.agents)
                    .tokens
                : null,
            actionSuffix:
              titleAt >= 0
                ? forecastPresenter(
                    forecast.header.slice(titleAt + forecast.title.length),
                    line.room,
                    line.agents
                  ).tokens
                : null,
            activated: backupChangeText(forecast.backups, true),
            deactivated: backupChangeText(forecast.backups, false)
          }
        }
      }
      const occurrence = occurrences.get(line.text) ?? 0
      occurrences.set(line.text, occurrence + 1)
      const key = line.id !== null ? `id:${line.id}` : `${line.text}\u0000${occurrence}`
      nextLines.set(cacheKey, row)
      rows.push({ index, line, row, key })
    }
    previousLines = nextLines
    return rows
  }

  return { present, presentLines }
}
