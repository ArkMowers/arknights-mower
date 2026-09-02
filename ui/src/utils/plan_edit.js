// 排班表里的干员名单 conf 字段（主表 conf 与副表 conf 同构；ling_xi 是枚举不是名单）
export const OPERATOR_CONF_FIELDS = [
  'rest_in_full',
  'exhaust_require',
  'workaholic',
  'resting_priority',
  'refresh_trading',
  'refresh_drained',
  'free_blacklist',
  'ope_resting_priority'
]

// ---- 以下三个复用于 PlanEditor.vue 的设施拖拽换位（swapSubstrings / swapTask / updateTrigger） ----

function swapSubstrings(str, source, target) {
  const placeholder = '__PLACEHOLDER__'
  let newStr = str.replace(new RegExp(source, 'g'), placeholder)
  newStr = newStr.replace(new RegExp(target, 'g'), source)
  newStr = newStr.replace(new RegExp(placeholder, 'g'), target)
  return newStr
}

function swapTask(tasks, source, target) {
  if (tasks) {
    const placeholder = '__PLACEHOLDER__'
    const has = (key) => Object.prototype.hasOwnProperty.call(tasks, key)
    if (has(source)) {
      tasks[placeholder] = tasks[source]
      delete tasks[source]
    }
    if (has(target)) {
      tasks[source] = tasks[target]
      delete tasks[target]
    }
    if (has(placeholder)) {
      tasks[target] = tasks[placeholder]
      delete tasks[placeholder]
    }
  }
}

function updateTrigger(trigger, source, target) {
  for (const key in trigger) {
    if (key === 'left' || key === 'right') {
      if (typeof trigger[key] === 'string') {
        trigger[key] = swapSubstrings(trigger[key], source, target)
      } else if (typeof trigger[key] === 'object' && trigger[key] !== null) {
        updateTrigger(trigger[key], source, target)
      }
    }
  }
}

// ---- 一键替换干员：把「排班里的 A」替换成「新干员 B」（单向；B 不在排班里，去重守卫在调用方） ----

function replace_in_list(list, source, target) {
  if (!Array.isArray(list)) return
  for (let i = 0; i < list.length; i++) {
    if (list[i] === source) list[i] = target
  }
}

export function replace_plan_operators(plan, source, target) {
  if (!plan) return
  for (const key in plan) {
    const facility = plan[key]
    if (!facility || !Array.isArray(facility.plans)) continue
    for (const item of facility.plans) {
      if (item.agent === source) item.agent = target
      replace_in_list(item.replacement, source, target)
    }
  }
}

export function replace_conf_operators(conf, source, target) {
  if (!conf) return
  for (const field of OPERATOR_CONF_FIELDS) {
    replace_in_list(conf[field], source, target)
  }
}

export function replace_trigger_operators(trigger, source, target) {
  if (!trigger) return
  // 触发表达式里的干员名恒为 op_data.operators['NAME'] 单引号字面量（TriggerString.vue），
  // 按带引号边界替换——避免裸子串替换误伤更长干员名（阿 ⊂ 阿米娅/阿消 等）
  const quoted_source = `['${source}']`
  const quoted_target = `['${target}']`
  for (const key of ['left', 'right']) {
    const value = trigger[key]
    if (typeof value === 'string') {
      trigger[key] = value.split(quoted_source).join(quoted_target)
    } else if (value && typeof value === 'object') {
      replace_trigger_operators(value, source, target)
    }
  }
}

export function replace_task_operators(task, source, target) {
  if (!task) return
  for (const room in task) {
    replace_in_list(task[room], source, target)
  }
}

export function apply_operator_replace({ main_plan, main_conf, backup_plans }, source, target) {
  replace_plan_operators(main_plan, source, target)
  replace_conf_operators(main_conf, source, target)
  for (const backup of backup_plans || []) {
    replace_plan_operators(backup.plan, source, target)
    replace_conf_operators(backup.conf, source, target)
    replace_trigger_operators(backup.trigger, source, target)
    replace_task_operators(backup.task, source, target)
  }
}

// 排班里出现过的全部干员（agent / replacement / conf 名单 / 副表 task 数组），
// 用于「被替换侧」下拉选项与「目标干员已在排班」去重守卫
export function collect_plan_operators({ main_plan, main_conf, backup_plans }) {
  const seen = new Set()
  const add = (name) => {
    if (name) seen.add(name)
  }
  const collect_plan = (plan) => {
    if (!plan) return
    for (const key in plan) {
      const facility = plan[key]
      if (!facility || !Array.isArray(facility.plans)) continue
      for (const item of facility.plans) {
        add(item.agent)
        for (const r of item.replacement || []) add(r)
      }
    }
  }
  const collect_conf = (conf) => {
    if (!conf) return
    for (const field of OPERATOR_CONF_FIELDS) {
      for (const name of conf[field] || []) add(name)
    }
  }
  const collect_task = (task) => {
    if (!task) return
    for (const room in task) {
      for (const name of task[room] || []) add(name)
    }
  }
  collect_plan(main_plan)
  collect_conf(main_conf)
  for (const backup of backup_plans || []) {
    collect_plan(backup.plan)
    collect_conf(backup.conf)
    collect_task(backup.task)
  }
  return [...seen]
}

export { swapSubstrings, swapTask, updateTrigger }
