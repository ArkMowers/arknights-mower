import { i18n } from '@/i18n'
import { itemDisplayName } from '@/i18n/gameNames'
const { t } = i18n.global
export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export const WEEKDAY_INDICES = Object.fromEntries(
  WEEKDAYS.map((weekday, index) => [weekday, index])
)

const weekdayMessageKeys = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday'
]

export function formatWeekday(weekday) {
  const key = weekdayMessageKeys[WEEKDAY_INDICES[weekday]]
  return key ? t(`tasks.${key}`) : weekday
}

const GAME_TIMEZONE_OFFSET_HOURS = 8
const GAME_DAY_START_HOUR = 4

/**
 * Return the weekday index used by the game (Monday = 0, Sunday = 6).
 *
 * Arknights' daily reset is at 04:00 in UTC+8, so 00:00-03:59 still
 * belongs to the previous game day. Using UTC here also keeps the result
 * independent from the browser's local timezone.
 */
export function getGameWeekdayIndex(date = new Date()) {
  const gameDayOffsetMs = (GAME_TIMEZONE_OFFSET_HOURS - GAME_DAY_START_HOUR) * 60 * 60 * 1000
  const day = new Date(date.getTime() + gameDayOffsetMs).getUTCDay()
  return day === 0 ? 6 : day - 1
}

export const STAGE_DISPLAY_NAMES = {
  get ''() {
    return t('tasks.lastStage')
  },
  get Annihilation() {
    return t('tasks.currentAnnihilation')
  },
  get 'LS-6'() {
    return t('tasks.battleRecords')
  },
  get 'CE-6'() {
    return t('tasks.lmd')
  },
  get 'AP-5'() {
    return t('tasks.purchaseCertificates')
  },
  get 'SK-5'() {
    return t('tasks.carbonStage')
  },
  get 'CA-5'() {
    return t('tasks.skillSummaries')
  },
  get 'PR-A-1'() {
    return t('tasks.medicDefender1')
  },
  get 'PR-A-2'() {
    return t('tasks.medicDefender2')
  },
  get 'PR-B-1'() {
    return t('tasks.sniperCaster1')
  },
  get 'PR-B-2'() {
    return t('tasks.sniperCaster2')
  },
  get 'PR-C-1'() {
    return t('tasks.vanguardSupporter1')
  },
  get 'PR-C-2'() {
    return t('tasks.vanguardSupporter2')
  },
  get 'PR-D-1'() {
    return t('tasks.guardSpecialist1')
  },
  get 'PR-D-2'() {
    return t('tasks.guardSpecialist2')
  },
  '1-7': '1-7'
}

export const PRESET_STAGES = Object.keys(STAGE_DISPLAY_NAMES)
export const ANNIHILATION_STAGE = 'Annihilation'
export const CHIP_STAGES = PRESET_STAGES.filter((stage) => /^PR-[ABCD]-[12]$/.test(stage))

export function promoteChipStageOrder(currentOrder = []) {
  const promoted = new Set([ANNIHILATION_STAGE, ...CHIP_STAGES])
  return [...promoted, ...currentOrder.filter((stage) => !promoted.has(stage))]
}

const stageMessageKeys = {
  '': 'lastStage',
  Annihilation: 'currentAnnihilation',
  'LS-6': 'battleRecords',
  'CE-6': 'lmd',
  'AP-5': 'purchaseCertificates',
  'SK-5': 'carbonStage',
  'CA-5': 'skillSummaries',
  'PR-A-1': 'medicDefender1',
  'PR-A-2': 'medicDefender2',
  'PR-B-1': 'sniperCaster1',
  'PR-B-2': 'sniperCaster2',
  'PR-C-1': 'vanguardSupporter1',
  'PR-C-2': 'vanguardSupporter2',
  'PR-D-1': 'guardSpecialist1',
  'PR-D-2': 'guardSpecialist2'
}
const STAGE_VALUE_MAP = Object.fromEntries([
  ['1-7', '1-7'],
  ...Object.entries(stageMessageKeys).flatMap(([value, key]) =>
    ['zh-CN', 'en-US', 'ja-JP', 'zh-TW'].map((locale) => [t(`tasks.${key}`, {}, { locale }), value])
  )
])

const ALWAYS_AVAILABLE_STAGES = new Set(['', 'Annihilation', '1-7', 'LS-6'])

