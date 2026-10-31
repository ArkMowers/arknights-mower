// Offline-preview growth API adapter.
//
// createGrowthAdapter(preview) receives the fixture from createGrowthPreview() and
// returns { handle({ method, path, query, body }) }. Handled growth-planning calls
// return { status, data }; anything else returns { unhandled: true } so the preview
// axios adapter can fall back to its generic table. State (plans, goals, crafting
// order, route settings) is cloned from the fixture and mutated in memory.

const clone = (value) => (value === undefined ? value : JSON.parse(JSON.stringify(value)))
const LEVEL_GOALS = new Set(['elite1', 'level_max', 'elite2', 'elite2_module', 'elite2_max'])
const LEVEL_GOAL_PHASE = { elite1: 1, elite2: 2, elite2_max: 2, elite2_module: 2, level_max: 0 }
const ORDINALS = ['一', '二', '三']
const PHASES = ['零', '一', '二']
const LOCKED_STATUSES = new Set(['arranging', 'training', 'waiting_collect'])
const PROFESSIONS = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种']

function queryValue(query, key) {
  if (!query) return undefined
  if (typeof query.get === 'function') {
    const value = query.get(key)
    return value === null ? undefined : value
  }
  const value = query[key]
  return Array.isArray(value) ? value[0] : value
}

function requestBody(body) {
  if (body === undefined || body === null) return {}
  if (typeof body === 'string') {
    try {
      return JSON.parse(body)
    } catch {
      return {}
    }
  }
  return body
}

function isInteger(value) {
  return typeof value === 'number' && Number.isInteger(value)
}

function keyMap(items) {
  return new Map((Array.isArray(items) ? items : []).map((item) => [item.key, item]))
}

function projectOperatorList(operator) {
  const projected = clone(operator)
  delete projected.promotion_summary
  delete projected.max_level_summary
  delete projected.module_level_summary
  delete projected.basic_skill_summary
  projected.level_goals = (projected.level_goals || []).map((goal) => {
    const entry = { ...goal }
    delete entry.summary
    return entry
  })
  projected.recommendations = (projected.recommendations || []).map((rec) => ({
    skill_index: rec.skill_index,
    skill_name: rec.skill_name,
    skill_icon_id: rec.skill_icon_id,
    current_level: rec.current_level
  }))
  projected.modules = (projected.modules || []).map((module) => ({
    id: module.id,
    name: module.name,
    type: module.type,
    current_level: module.current_level,
    max_level: module.max_level,
    elite: module.elite,
    level: module.level
  }))
  return projected
}

