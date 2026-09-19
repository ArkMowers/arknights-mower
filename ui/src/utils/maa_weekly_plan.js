export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export const WEEKDAY_INDICES = Object.fromEntries(
  WEEKDAYS.map((weekday, index) => [weekday, index])
)

export const STAGE_DISPLAY_NAMES = {
  '': '上次作战',
  Annihilation: '当期剿灭',
  'LS-6': '经验书',
  'CE-6': '龙门币',
  'AP-5': '红票',
  'SK-5': '碳本',
  'CA-5': '技能书',
  'PR-A-1': '医疗重装1',
  'PR-A-2': '医疗重装2',
  'PR-B-1': '狙击术师1',
  'PR-B-2': '狙击术师2',
  'PR-C-1': '先锋辅助1',
  'PR-C-2': '先锋辅助2',
  'PR-D-1': '近卫特种1',
  'PR-D-2': '近卫特种2',
  '1-7': '1-7'
}

export const PRESET_STAGES = Object.keys(STAGE_DISPLAY_NAMES)
export const ANNIHILATION_STAGE = 'Annihilation'

const STAGE_VALUE_MAP = Object.fromEntries(
  Object.entries(STAGE_DISPLAY_NAMES).map(([value, label]) => [label, value])
)

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
    return `${value.slice(0, -5)} 困难`
  }
  if (typeof value === 'string' && value.endsWith('-NORMAL')) {
    return `${value.slice(0, -7)} 标准`
  }
  return value
}

export function normalizeCreatedStage(label) {
  const normalizedLabel = typeof label === 'string' ? label.trim() : ''
  if (normalizedLabel in STAGE_VALUE_MAP) {
    return STAGE_VALUE_MAP[normalizedLabel]
  }
  if (normalizedLabel.endsWith('困难') || normalizedLabel.endsWith('磨难')) {
    return `${normalizedLabel.slice(0, -2)}-HARD`
  }
  if (normalizedLabel.endsWith('标准')) {
    return `${normalizedLabel.slice(0, -2)}-NORMAL`
  }
  return normalizedLabel
}

export function createStageOption(label) {
  const value = normalizeCreatedStage(label)
  return {
    label: formatStageLabel(value),
    value
  }
}

export function splitStageInventoryLabel(label) {
  const text = typeof label === 'string' ? label : ''
  const match = text.match(/^(.*?)([（(]库存[:：][^）)]*[）)])$/)
  if (!match) {
    return { stageLabel: text, inventoryLabel: '' }
  }
  return {
    stageLabel: match[1].trimEnd(),
    inventoryLabel: match[2]
  }
}

function normalizeOption(option) {
  if (!option || typeof option.value !== 'string') {
    return null
  }
  return {
    ...option,
    label:
      typeof option.label === 'string' && option.label
        ? option.label
        : formatStageLabel(option.value)
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
  ordered.splice(annihilationIndex >= 0 ? annihilationIndex + 1 : 0, 0, ...newActivityOptions)

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