const RESOURCE_STAGE_OPEN_DAYS = {
  CE: [1, 3, 5, 6],
  AP: [0, 3, 5, 6],
  SK: [0, 2, 4, 5],
  CA: [1, 2, 4, 6],
  'PR-A': [0, 3, 4, 6],
  'PR-B': [0, 1, 4, 5],
  'PR-C': [2, 3, 5, 6],
  'PR-D': [1, 2, 5, 6]
}

export function formatStageLabel(value) {
  if (value in STAGE_DISPLAY_NAMES) {
    return STAGE_DISPLAY_NAMES[value]
  }
  if (typeof value === 'string' && value.endsWith('-HARD')) {
    return t('tasks.hardStage', { stage: value.slice(0, -5) })
  }
  if (typeof value === 'string' && value.endsWith('-NORMAL')) {
    return t('tasks.normalStage', { stage: value.slice(0, -7) })
  }
  return value
}

export function normalizeCreatedStage(label) {
  const normalizedLabel = typeof label === 'string' ? label.trim() : ''
  if (normalizedLabel in STAGE_VALUE_MAP) {
    return STAGE_VALUE_MAP[normalizedLabel]
  }
  for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'zh-TW']) {
    for (const [key, suffix] of [
      ['hardStage', '-HARD'],
      ['normalStage', '-NORMAL']
    ]) {
      const [before, after] = t(`tasks.${key}`, { stage: '__STAGE__' }, { locale }).split(
        '__STAGE__'
      )
      if (normalizedLabel.startsWith(before) && normalizedLabel.endsWith(after)) {
        const stage = normalizedLabel.slice(before.length, after ? -after.length : undefined).trim()
        if (stage) return stage + suffix
      }
    }
  }
  if (normalizedLabel.endsWith('困难') || normalizedLabel.endsWith('磨难')) {
    return `${normalizedLabel.slice(0, -2)}-HARD`
  }
  if (normalizedLabel.endsWith('标准')) {
    return `${normalizedLabel.slice(0, -2)}-NORMAL`
  }
  if (/\s+hard$/i.test(normalizedLabel)) return `${normalizedLabel.replace(/\s+hard$/i, '')}-HARD`
  if (/\s+normal$/i.test(normalizedLabel))
    return `${normalizedLabel.replace(/\s+normal$/i, '')}-NORMAL`
  return normalizedLabel
}

export function createStageOption(label) {
  const value = normalizeCreatedStage(label)
  return {
    get label() {
      return formatStageLabel(value)
    },
    value
  }
}

export function splitStageInventoryLabel(label) {
  const text = typeof label === 'string' ? label : ''
  const match = text.match(/^(.*?)([（(](?:库存|庫存|Stock|在庫)[:：][^）)]*[）)])$/)
  if (!match) {
    return { stageLabel: text, inventoryLabel: '' }
  }
  return {
    stageLabel: match[1].trimEnd(),
    inventoryLabel: match[2]
  }
}

export function localizeActivityStageLabel(label) {
  if (typeof label !== 'string' || i18n.global.locale.value === 'zh-CN') return label
  return label.replace(
    /([^:,，()（）]+)[（(](?:库存|庫存|Stock|在庫)[:：]\s*(\d+)[）)]/g,
    (_match, name, count) => `${itemDisplayName(name)}(${t('tasks.inventoryCount', { count })})`
  )
}

function normalizeOption(option) {
  if (!option || typeof option.value !== 'string') {
    return null
  }
  return {
    ...option,
    get label() {
      return localizeActivityStageLabel(
        typeof option.label === 'string' && option.label
          ? option.label
          : formatStageLabel(option.value)
      )
    }
  }
}

export function dedupeStageOptions(options) {
  const seen = new Set()
  const result = []
  for (const rawOption of options) {
    const option = normalizeOption(rawOption)
    if (!option || seen.has(option.value)) {
      continue
    }
    seen.add(option.value)
    result.push(option)
  }
  return result
}

export function buildStageOptions(latestActivityOptions = []) {
  return dedupeStageOptions([
    {
      label: STAGE_DISPLAY_NAMES[ANNIHILATION_STAGE],
      value: ANNIHILATION_STAGE
    },
    ...latestActivityOptions,
    ...PRESET_STAGES.filter((value) => value !== ANNIHILATION_STAGE).map((value) => ({
      label: value ? `${STAGE_DISPLAY_NAMES[value]} (${value})` : STAGE_DISPLAY_NAMES[value],
      value
    }))
  ])
}