export function createGrowthAdapter(preview) {
  const fixture = preview || {}
  const mastery = fixture.mastery || {}
  const fullOperators = Array.isArray(mastery.operators) ? mastery.operators : []
  const operatorById = new Map()
  const operatorByName = new Map()
  for (const operator of fullOperators) {
    operatorById.set(operator.char_id, operator)
    operatorByName.set(operator.name, operator)
  }
  const operatorNames =
    Array.isArray(fixture.operatorNames) && fixture.operatorNames.length
      ? [...fixture.operatorNames]
      : fullOperators.map((operator) => operator.name)
  const initialOrder = fixture.craftingOrder || {}
  const state = {
    plans: clone(fixture.plans || []),
    planHistory: clone(fixture.planHistory || []),
    goals: clone(mastery.goals || []),
    order: (initialOrder.planning_items || []).map((item) => item.key),
    route: clone(
      fixture.route || {
        routes: [],
        defaults: {},
        settings: {},
        best_trainers: {},
        defaults_error: null
      }
    ),
    survey: clone(
      fixture.survey || {
        operators: [],
        fetched_at: null,
        stale: false,
        error: null,
        source_url: 'https://auth.yituliu.cn/open/ak-operator-statistics/result'
      }
    ),
    workshop: clone(fixture.workshop || { defaults: {}, recommendations: {}, owned_operators: [] }),
    workshopReference: clone(fixture.workshopReference || { recommendations: {} }),
    workshopStatus: clone(
      fixture.workshopStatus || {
        mode: 'automatic',
        execution: 'idle',
        project_key: null,
        project_name: null,
        recipe: null,
        generation: 0,
        pending_refresh: false,
        observed_at: null,
        blockers: []
      }
    ),
    materialSummary: clone(fixture.materialSummary || { material_summary: null, t3_summary: [] })
  }
  const sourcePlanning = keyMap(initialOrder.planning_items)
  const sourceItems = keyMap(initialOrder.items)
  const sourcePrepared = keyMap(initialOrder.prepared_items)
  const startedTargets = new Set()
  let planIdCounter =
    state.plans.reduce((max, plan) => Math.max(max, Number(plan.id) || 0), 0) + 100
  let craftingOrder = {
    items: clone(initialOrder.items || []),
    planning_items: clone(initialOrder.planning_items || []),
    prepared_items: clone(initialOrder.prepared_items || []),
    custom: Boolean(initialOrder.custom)
  }

  const ok = (data, status = 200) => ({ status, data })
  const bad = (message, status = 400) => ({ status, data: { error: message } })

  function currentMastery(operator, skillIndex) {
    const rec = (operator && operator.recommendations ? operator.recommendations : []).find(
      (entry) => entry.skill_index === skillIndex
    )
    return rec ? rec.current_level : 0
  }

  function skillNameFor(operator, skillIndex) {
    const rec = (operator && operator.recommendations ? operator.recommendations : []).find(
      (entry) => entry.skill_index === skillIndex
    )
    if (rec) return rec.skill_name
    return '技能' + (skillIndex + 1)
  }

  function makeSupportPlan(operator, skillIndex, targetLevel) {
    const current = currentMastery(operator, skillIndex)
    const stages = []
    for (let level = current + 1; level <= targetLevel; level += 1) {
      const first = level === 3 ? '逻各斯' : '艾丽妮'
      const reducer = level < targetLevel ? (level === 1 ? '逻各斯' : '艾丽妮') : null
      const efficiency = first === '逻各斯' ? 60 : 75
      const work = { 1: 8, 2: 16, 3: 24 }[level] || 8
      stages.push({
        operator: first,
        efficiency,
        level,
        swap_target: reducer,
        swap_efficiency: reducer ? 60 : 0,
        central_bonus: 5,
        mastery_swap_buffer: 10,
        configured_swap_buffer: 10,
        half_inherited: false,
        hours: Math.round((work / (1 + efficiency / 100)) * 100) / 100,
        switch_after: null,
        activate_with: null,
        next_carry: null,
        manual: false
      })
    }
    return {
      version: 1,
      stages,
      hours: Math.round(stages.reduce((sum, stage) => sum + stage.hours, 0) * 100) / 100,
      switches: 0,
      central_bonus: 5,
      current,
      target: targetLevel
    }
  }

  function waitingPlanId() {
    const waiting = state.plans.find(
      (plan) =>
        (plan.status === 'idle' || plan.status === 'failed') &&
        plan.expires_at &&
        plan.failed_reason === '材料不足'
    )
    return waiting ? waiting.id : null
  }

  function goalMeta(goal) {
    const operator = operatorById.get(goal.char_id)
    if (!operator) return null
    const moduleId = goal.module_id
    if (moduleId === 'skill7') {
      return { label: '基础技能升至 7 级', planningLabel: '基础技能升至 7 级', crafting: true }
    }
    if (LEVEL_GOALS.has(moduleId)) {
      const definition = (operator.level_goals || []).find((entry) => entry.id === moduleId)
      const phase = definition?.elite ?? LEVEL_GOAL_PHASE[moduleId]
      const level =
        definition?.level ??
        (moduleId === 'elite2_max' || moduleId === 'level_max'
          ? operator.max_level
          : moduleId === 'elite2_module'
            ? operator.module_level
            : 1)
      return {
        label: '精英化至精' + (PHASES[phase] || '零') + ' Lv.1',
        planningLabel: definition?.label || '精' + (PHASES[phase] || '零') + ' Lv.' + level,
        crafting: operator.elite < phase,
        phase,
        level
      }
    }
    const module = (operator.modules || []).find((entry) => entry.id === moduleId)
    if (!module) return null
    const targetLevel = goal.target_level || module.max_level || 1
    const label = module.name + ' · 模组 ' + targetLevel + ' 级'
    return { label, planningLabel: label, crafting: true }
  }

  function projectEntries() {
    const waiting = waitingPlanId()
    const skillProjects = []
    for (const plan of state.plans) {
      if (plan.status === 'failed' || plan.status === 'completed') continue
      const operator = operatorById.get(plan.char_id)
      if (!operator) continue
      const locked =
        LOCKED_STATUSES.has(plan.status) ||
        (plan.id === waiting && plan.status === 'idle' && Boolean(plan.expires_at))
      const ordinal = ORDINALS[Math.max(0, Math.min(2, (plan.target_level || 3) - 1))]
      const name = plan.skill_name || skillNameFor(operator, plan.skill_index)
      skillProjects.push({
        key: 'skill:' + plan.char_id + ':' + plan.skill_index,
        char_id: plan.char_id,
        kind: 'skill',
        locked,
        char_name: plan.name || operator.name,
        label: name + ' · 专' + ordinal,
        profession: operator.profession,
        plan_id: plan.id,
        crafting_required: true
      })
    }
    const goalProjects = []
    for (const goal of state.goals) {
      const operator = operatorById.get(goal.char_id)
      const meta = goalMeta(goal)
      if (!operator || !meta) continue
      if (
        LEVEL_GOALS.has(goal.module_id) &&
        (operator.elite > meta.phase ||
          (operator.elite === meta.phase && operator.level >= meta.level))
      )
        continue
      goalProjects.push({
        key: 'goal:' + goal.char_id + ':' + goal.module_id,
        char_id: goal.char_id,
        kind: 'goal',
        locked: false,
        char_name: operator.name,
        label: meta.label,
        planningLabel: meta.planningLabel,
        profession: operator.profession,
        module_id: goal.module_id,
        crafting_required: meta.crafting
      })
    }
    return { skillProjects, goalProjects, waiting }
  }

  function defaultStatus(project) {
    if (project.locked) return { status: 'active', reason: '' }
    if (!project.crafting_required) return { status: 'manual', reason: '纯等级提升，不需要合成' }
    return { status: 'ready', reason: '' }
  }

  function rebuildCraftingOrder() {
    const entries = projectEntries()
    const projects = [...entries.skillProjects, ...entries.goalProjects]
    const byKey = new Map(projects.map((project) => [project.key, project]))
    const lockedKeys = projects.filter((project) => project.locked).map((project) => project.key)
    const saved = state.order.filter((key) => byKey.has(key) && !lockedKeys.includes(key))
    const savedSet = new Set(saved)
    const remaining = projects
      .filter((project) => !project.locked && !savedSet.has(project.key))
      .map((project) => project.key)
    const ordered = [...lockedKeys, ...saved, ...remaining]
      .map((key) => byKey.get(key))
      .filter(Boolean)
    const planningItems = ordered.map((project) => {
      const template = sourcePlanning.get(project.key)
      const fallback = defaultStatus(project)
      const planned = {
        key: project.key,
        char_id: project.char_id,
        kind: project.kind,
        locked: project.locked,
        status: template && !project.locked ? template.status : fallback.status,
        reason: template && !project.locked ? template.reason : fallback.reason,
        char_name: project.char_name,
        label: project.planningLabel || project.label,
        profession: project.profession,
        crafting_required: project.crafting_required
      }
      if (project.kind === 'skill') planned.plan_id = project.plan_id
      else planned.module_id = project.module_id
      return planned
    })
    const items = []
    for (const project of ordered) {
      if (!project.crafting_required) continue
      const template = sourceItems.get(project.key)
      const planned = planningItems.find((entry) => entry.key === project.key)
      const item = {
        key: project.key,
        char_id: project.char_id,
        kind: project.kind,
        locked: project.locked,
        status: planned.status,
        reason: planned.reason,
        char_name: project.char_name,
        label: project.label,
        profession: project.profession
      }
      if (project.kind === 'skill') item.plan_id = project.plan_id
      else item.module_id = project.module_id
      if (template && !project.locked) item.shortages = template.shortages
      items.push(item)
    }
    const presentKeys = new Set(planningItems.map((item) => item.key))
    const preparedItems = [...sourcePrepared.values()]
      .filter((item) => presentKeys.has(item.key) && !item.locked)
      .map((item) => {
        const project = byKey.get(item.key) || {}
        return {
          ...item,
          label: project.planningLabel || item.label,
          char_name: project.char_name || item.char_name,
          crafting_required: project.crafting_required ?? item.crafting_required
        }
      })
    craftingOrder = {
      items,
      planning_items: planningItems,
      prepared_items: preparedItems,
      custom: state.order.length > 0
    }
    return craftingOrder
  }

  function findPlan(charId, skillIndex) {
    return state.plans.find((plan) => plan.char_id === charId && plan.skill_index === skillIndex)
  }

  function findPlanById(id) {
    return state.plans.find((plan) => plan.id === id)
  }

  function createPlanFromItem(item, options) {
    const settings = options || {}
    const name = item.name
    const charId = item.char_id || (operatorByName.get(name) || {}).char_id
    const operator = charId ? operatorById.get(charId) : null
    if (!operator || (item.name && operator.name !== item.name)) {
      return { error: 'operator not found' }
    }
    const skillIndex = item.skill_index
    const targetLevel = isInteger(item.target_level) ? item.target_level : 3
    const plan = {
      id: planIdCounter++,
      char_id: operator.char_id,
      name: operator.name,
      skill_index: skillIndex,
      skill_name: skillNameFor(operator, skillIndex),
      target_level: targetLevel,
      status: 'idle',
      priority: isInteger(item.priority) ? item.priority : 0,
      expires_at: null,
      failed_reason: null,
      support_plan: makeSupportPlan(operator, skillIndex, targetLevel),
      support_runtime: null
    }
    state.plans.push(plan)
    const result = { key: operator.name, status: 'added', id: plan.id, support_mode: 'auto' }
    if (settings.planning && operator.mastery_error) result.warning = operator.mastery_error
    return { result, plan }
  }

  function addOrReusePlan(item, options) {
    const settings = options || {}
    const name = item.name
    const charId = item.char_id || (operatorByName.get(name) || {}).char_id
    if (!charId || !operatorById.has(charId)) {
      return { key: name, status: 'error', reason: 'operator not found' }
    }
    const operator = operatorById.get(charId)
    if (item.char_id && item.name && operator.name !== item.name) {
      return { key: name, status: 'error', reason: '干员形态无效或与名称不匹配，请刷新后重试' }
    }
    if (!isInteger(item.skill_index) || item.skill_index < 0 || item.skill_index > 2) {
      return { key: name, status: 'error', reason: 'invalid skill_index' }
    }
    if (item.priority !== undefined && !isInteger(item.priority)) {
      return { key: name, status: 'error', reason: 'invalid priority' }
    }
    if (
      settings.requireTarget &&
      (!isInteger(item.target_level) || item.target_level < 1 || item.target_level > 3)
    ) {
      return { key: name, status: 'error', reason: '目标专精等级无效' }
    }
    const existing = findPlan(charId, item.skill_index)
    if (existing) {
      if (existing.status === 'failed') {
        const previous = existing.failed_reason
        existing.status = 'idle'
        existing.failed_reason = null
        existing.expires_at = null
        return {
          key: operator.name,
          status: 'existing',
          id: existing.id,
          reason: previous
            ? '此前失败：' + previous + '，已重新排入待执行'
            : '此前失败，已重新排入待执行'
        }
      }
      return {
        key: operator.name,
        status: 'existing',
        id: existing.id,
        reason: existing.status === 'idle' ? '已在计划中，已安排立即开始' : '已在训练中'
      }
    }
    const created = createPlanFromItem(
      { ...item, name: operator.name },
      { planning: settings.planning }
    )
    if (created.error) return { key: name, status: 'error', reason: created.error }
    return created.result
  }

  function handleMasteryRecommendation(query) {
    const charId = queryValue(query, 'char_id')
    const materialsFlag = queryValue(query, 'materials')
    const includeMaterials = materialsFlag === undefined || String(materialsFlag) !== '0'
    if (charId) {
      const operator = operatorById.get(charId) || operatorByName.get(charId)
      if (!operator) return ok({ operators: [], has_data: true, error: null })
      const detail = includeMaterials ? clone(operator) : projectOperatorList(operator)
      return ok({ operators: [detail], has_data: true, error: null })
    }
    const operators = includeMaterials
      ? fullOperators.map((operator) => clone(operator))
      : fullOperators.map((operator) => projectOperatorList(operator))
    return ok({
      operators,
      has_data: mastery.has_data !== undefined ? mastery.has_data : true,
      error: null,
      goals: clone(state.goals),
      statistics: clone(mastery.statistics || {}),
      personal_statistics: clone(mastery.personal_statistics || { rarities: {}, source: {} }),
      history: clone(mastery.history || [])
    })
  }

  function handleMasteryPlan(method, body) {
    if (method === 'GET') {
      return ok({ plans: clone(state.plans), history: clone(state.planHistory) })
    }
    if (method === 'POST') {
      const payload = requestBody(body)
      const results = []
      const items = Array.isArray(payload.items) ? payload.items : null
      if (items) {
        for (const item of items) {
          if (!item || typeof item !== 'object') {
            results.push({ key: '', status: 'error', reason: '计划格式错误' })
            continue
          }
          results.push(
            addOrReusePlan(item, {
              planning: payload.planning === true,
              requireTarget: payload.create_task === true
            })
          )
        }
      } else {
        for (const [name, skillIndex] of Object.entries(payload)) {
          results.push(
            addOrReusePlan(
              { name, skill_index: skillIndex },
              { planning: payload.planning === true }
            )
          )
        }
      }
      rebuildCraftingOrder()
      return ok({ results })
    }
    if (method === 'DELETE') {
      const payload = requestBody(body)
      if (!isInteger(payload.id)) return bad('invalid id: ' + String(payload.id))
      const index = state.plans.findIndex((plan) => plan.id === payload.id)
      if (index < 0) return bad('delete failed', 500)
      state.plans.splice(index, 1)
      rebuildCraftingOrder()
      return ok({ status: 'ok' })
    }
    return { unhandled: true }
  }

  function handleMasteryPlanTarget(body) {
    const payload = requestBody(body)
    if (!isInteger(payload.id)) return bad('无效的计划 ID')
    if (!isInteger(payload.target_level) || ![1, 2, 3].includes(payload.target_level)) {
      return bad('目标专精等级无效')
    }
    const plan = findPlanById(payload.id)
    if (!plan) return bad('计划不存在', 404)
    if (!['idle', 'failed'].includes(plan.status)) {
      return bad('已开始的专精计划不能修改目标')
    }
    const operator = operatorById.get(plan.char_id)
    const current = currentMastery(operator, plan.skill_index)
    if (payload.target_level <= current) return bad('目标等级必须高于当前专精等级')
    plan.target_level = payload.target_level
    plan.support_plan = makeSupportPlan(operator, plan.skill_index, payload.target_level)
    plan.support_runtime = null
    rebuildCraftingOrder()
    return ok({ status: 'ok' })
  }

  function handleMasteryPlanSupports(method, body) {
    if (method === 'GET') {
      return ok({
        operators: operatorNames.map((name) => ({ name, blocked: [] })),
        central_bonus: 5
      })
    }
    const payload = requestBody(body)
    if (!isInteger(payload.id)) return bad('无效的计划 ID')
    const plan = findPlanById(payload.id)
    if (!plan) return bad('计划不存在', 404)
    if (!Array.isArray(payload.stages)) return bad('请提交全部专精阶段的协助者')
    const planSupports = plan.support_plan || { version: 1, stages: [], central_bonus: 5 }
    const known = new Set(operatorNames)
    const stages = payload.stages.map((stage) => {
      const current = (planSupports.stages || []).find((entry) => entry.level === stage.level) || {}
      const operator = known.has(stage.operator) ? stage.operator : current.operator
      const swapTarget = known.has(stage.swap_target) ? stage.swap_target : null
      return {
        ...current,
        level: stage.level,
        operator,
        efficiency: current.efficiency || 60,
        swap_target: swapTarget,
        swap_efficiency: swapTarget ? current.swap_efficiency || 60 : 0,
        central_bonus: 5,
        mastery_swap_buffer: 10,
        configured_swap_buffer: 10,
        half_inherited: false,
        switch_after: null,
        manual: true
      }
    })
    const supportPlan = {
      ...planSupports,
      stages,
      hours: Math.round(stages.reduce((sum, stage) => sum + (stage.hours || 0), 0) * 100) / 100,
      central_bonus: 5
    }
    plan.support_plan = supportPlan
    plan.support_runtime = null
    return ok({ status: 'ok', support_plan: clone(supportPlan) })
  }

  function handleMasteryStart(body) {
    const payload = requestBody(body)
    const charId = payload.char_id
    const skillIndex = payload.skill_index
    const targetLevel = payload.target_level
    const operator = operatorById.get(charId)
    if (
      !operator ||
      !isInteger(skillIndex) ||
      ![0, 1, 2].includes(skillIndex) ||
      !isInteger(targetLevel) ||
      ![1, 2, 3].includes(targetLevel)
    ) {
      return bad('干员、技能或目标专精等级无效')
    }
    if (operator.mastery_error) return ok({ status: 'blocked', reason: operator.mastery_error })
    const existing = findPlan(charId, skillIndex)
    if (existing && LOCKED_STATUSES.has(existing.status)) {
      return ok({ status: 'active', id: existing.id, reason: '该技能已在训练流程中' })
    }
    const targetKey = charId + '_' + skillIndex
    if (startedTargets.has(targetKey)) {
      return ok({
        status: 'queued',
        id: existing ? existing.id : null,
        reason: '该专精任务已在队列中'
      })
    }
    const busy = state.plans.some(
      (plan) => plan.id !== (existing ? existing.id : null) && LOCKED_STATUSES.has(plan.status)
    )
    if (startedTargets.size > 0 || busy) {
      return ok({ status: 'blocked', reason: '训练室已有训练或待执行专精任务，请完成后再插入' })
    }
    let plan = existing
    if (!plan) {
      const created = createPlanFromItem(
        {
          char_id: charId,
          name: operator.name,
          skill_index: skillIndex,
          target_level: targetLevel
        },
        {}
      )
      plan = created.plan || null
    }
    if (!plan) return ok({ status: 'blocked', reason: '计划状态已变化，请刷新后重试' })
    startedTargets.add(targetKey)
    rebuildCraftingOrder()
    return ok({
      status: 'inserted',
      id: plan.id,
      reason: '已插入专精任务，调度器将在确认训练室空闲后执行',
      warning: null
    })
  }

  function handleGrowthPlan(method, body) {
    if (method === 'GET') return ok({ goals: clone(state.goals) })
    const payload = requestBody(body)
    const charId = payload.char_id
    const moduleId = payload.module_id
    const selected = payload.selected
    if (
      typeof selected !== 'boolean' ||
      typeof charId !== 'string' ||
      typeof moduleId !== 'string'
    ) {
      return bad('养成目标格式错误')
    }
    const operator = operatorById.get(charId)
    if (!operator) return bad('干员不在已拥有列表，请同步干员数据')
    if (LEVEL_GOALS.has(moduleId)) {
      const supported = (operator.level_goals || []).some((goal) => goal.id === moduleId)
      if (!supported) return bad('该干员不支持此等级目标')
    } else if (moduleId === 'skill7') {
      if (!operator.supports_basic_skill7) return bad('该干员不支持基础技能 7 级养成')
    } else {
      const module = (operator.modules || []).find((entry) => entry.id === moduleId)
      if (!module) return bad('该干员没有此模组')
      if (selected) {
        const target = isInteger(payload.target_level) ? payload.target_level : module.max_level
        if (!isInteger(target) || target < 1 || target > module.max_level) {
          return bad('目标模组等级无效')
        }
        if (target <= module.current_level) return bad('模组已达到所选等级')
      }
    }
    const nextGoal = { char_id: charId, module_id: moduleId }
    if (!LEVEL_GOALS.has(moduleId) && moduleId !== 'skill7' && selected) {
      const module = (operator.modules || []).find((entry) => entry.id === moduleId)
      nextGoal.target_level = isInteger(payload.target_level)
        ? payload.target_level
        : module.max_level
    }
    state.goals = state.goals.filter((goal) => {
      if (goal.char_id !== charId) return true
      if (goal.module_id === moduleId) return false
      return !(selected && LEVEL_GOALS.has(moduleId) && LEVEL_GOALS.has(goal.module_id))
    })
    if (selected) state.goals.push(nextGoal)
    rebuildCraftingOrder()
    return ok({ goals: clone(state.goals) })
  }

  function handleCraftingOrder(method, body) {
    if (method === 'GET') {
      rebuildCraftingOrder()
      return ok(clone(craftingOrder))
    }
    const projects = craftingOrder.planning_items || []
    const keys = projects.map((item) => item.key)
    if (method === 'PUT') {
      const payload = requestBody(body)
      const order = payload.order
      if (!Array.isArray(order) || order.some((key) => typeof key !== 'string')) {
        return bad('养成顺序格式错误')
      }
      if (order.length !== keys.length || new Set(order).size !== order.length) {
        return bad('养成项目已变化，请刷新养成计划后重试')
      }
      const keySet = new Set(keys)
      if (order.some((key) => !keySet.has(key))) {
        return bad('养成项目已变化，请刷新养成计划后重试')
      }
      const lockedKeys = projects.filter((item) => item.locked).map((item) => item.key)
      if (lockedKeys.some((key, index) => order[index] !== key)) {
        return bad('正在训练或等待继续的计划固定在最前，不能调整')
      }
      state.order = [...order]
    } else if (method === 'DELETE') {
      state.order = []
    } else {
      return { unhandled: true }
    }
    rebuildCraftingOrder()
    return ok(clone(craftingOrder))
  }

  function handleMasteryRoute(method, body) {
    if (method === 'GET') return ok(clone(state.route))
    const payload = requestBody(body)
    const profession = payload.profession
    if (typeof profession !== 'string' || !PROFESSIONS.includes(profession)) {
      return bad('profession is required')
    }
    let supports = payload.supports
    if (typeof supports === 'string') {
      try {
        supports = JSON.parse(supports)
      } catch {
        return bad('协助路线格式无效')
      }
    }
    if (!Array.isArray(supports)) return bad('协助路线格式无效')
    const route = {
      profession,
      supports: JSON.stringify(supports),
      is_default: 0,
      optimal: Boolean(payload.optimal),
      half_off: payload.half_off !== false
    }
    state.route.routes = (state.route.routes || []).filter(
      (entry) => entry.profession !== profession
    )
    state.route.routes.push(route)
    return ok({ status: 'ok' })
  }

  function handleRouteSettings(body) {
    const payload = requestBody(body)
    const buffers = payload.mastery_swap_buffers
    if (buffers !== undefined) {
      if (
        !buffers ||
        typeof buffers !== 'object' ||
        Array.isArray(buffers) ||
        Object.entries(buffers).some(
          ([key, value]) =>
            !['no_central', 'central', 'central_unhalved_m2'].includes(key) ||
            !isInteger(value) ||
            value < 0
        )
      ) {
        return bad('换人缓冲时间必须为非负整数')
      }
    }
    const settings = state.route.settings || {}
    if (isInteger(payload.central_bonus)) settings.central_bonus = payload.central_bonus
    if (buffers) settings.mastery_swap_buffers = { ...buffers }
    if (isInteger(payload.mastery_swap_buffer)) {
      settings.mastery_swap_buffer = payload.mastery_swap_buffer
    }
    state.route.settings = settings
    return ok({ status: 'ok' })
  }

  function handleWorkshopAutoConfig() {
    return ok({
      workshop_settings: [],
      automatic: false,
      restored: true,
      crafting_status: clone(state.workshopStatus),
      t3_summary: []
    })
  }

  function handleWorkshopRecommendations() {
    const workshop = state.workshop
    return ok({
      defaults: clone(workshop.defaults || {}),
      recommendations: clone(workshop.recommendations || {}),
      owned_operators: clone(workshop.owned_operators || []),
      blocked_operators: clone(workshop.blocked_operators || []),
      nine_colored_deer: clone(workshop.nine_colored_deer || { name: '九色鹿', owned: false }),
      min_bonus: workshop.min_bonus || 80
    })
  }

  function handle(request) {
    const config = request || {}
    const verb = String(config.method || 'GET').toUpperCase()
    let route = String(config.path || '')
    if (route.includes('?')) route = route.split('?')[0]
    if (/^https?:\/\//i.test(route)) route = route.replace(/^https?:\/\/[^/]+/i, '')
    if (route.length > 1 && route.endsWith('/')) route = route.slice(0, -1)
    const payload = requestBody(config.body)
    switch (route) {
      case '/mastery-recommendation':
        return verb === 'GET' ? handleMasteryRecommendation(config.query) : { unhandled: true }
      case '/mastery-plan':
        return handleMasteryPlan(verb, payload)
      case '/mastery-plan/target':
        return verb === 'PATCH' ? handleMasteryPlanTarget(payload) : { unhandled: true }
      case '/mastery-plan/start':
        return verb === 'POST' ? handleMasteryStart(payload) : { unhandled: true }
      case '/mastery-plan/supports':
        return verb === 'GET' || verb === 'PATCH'
          ? handleMasteryPlanSupports(verb, payload)
          : { unhandled: true }
      case '/growth-plan':
        return verb === 'GET' || verb === 'POST'
          ? handleGrowthPlan(verb, payload)
          : { unhandled: true }
      case '/mastery-t3-summary':
        return verb === 'POST' ? ok(clone(state.materialSummary)) : { unhandled: true }
      case '/growth-survey':
        return verb === 'GET' ? ok(clone(state.survey)) : { unhandled: true }
      case '/growth-crafting-order':
        return ['GET', 'PUT', 'DELETE'].includes(verb)
          ? handleCraftingOrder(verb, payload)
          : { unhandled: true }
      case '/mastery-route':
        return verb === 'GET' || verb === 'POST'
          ? handleMasteryRoute(verb, payload)
          : { unhandled: true }
      case '/mastery-route/settings':
        return verb === 'POST' ? handleRouteSettings(payload) : { unhandled: true }
      case '/cultivate-fetch':
        return verb === 'GET'
          ? ok({ success: true, message: '离线预览数据已就绪', yituliu_sync: null })
          : { unhandled: true }
      case '/workshop-status':
        return verb === 'GET' ? ok(clone(state.workshopStatus)) : { unhandled: true }
      case '/workshop-auto-config':
        return verb === 'POST' ? handleWorkshopAutoConfig(payload) : { unhandled: true }
      case '/workshop-operators/recommendations':
        return verb === 'GET' ? handleWorkshopRecommendations() : { unhandled: true }
      case '/workshop-operators/reference':
        return verb === 'GET'
          ? ok({ recommendations: clone(state.workshopReference.recommendations || {}) })
          : { unhandled: true }
      case '/growth-chip-farming':
        return verb === 'POST' ? ok({ stages: ['PR-B'], active: '默认' }) : { unhandled: true }
      case '/operator':
        return verb === 'GET' ? ok(clone(operatorNames)) : { unhandled: true }
      default:
        return { unhandled: true }
    }
  }

  rebuildCraftingOrder()
  return { handle }
}
