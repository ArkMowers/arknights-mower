// 本文件是后端 arknights_mower/utils/maa_stage_inventory.py 实际调度算法的 UI
// 即时预览镜像。修改物品解析、上限回退、比例参与条件或同分选择顺序时，需要同步
// 更新两处实现及对应测试。

export function createInventoryItemOption(label) {
  const value = typeof label === 'string' ? label.trim() : ''
  return { value, label: value, id: value, name: value }
}

function resolveItemId(value, itemAliases = {}) {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return ''
  }
  const resolved =
    itemAliases instanceof Map ? itemAliases.get(normalized) : itemAliases?.[normalized]
  return String(resolved || normalized).trim()
}

export function inventoryCount(item, inventory = {}, itemAliases = {}) {
  const itemId = String(item?.item_id || item?.value || '').trim()
  const itemName = String(item?.item_name || item?.name || '').trim()
  const candidates = new Set(
    [itemId, resolveItemId(itemId, itemAliases), resolveItemId(itemName, itemAliases)].filter(
      Boolean
    )
  )
  let count = 0
  for (const candidate of candidates) {
    const candidateCount = Number(inventory[candidate])
    if (Number.isFinite(candidateCount)) {
      count = Math.max(count, candidateCount)
    }
  }
  return count
}

export function createLimitRule(stageOption) {
  return {
    stage: stageOption.value,
    operator: 'and',
    enabled: true,
    items: (stageOption.materials || []).map((item) => ({
      item_id: item.id,
      item_name: item.name,
      limit: 0
    }))
  }
}

export function createRatioMember() {
  return { stage: '', item_id: '', item_name: '', ratio: 0 }
}

export function evaluateLimitRule(rule, inventory = {}, itemAliases = {}) {
  const conditions = (rule?.items || [])
    .filter((item) => Number(item.limit) > 0 && (item.item_id || item.item_name))
    .map((item) => {
      const count = inventoryCount(item, inventory, itemAliases)
      return {
        item,
        count,
        reached: count >= Number(item.limit)
      }
    })
  if (rule?.enabled === false || conditions.length === 0) {
    return { active: false, reached: false, conditions }
  }
  const reached =
    String(rule.operator || 'and').toLowerCase() === 'or'
      ? conditions.some((condition) => condition.reached)
      : conditions.every((condition) => condition.reached)
  return { active: true, reached, conditions }
}

export function selectRatioMember(
  rule,
  inventory = {},
  excludedStages = new Set(),
  stageOrder = [],
  itemAliases = {}
) {
  if (rule?.enabled === false) {
    return null
  }
  const stagePositions = new Map(stageOrder.map((stage, index) => [stage, index]))
  const seenStages = new Set()
  const candidates = []
  for (const member of rule?.members || []) {
    if (
      !member.stage ||
      seenStages.has(member.stage) ||
      !(member.item_id || member.item_name) ||
      Number(member.ratio) <= 0 ||
      excludedStages.has(member.stage)
    ) {
      continue
    }
    seenStages.add(member.stage)
    const count = inventoryCount(member, inventory, itemAliases)
    candidates.push({
      member,
      count,
      score: count / Number(member.ratio),
      stagePosition: stagePositions.get(member.stage) ?? Number.MAX_SAFE_INTEGER
    })
  }
  if (candidates.length < 2) {
    return null
  }
  return candidates.reduce((best, candidate) =>
    candidate.score < best.score ||
    (candidate.score === best.score && candidate.stagePosition < best.stagePosition)
      ? candidate
      : best
  )
}

export function previewInventorySelection(
  stages = [],
  limitRules = [],
  ratioRules = [],
  inventory = {},
  itemAliases = {}
) {
  const original = Array.isArray(stages) ? [...stages] : []
  const skippedStages = new Set()
  const limitSkipped = []

  for (const stage of original) {
    if (!stage || stage === 'Annihilation') {
      continue
    }
    const reached = limitRules
      .filter((rule) => rule?.stage === stage)
      .some((rule) => evaluateLimitRule(rule, inventory, itemAliases).reached)
    if (reached) {
      skippedStages.add(stage)
      if (!limitSkipped.includes(stage)) {
        limitSkipped.push(stage)
      }
    }
  }

  let kept = original.filter((stage) => !skippedStages.has(stage))
  if (original.length > 0 && kept.length === 0 && limitSkipped.length > 0) {
    return {
      stages: original,
      limitSkipped: [],
      limitFallback: true,
      ratioDecisions: []
    }
  }

  const ratioDecisions = []
  const claimedStages = new Set()
  for (const rule of ratioRules) {
    const excludedStages = new Set(claimedStages)
    for (const member of rule.members || []) {
      if (member.stage && !kept.includes(member.stage)) {
        excludedStages.add(member.stage)
      }
    }
    const selected = selectRatioMember(rule, inventory, excludedStages, original, itemAliases)
    if (!selected || !kept.includes(selected.member.stage)) {
      continue
    }
    const candidateStages = new Set(
      (rule.members || [])
        .filter(
          (member) =>
            member.stage &&
            (member.item_id || member.item_name) &&
            Number(member.ratio) > 0 &&
            kept.includes(member.stage) &&
            !claimedStages.has(member.stage)
        )
        .map((member) => member.stage)
    )
    if (candidateStages.size < 2) {
      continue
    }
    kept = kept.filter((stage) => !candidateStages.has(stage) || stage === selected.member.stage)
    for (const stage of candidateStages) {
      claimedStages.add(stage)
    }
    ratioDecisions.push({
      name: rule.name || '',
      selected: selected.member.stage,
      candidates: [...candidateStages]
    })
  }

  return {
    stages: kept,
    limitSkipped,
    limitFallback: false,
    ratioDecisions
  }
}