export function collectConfiguredStageOptions(weeklyPlan = []) {
  const options = []
  for (const plan of weeklyPlan) {
    for (const stage of Array.isArray(plan?.stage) ? plan.stage : []) {
      if (typeof stage === 'string') {
        options.push(createStageOption(stage))
      }
    }
  }
  return dedupeStageOptions(options)
}

export function buildTableStageOptions(
  latestActivityOptions = [],
  weeklyPlan = [],
  manuallyAddedOptions = []
) {
  const latestByValue = new Map(
    latestActivityOptions
      .map(normalizeOption)
      .filter(Boolean)
      .map((option) => [option.value, option])
  )
  const options = dedupeStageOptions([
    { label: formatStageLabel(ANNIHILATION_STAGE), value: ANNIHILATION_STAGE },
    ...latestActivityOptions,
    ...collectConfiguredStageOptions(weeklyPlan),
    ...manuallyAddedOptions,
    ...PRESET_STAGES.filter((value) => value !== ANNIHILATION_STAGE).map((value) => ({
      label: formatStageLabel(value),
      value
    }))
  ])
  return options.map((option) =>
    latestByValue.has(option.value) ? { ...option, ...latestByValue.get(option.value) } : option
  )
}

export function mergeTableStageOrder(options, currentOrder = [], activityValues = []) {
  const optionsByValue = new Map(options.map((option) => [option.value, option]))
  const existingOptions = []
  for (const value of currentOrder) {
    const option = optionsByValue.get(value)
    if (option) {
      existingOptions.push(option)
      optionsByValue.delete(value)
    }
  }

  const activitySet = new Set(activityValues)
  const newActivityOptions = []
  for (const value of activityValues) {
    const option = optionsByValue.get(value)
    if (option) {
      newActivityOptions.push(option)
      optionsByValue.delete(value)
    }
  }
  const newAnnihilationOption = optionsByValue.get(ANNIHILATION_STAGE)
  if (newAnnihilationOption) {
    optionsByValue.delete(ANNIHILATION_STAGE)
  }

  const ordered = [...existingOptions]
  if (newAnnihilationOption) {
    ordered.unshift(newAnnihilationOption)
  }
  const annihilationIndex = ordered.findIndex((option) => option.value === ANNIHILATION_STAGE)
  let activityInsertIndex = annihilationIndex >= 0 ? annihilationIndex + 1 : 0
  while (CHIP_STAGES.includes(ordered[activityInsertIndex]?.value)) {
    activityInsertIndex += 1
  }
  ordered.splice(activityInsertIndex, 0, ...newActivityOptions)

  for (const option of optionsByValue.values()) {
    if (!activitySet.has(option.value)) {
      ordered.push(option)
    }
  }
  return ordered
}

export function isStageAvailableOnWeekday(stage, weekday) {
  const dayIndex = WEEKDAY_INDICES[weekday]
  if (dayIndex === undefined || ALWAYS_AVAILABLE_STAGES.has(stage)) {
    return true
  }
  for (const [prefix, days] of Object.entries(RESOURCE_STAGE_OPEN_DAYS)) {
    if (stage.startsWith(prefix)) {
      return days.includes(dayIndex)
    }
  }
  return true
}

export function setStageForWeekday(weeklyPlan, weekday, stage, enabled, priorityOrder = []) {
  const plan = weeklyPlan.find((item) => item.weekday === weekday)
  if (!plan) {
    return []
  }

  const previousStages = Array.isArray(plan.stage) ? plan.stage : []
  const selected = new Set(previousStages)
  if (enabled) {
    selected.add(stage)
  } else {
    selected.delete(stage)
  }

  const ordered = []
  for (const value of priorityOrder) {
    if (selected.delete(value)) {
      ordered.push(value)
    }
  }
  for (const value of previousStages) {
    if (selected.delete(value)) {
      ordered.push(value)
    }
  }
  ordered.push(...selected)
  plan.stage = ordered
  return ordered
}

export function reorderWeeklyPlanStages(weeklyPlan, priorityOrder = []) {
  for (const plan of weeklyPlan) {
    const previousStages = Array.isArray(plan.stage) ? plan.stage : []
    const selected = new Set(previousStages)
    const ordered = []
    for (const value of priorityOrder) {
      if (selected.delete(value)) {
        ordered.push(value)
      }
    }
    for (const value of previousStages) {
      if (selected.delete(value)) {
        ordered.push(value)
      }
    }
    ordered.push(...selected)
    plan.stage = ordered
  }
}
