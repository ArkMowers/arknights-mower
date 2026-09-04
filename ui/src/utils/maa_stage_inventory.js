export function createInventoryItemOption(label) {
  const value = typeof label === 'string' ? label.trim() : ''
  return { value, label: value, id: value, name: value }
}

export function inventoryCount(item, inventory = {}) {
  const itemId = String(item?.item_id || item?.value || '')
  const count = Number(inventory[itemId])
  return Number.isFinite(count) ? count : 0
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

export function evaluateLimitRule(rule, inventory = {}) {
  const conditions = (rule?.items || [])
    .filter((item) => Number(item.limit) > 0 && item.item_id)
    .map((item) => ({
      item,
      count: inventoryCount(item, inventory),
      reached: inventoryCount(item, inventory) >= Number(item.limit)
    }))
  if (!rule?.enabled || conditions.length === 0) {
    return { active: false, reached: false, conditions }
  }
  const reached =
    rule.operator === 'or'
      ? conditions.some((condition) => condition.reached)
      : conditions.every((condition) => condition.reached)
  return { active: true, reached, conditions }
}

export function selectRatioMember(rule, inventory = {}, excludedStages = new Set()) {
  if (!rule?.enabled) {
    return null
  }
  const candidates = (rule.members || [])
    .filter(
      (member) =>
        member.stage &&
        member.item_id &&
        Number(member.ratio) > 0 &&
        !excludedStages.has(member.stage)
    )
    .map((member, index) => ({
      member,
      index,
      count: inventoryCount(member, inventory),
      score: inventoryCount(member, inventory) / Number(member.ratio)
    }))
  if (candidates.length < 2) {
    return null
  }
  return candidates.reduce((best, candidate) => (candidate.score < best.score ? candidate : best))
}

export function previewInventorySelection(
  stages = [],
  limitRules = [],
  ratioRules = [],
  inventory = {}
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
      .some((rule) => evaluateLimitRule(rule, inventory).reached)
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
    const selected = selectRatioMember(rule, inventory, excludedStages)
    if (!selected || !kept.includes(selected.member.stage)) {
      continue
    }
    const candidateStages = new Set(
      (rule.members || [])
        .filter(
          (member) =>
            member.stage &&
            member.item_id &&
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
