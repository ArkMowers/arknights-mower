import { hasValidProgression } from './basementSkills'
import catalog from '../../../arknights_mower/data/building_skill.json'
import operatorCatalog from '../../../arknights_mower/data/riic/operators.json'
import terms from '@/pages/basement_skill/buffer.json'
import {
  normalizedReceptionEfficiency,
  receptionOccupancyBonus,
  receptionReferenceBonus
} from '@/riic/receptionEfficiency'
const operatorMetadata = new Map(
  operatorCatalog.operators.map((operator) => [operator.name, operator])
)
const termNames = (key) => terms[key].description.split('\n').slice(1).join('、').split('、')
const termIncludes = (key, name) => termNames(key).includes(name)
const extendableControlSkillNames = new Set(termNames('cc_c_skill'))
const skillCatalog = new Map(catalog.map((operator) => [operator.name, operator.child_skill]))
const minimalLayouts = [
  '三电 · 40%',
  '二电 · 1111宿舍 · 28%',
  '二电 · 2111宿舍 · 30%',
  '二电 · 3111宿舍 · 30%'
]
const minimalReference = [40, 28, 30, 30]

// Formulas follow the bundled building-skill catalog; skill_key identifies upgrades.
const maxSkills = new Map(
  catalog.map((operator) => {
    const skills = new Map()
    for (const entry of operator.child_skill) {
      if (
        !skills.has(entry.skill_key) ||
        skills.get(entry.skill_key).skill_level < entry.skill_level
      ) {
        skills.set(entry.skill_key, entry)
      }
    }
    return [operator.name, [...skills.values()].map((entry) => ({ ...entry, status: 'active' }))]
  })
)
const number = (key, label, value, max, min = 0) => ({ key, label, value, min, max })
const choice = (key, label, value, options) => ({
  key,
  label,
  value,
  options: options.map((option) => ({ label: option, value: option }))
})
const dorm = () => number('dorm', '宿舍人数', 20, 20)
const recruits = () => number('recruits', '额外招募位', 2, 2)
const trade = () => number('trade', '贸易站数', 2, 5)
const power = () => number('power', '发电站数', 2, 3, 1)
const averageRamp = (initial, step, cap, hours) => {
  let total = 0
  for (let hour = 0; hour < hours; hour++) {
    total += Math.min(1, hours - hour) * Math.min(cap, initial + hour * step)
  }
  return total / hours
}

export function estimateFields(group) {
  const residents = number('factoryResidents', '制造站实际人数', 3, 3, 1)
  const dormLevel = number('cuisineDorm', '森西所在宿舍等级', 1, 5, 1)
  if (group.kind === 'single' || group.estimator === 'control') {
    const name = group.core[0]
    const fields =
      ['机械师', '阿罗玛'].includes(name) && group.facility !== '办公' ? [residents] : []
    if (name === '槐琥') fields.push(number('peerEfficiency', '其他干员可复制生产力', 40, 200))
    if (name === '至简')
      fields.push(choice('dormLayout', '发电站与宿舍配置', minimalLayouts[0], minimalLayouts))
    if (name === '玛露西尔') fields.push(dormLevel)
    if (name === '引星棘刺') fields.push(trade())
    if (['吉星', '冻河'].includes(name))
      fields.push(number('tradeResidents', '贸易站工作人数', 3, 3, 1))
    if (name === '孑')
      fields.push(
        choice('jayeStage', '孑的精英阶段', '跟随森空岛', ['跟随森空岛', '未精英化', '精一及以上']),
        number('orderCap', '设施基础订单上限', 10, 10, 6)
      )
    if (name === '伺夜') fields.push(number('reception', '会客室等级', 3, 3, 1))
    if (name === '风絮') fields.push(number('suiRooms', '有岁干员的不同设施', 5, 5))
    if (name === '雪雉')
      fields.push(number('peerTradeEfficiency', '其他干员可复制订单效率', 35, 200))
    if (name === '承曦格雷伊') fields.push(number('droneCap', '无人机上限', 250, 250))
    if (name === '缪尔赛思') fields.push(number('rhineWorkers', '其他有心情的莱茵生命干员', 5, 5))
    if (group.facility === '会客') {
      if (['跃跃', '响石', '虎狼丸'].includes(name))
        fields.push(choice('clueExchange', '正在进行线索交流', '是', ['是', '否']))
      if (name === '克莱门莎') fields.push(number('awakePeers', '同室其他有心情干员数', 1, 1))
      if (name === '赤刃明霄陈') fields.push(number('fireworks', '人间烟火', 90, 95))
      if (name === '莱欧斯') fields.push(dormLevel)
    }
    if (group.facility === '中枢') {
      if (name === '望') fields.push(number('factories', '制造站数', 5, 5, 1))
      if (name === '望') fields.push(trade())
      if (name === '布丁') fields.push(number('workingPlatforms', '发电站有心情的作业平台数', 2, 3))
      if (name === '望') fields.push(power(), number('virtualPower', '技能额外发电站数', 0, 3))
      if (name === '丰川祥子' && group.estimator === 'control') fields.push(dorm())
      if (name === '玛恩纳' && group.estimator !== 'control')
        fields.push(number('extraMoodSkills', '其他已生效可扩展笑脸技能数（不含已选干员）', 0, 4))
      if (name === '摆渡人')
        fields.push(
          number('minosOthers', '其他米诺斯挂件数', 4, 4),
          choice('sargonInControl', '萨尔贡干员同驻中枢', '无', ['无', '有'])
        )
      if (name === '阿斯卡纶') fields.push(choice('training', '训练室正在专精', '是', ['是', '否']))
    }
    if (group.facility === '办公' && name === '凯尔希·思衡托')
      fields.push(number('eliteRooms', '有精英干员的不同设施', 5, 5))
    if (name === '石英') fields.push(number('formulaKinds', '制造配方种类', 3, 3, 1))
    if (name === '空弦') fields.push(number('dormLevels', '四间宿舍等级总和', 20, 20, 4))
    return fields
  }
  if (group.id.startsWith('builtin-jaye-'))
    return [
      choice('jayeStage', '孑的精英阶段', '跟随森空岛', ['跟随森空岛', '未精英化', '精一及以上']),
      number('orderCap', '设施基础订单上限', 10, 10, 6),
      ...(group.id === 'builtin-jaye-siracusa' ? [number('reception', '会客室等级', 3, 3, 1)] : []),
      ...(group.id === 'builtin-jaye-parts' ? [dormLevel] : [])
    ]
  switch (group.id) {
    case 'builtin-smoke':
      return [
        dorm(),
        recruits(),
        number('sui', '工作设施内岁人数', 5, 5),
        trade(),
        power(),
        number('factories', '制造站数', 5, 5),
        number('virtualPower', '技能额外发电站数', 0, 3)
      ]
    case 'builtin-perception':
      return [
        dorm(),
        recruits(),
        number('dormLevel', '爱丽丝/车尔尼宿舍等级', 1, 5, 1),
        number('roomResidents', '塑心所在宿舍人数', 5, 5)
      ]
    case 'builtin-monster-hunter':
      return [choice('catRoom', '调查团进驻', '贸易站', ['贸易站', '制造站'])]
    case 'builtin-automation':
      return [
        power(),
        trade(),
        number('droneCap', '无人机上限', 250, 250),
        choice('eunectesRoom', '森蚺进驻', '中枢', ['中枢', '制造站']),
        choice('platforms', '其他发电站有作业平台', '无', ['无', '有'])
      ]
    case 'builtin-abyss':
      return [number('targetHunters', '每个制造站猎人数', 2, 3, 1)]
    case 'builtin-aroma':
      return [residents, number('thirdEfficiency', '额外岗位可复制生产力', 15, 100)]
    case 'builtin-tianmao':
    case 'builtin-cloud':
    case 'builtin-bubble':
      return [residents]
    case 'builtin-cuisine':
      return [dormLevel]
    case 'builtin-pozy':
      return [number('goldLines', '实际赤金生产线', 4, 5)]
    case 'builtin-siracusa':
      return [number('reception', '会客室等级', 3, 3, 1)]
    case 'builtin-karlan':
      return [
        choice('jayeStage', '孑的精英阶段', '跟随森空岛', ['跟随森空岛', '未精英化', '精一及以上']),
        number('orderCap', '设施基础订单上限', 10, 10, 6)
      ]
    case 'builtin-gold':
      return [trade()]
    default:
      return []
  }
}

export function defaultEstimateOptions(group) {
  return Object.fromEntries(estimateFields(group).map((field) => [field.key, field.value]))
}

export function applyEstimateConditions(group, current, source = {}) {
  const result = { ...current }
  for (const field of estimateFields(group)) {
    const value = source[field.key] ?? (field.key === 'cuisineDorm' ? source.dormLevel : undefined)
    if (field.key === 'dormLayout' && field.options.some((option) => option.value === value)) {
      result[field.key] = value
      continue
    }
    if (
      field.type !== 'checkbox' &&
      !field.options &&
      Number.isInteger(value) &&
      value >= field.min &&
      value <= field.max
    ) {
      result[field.key] = value
    }
  }
  return result
}

export function defaultEstimateSelection(group) {
  return [...(group.defaultAccessories || group.accessory)]
}

export function estimateGroup(group, selection, input = {}, items = [], { maximum = false } = {}) {
  const fields = estimateFields(group)
  const options = Object.fromEntries(
    fields.map((field) => {
      const value = input[field.key] ?? field.value
      return [
        field.key,
        field.type === 'checkbox'
          ? typeof value === 'boolean'
            ? value
            : field.value
          : field.options
            ? field.options.some((option) => option.value === value)
              ? value
              : field.value
            : Number.isFinite(Number(value))
              ? Math.max(field.min, Math.min(field.max, Math.floor(Number(value))))
              : field.value
      ]
    })
  )
  const members = [...group.core, ...group.support, ...group.accessory]
  const selected = new Set(selection.filter((name) => members.includes(name)))
  const active = new Set([...selected].filter((name) => !group.accessory.includes(name)))
  const roster = new Map(items.map((item) => [item.avatar, item]))
  const assumeUnowned = (name) => roster.get(name)?.ownership === 'unowned'
  const hasProgression = (name) => !maximum && hasValidProgression(roster.get(name))
  const assumeMaximum = (name) => !hasProgression(name)
  const followJayeProgression = options.jayeStage === '跟随森空岛'
  const skillsFor = (name) =>
    name === '孑' && !followJayeProgression
      ? maxSkills
          .get(name)
          ?.filter((entry) => entry.skill_key === 0 || options.jayeStage === '精一及以上')
      : assumeMaximum(name)
        ? maxSkills.get(name)
        : roster.get(name)?.childSkill
  const result = {
    metrics: [],
    assumptions: [],
    details: [],
    warnings: [],
    valid: true,
    hasSelection: active.size > 0 && group.id !== 'builtin-run-order'
  }
  if (!result.hasSelection) return result
  if (group.core.includes('孑') && options.orderCap !== 10) {
    result.valid = false
    result.warnings.push('所有孑贸易推荐仅限3级贸易站，设施基础订单上限须为10')
    return result
  }
  for (const name of active) {
    if (!skillsFor(name)?.length || skillsFor(name).some((skill) => skill.status === 'unknown')) {
      result.warnings.push(
        name === '孑' ? '孑缺少基建技能目录' : `${name}缺少基建技能目录，无法计算`
      )
    }
  }
  if (result.warnings.length) return { ...result, valid: false }
  const skill = (name, key) =>
    active.has(name)
      ? skillsFor(name)?.find((entry) => entry.skill_key === key && entry.status === 'active')
      : undefined
  const has = (name, key = 0) => Boolean(skill(name, key))
  const tier = (name, key = 0) => skill(name, key)?.skill_level ?? -1
  const on = (name) => active.has(name)
  const assumedNames = [...selected].filter(
    (name) => assumeUnowned(name) && (name !== '孑' || followJayeProgression)
  )
  if (!maximum && assumedNames.length)
    result.details.push(`未拥有干员按满练度计算：${assumedNames.join('、')}`)
  const missingNames = [...selected].filter(
    (name) =>
      !assumeUnowned(name) && assumeMaximum(name) && (name !== '孑' || followJayeProgression)
  )
  if (!maximum && missingNames.length)
    result.details.push(`无有效练度数据，按满练度假设：${missingNames.join('、')}`)
  result.assumptions = maximum ? [] : [...assumedNames, ...missingNames]
  if (maximum)
    result.details.push(
      group.core.includes('孑') && options.jayeStage === '未精英化'
        ? '孑散件固定按精0技能计算'
        : '散件推荐按满练技能计算'
    )
  // Accessories supply roster conditions only, including explicit hypothetical ownership.
  const present = (name) => selected.has(name)
  const externalSkill = (name, key = 0) => {
    if (!present(name)) return undefined
    const entries = skillsFor(name)
    if (!entries?.length || entries.some((entry) => entry.status === 'unknown')) {
      result.valid = false
      result.warnings.push(`${name}缺少基建技能目录，无法计算`)
      return undefined
    }
    return entries.find((entry) => entry.skill_key === key && entry.status === 'active')
  }
  const externalHas = (name, key = 0) => Boolean(externalSkill(name, key))
  const count = (names, predicate = on) => names.filter(predicate).length
  const familyCount = (names, prefix) =>
    names
      .filter(on)
      .reduce(
        (total, name) =>
          total +
          skillsFor(name).filter(
            (entry) => entry.status === 'active' && entry.skillname.startsWith(prefix)
          ).length,
        0
      )
  const metric = (label, value, unit = '%') => result.metrics.push({ label, value, unit })
  const detail = (text) => result.details.push(text)
  const capacity = (names, room, limit = 3) => {
    const occupants = names.filter(on)
    if (occupants.length > limit) {
      result.valid = false
      result.warnings.push(`${room}已选${occupants.length}人，最多${limit}人，请取消部分干员`)
    }
    return occupants.length
  }
  const tradeMetric = (value) => metric('贸易订单效率', value)
  const factoryMetric = (value, product = '通用') => metric(`${product}制造生产力`, value)
  const factoryProducts = (common, products) => {
    if (common || !Object.keys(products).length) factoryMetric(common)
    for (const [product, extra] of Object.entries(products)) factoryMetric(common + extra, product)
    if (common && Object.keys(products).length)
      detail('各配方效率已包含通用制造加成，选择对应配方的结果，不重复叠加')
  }
  const factoryWorkCycle = (names, extraCost = {}) => {
    const workers = names.filter(on)
    // Five control-center occupants; each additional factory worker saves 0.05 mood/h.
    const residents = Math.max(workers.length, options.factoryResidents || 3)
    if (workers.length > options.factoryResidents) {
      result.valid = false
      result.warnings.push('制造站实际人数不能小于已选同站人数')
    }
    const baseCost = 1 - 5 * 0.05 - (Math.min(3, residents) - 1) * 0.05
    const rates = workers.map((name) => {
      const reduction =
        ['红云', '帕拉斯', '刻俄柏', '泡泡', '贝娜'].includes(name) && has(name)
          ? 0.25
          : name === '火神' && has(name)
            ? tier(name) === 1
              ? 0.25
              : 0.15
            : 0
      return {
        name,
        rate: baseCost - (has('槐琥') ? 0 : reduction) + (has('槐琥') ? 0 : extraCost[name] || 0)
      }
    })
    const fastest = Math.max(...rates.map(({ rate }) => rate))
    const hours = 24 / fastest
    const first = rates.filter(({ rate }) => Math.abs(rate - fastest) < 1e-9)
    detail(
      `从满心情24开始，按${first.map(({ name }) => name).join('、')}最先用尽计算平均效率，工作${Number(hours.toFixed(2))}小时；${rates.map(({ name, rate }) => `${name}每小时消耗${Number(rate.toFixed(2))}心情`).join('，')}`
    )
    detail('心情消耗按中枢5人及制造站实际人数计算；额外岗位不自动计入生产力或减耗技能')
    return hours
  }
  const receptionInfo = (name) => {
    const rarity = operatorMetadata.get(name)?.rarity
    if (!rarity) {
      result.valid = false
      result.warnings.push(`${name}缺少稀有度资料，无法折算会客效率`)
      return null
    }
    const maximum = rarity >= 4 ? 2 : rarity === 3 ? 1 : 0
    const observed = roster.get(name)?.progression?.match(/^精([012])(?:\s|$)/)?.[1]
    const phase =
      hasProgression(name) && observed !== undefined ? Math.min(maximum, Number(observed)) : maximum
    return { rarity, phase, bonus: receptionOccupancyBonus(rarity, phase) }
  }
  if (group.kind === 'single' || group.estimator === 'control') {
    const name = group.core[0]
    const personalCost =
      name === '酒神' && has(name)
        ? -0.25
        : (name === '阿罗玛' && has(name)) || (name === '裂响' && has(name, 1))
          ? 0.25
          : 0
    let hours
    if (['机械师', '阿罗玛'].includes(name))
      hours = factoryWorkCycle([name], { [name]: personalCost })
    const expNames = ['酒神', '断罪者', '食铁兽', '弑君者', '裂响']
    if (group.facility === '会客') {
      let raw = 0
      let cost = 0
      const sharedReception = ['予愿安洁莉娜', '风丸'].includes(name)
      if (name === '予愿安洁莉娜') {
        raw = has(name, 1) ? 50 : 0
        cost = has(name, 1) ? 2 : 0
      } else if (name === '风丸') raw = (has(name) ? 15 : 0) + (has(name, 1) ? 35 : 0)
      else if (name === '跃跃')
        raw = (has(name) ? 10 : 0) + (has(name, 1) && options.clueExchange === '是' ? 30 : 0)
      else if (name === '克莱门莎') {
        raw = (has(name) ? 20 : 0) + (has(name, 1) && options.awakePeers ? 15 : 0)
        cost = (has(name) ? 1 : 0) + (has(name, 1) && options.awakePeers ? 1 : 0)
      } else if (name === '见行者') {
        raw = has(name) ? (tier(name) === 1 ? 35 : 10) : 0
        cost = tier(name) === 1 ? 2 : 0
      } else if (name === '信仰搅拌机')
        raw =
          (has(name) ? (tier(name) === 1 ? 20 : 15) : 0) +
          (has(name, 1) && present('菲亚梅塔') ? 10 : 0)
      else if (name === '伊内丝') {
        raw = has(name, 1) ? averageRamp(20, 2, 30, 24 / 0.75) : 0
        detail('按每小时0.75心情消耗、32小时用尽窗口计算暖机平均')
      } else if (name === '赤刃明霄陈')
        raw = has(name, 1) ? 20 + Math.floor(options.fireworks / 10) : 0
      else if (name === '莱欧斯')
        raw = (has(name) ? 20 : 0) + (has(name, 1) && has('森西', 1) ? options.cuisineDorm * 2 : 0)
      else if (['响石', '虎狼丸'].includes(name))
        raw = has(name, 1) && options.clueExchange === '是' ? 30 : 0
      else if (['陈', '红'].includes(name)) raw = has(name, 1) ? 25 : 0
      else if (name === '伺夜') raw = has(name) ? 25 : 0
      else if (name === '星极') raw = has(name) ? (tier(name) === 1 ? 25 : 10) : 0
      const info = receptionInfo(name)
      if (info) {
        const efficiency =
          normalizedReceptionEfficiency(raw - (sharedReception ? 5 : 0), info.rarity, info.phase) /
          (sharedReception ? 2 : 1)
        metric('会客技能效率（折合精二六星）', efficiency)
        if (sharedReception) {
          detail('搭配1名0心情挂件，按两人平均除以2；挂件按精二六星基准，未列出或计入挂件技能')
          detail(
            `（技能${raw}% − 红脸挂件少5%普通工作进驻 + 本人稀有度与精英化${info.bonus}% − 精二六星基准21%）÷2 = ${Number(efficiency.toFixed(5))}%`
          )
        } else
          detail(
            `技能${Number(raw.toFixed(5))}% + ${info.rarity}星进驻${receptionOccupancyBonus(info.rarity, 0)}% + 精${info.phase}进驻${info.phase * 8}% − 精二六星基准${receptionReferenceBonus}%`
          )
      }
      if (cost) metric('自身心情消耗变化', cost, '/小时')
    } else if (group.facility === '回收') {
      metric('材料转化效率', has(name) ? (tier(name) === 1 ? 30 : 20) : 0)
      if (name === '国度' && has(name)) metric('自身心情消耗变化', -0.1, '/小时')
    } else if (group.facility === '中枢') {
      const factorySupport = (value) => metric('所有制造站·每站生产力', value)
      const tradeSupport = (value) => metric('所有贸易站·每站订单效率', value)
      const mood = (label, value) => metric(label, value, '/小时')
      if (group.estimator === 'control')
        capacity(
          members.filter((member) => group.placements[member] === '中枢'),
          '控制中枢',
          5
        )
      if (['八幡海铃', '焰狐龙梓兰'].includes(name)) metric('办公联络速度', has(name) ? 10 : 0)
      else if (['Mon3tr', '凯尔希', '结城理'].includes(name)) {
        factorySupport(has(name, name === '结城理' ? 0 : 1) ? 2 : 0)
        if (name === 'Mon3tr' && has(name)) mood('中枢全员·心情消耗变化', -0.05)
      } else if (name === '布丁')
        factorySupport(has(name, 1) && options.workingPlatforms >= 2 ? 2 : 0)
      else if (['阿米娅', '明椒', '阿斯卡纶'].includes(name)) {
        tradeSupport(has(name, name === '阿斯卡纶' ? 1 : 0) ? 7 : 0)
        if (name === '阿斯卡纶')
          metric('专精训练速度', has(name) && options.training === '是' ? 5 : 0)
      } else if (name === '望') {
        if (options.trade + options.power + options.virtualPower >= options.factories)
          tradeSupport(has(name) ? 7 : 0)
        else factorySupport(has(name) ? 2 : 0)
      } else if (name === '丰川祥子') {
        const linked = group.estimator === 'control'
        const enthusiasm = linked
          ? (has('八幡海铃') ? 10 : 0) +
            (has('三角初华') ? options.dorm : 0) +
            (has('祐天寺若麦') ? 10 : 0) +
            (has('若叶睦') ? 20 : 0)
          : options.enthusiasm
        const bonus = has(name)
          ? (tier(name) === 1 ? 1 : 0.5) * (1 + Math.floor(enthusiasm / 20))
          : 0
        metric('非自动化赤金站·每站生产力', bonus)
        const ownCost = has(name, 1) && enthusiasm >= 40 ? 0.05 : 0
        if (linked) {
          metric('热情值', enthusiasm, '点')
          if (has('八幡海铃')) metric('办公联络速度', 10)
          if (has('若叶睦')) {
            tradeSupport(Math.floor(enthusiasm / 8))
            mood(
              '若叶睦·自身心情消耗变化',
              has('若叶睦', 1) && on(name) ? 0 : Math.floor(enthusiasm / 8) * 0.01
            )
          }
          if (has('祐天寺若麦'))
            metric('会客线索搜集速度', 5 + (has('祐天寺若麦', 1) && on(name) ? 5 : 0))
          if (has('三角初华', 1)) mood('宿舍全员·心情恢复变化', 0.05)
          if (on(name))
            mood(
              '丰川祥子·自身心情消耗变化',
              ownCost + (has('祐天寺若麦', 1) ? 0.05 : 0) - (has('三角初华', 1) ? 0.1 : 0)
            )
          detail(
            '祥子自身消耗分别计入热情值阈值、若麦增加与初华恢复；若叶睦的额外消耗只在互为半身已解锁且祥子同驻时消除'
          )
        } else if (ownCost) mood('自身心情消耗变化', ownCost)
      } else if (name === '维什戴尔') {
        mood(
          '制造/贸易/发电/办公/会客·心情消耗变化',
          has(name, 1) ? -(0.1 + (on('魔王') ? 0.1 : 0)) : 0
        )
        if (on('伊内丝') && has(name)) metric('伊内丝·会客线索搜集', 5)
        if (group.estimator === 'control') {
          if (has('魔王', 1)) metric('魔王·会客线索搜集速度', 15)
          if (has('阿米娅')) tradeSupport(7)
          if (has('魔王') && on('阿米娅')) {
            const recovery = tier('魔王') === 1 ? 0.1 : 0.05
            mood('魔王·自身心情消耗变化', -recovery)
            mood('阿米娅·自身心情消耗变化', -recovery)
          }
        }
      } else if (name === '玛恩纳') {
        const contributors = members.filter(on).flatMap((operator) =>
          (skillsFor(operator) || [])
            .filter((entry) => entry.status === 'active')
            .map((entry) =>
              skillCatalog
                .get(operator)
                ?.find(
                  (source) =>
                    source.skill_key === entry.skill_key && source.skill_level === entry.skill_level
                )
            )
            .filter(
              (entry) =>
                entry?.roomType === '中枢' && extendableControlSkillNames.has(entry.skillname)
            )
            .map((entry) => ({ name: operator, skillname: entry.skillname }))
        )
        const smileSkills = contributors.length + (options.extraMoodSkills || 0)
        if (smileSkills > 5 && group.estimator !== 'control') {
          result.valid = false
          result.warnings.push('有效笑脸技能超过中枢5人上限，请减少其他技能数')
        }
        const extension = has(name, 1) ? 0.05 * smileSkills : 0
        mood('制造/贸易·心情消耗变化', -extension)
        mood('发电/办公/会客·心情消耗变化', -(extension + (has(name, 1) ? 0.1 : 0)))
        if (contributors.length) mood('中枢全员·心情消耗变化', -0.05 * contributors.length)
        if (group.estimator === 'control' && has('Mon3tr', 1)) factorySupport(2)
        detail(
          '按公事公办的官方技能清单，自动读取已选中枢干员当前已解锁的相关技能；不计未选择或未解锁的技能'
        )
        detail(
          '当前计入：' +
            (contributors.map((entry) => entry.name + '·' + entry.skillname).join('、') || '无')
        )
      } else if (['老鲤', '魔王'].includes(name))
        metric('会客线索搜集速度', has(name, 1) ? (name === '老鲤' ? 25 : 15) : 0)
      else if (name === '摆渡人') {
        metric(
          '会客线索搜集速度',
          has(name) ? Math.min(5, 1 + options.minosOthers) * (tier(name) === 1 ? 5 : 4) : 0
        )
        if (options.sargonInControl === '有' && has(name)) mood('自身心情消耗变化', 0.02)
      }
      detail('各设施效果分别列出；标注同种取最高的加成不叠加，心情效果按各技能规则计算')
    } else if (group.facility === '办公') {
      let contact = 0
      if (name === '斥罪') contact = has(name) ? 50 : 0
      else if (name === '凯尔希·思衡托') contact = has(name, 1) ? 30 + options.eliteRooms * 4 : 0
      else if (['艾雅法拉', '遥', '珊比'].includes(name)) contact = has(name, 1) ? 45 : 0
      else if (['地灵', '普罗旺斯', '水灯心'].includes(name))
        contact = has(name) ? (tier(name) === 1 ? 45 : 30) : 0
      else if (name === '圣聆初雪')
        contact = has(name) ? (tier(name) === 1 ? 35 + (present('凛御银灰') ? 10 : 0) : 20) : 0
      metric('办公联络速度', contact)
      const cost =
        name === '斥罪' && has(name)
          ? 0.5
          : name === '地灵' && tier(name) === 1
            ? 2
            : name === '水灯心' && has(name)
              ? 1
              : name === '圣聆初雪' && has(name)
                ? -0.25
                : 0
      if (cost) metric('自身心情消耗变化', cost, '/小时')
    } else if (name === '槐琥')
      factoryMetric(has(name, 1) ? Math.min(40, Math.floor(options.peerEfficiency / 5) * 5) : 0)
    else if (name === '至简') {
      if (tier(name, 1) === 1)
        factoryMetric(minimalReference[minimalLayouts.indexOf(options.dormLayout)])
      else {
        result.valid = false
        result.warnings.push('这四项配置参考使用至简的精二技能，当前练度未解锁')
      }
      detail('按指定发电站和宿舍配置展示精二技能参考值，不用手填工程机器人数量')
    } else if (name === '玛露西尔')
      factoryMetric(
        (has(name) ? (tier(name) === 1 ? 30 : 20) : 0) +
          (has(name, 1) && has('森西', 1) ? options.cuisineDorm : 0)
      )
    else if (name === '机械师')
      factoryMetric(
        (has(name) ? 30 : 0) + (has(name, 1) ? (10 * Math.max(0, hours - 12)) / hours : 0),
        '经验'
      )
    else if (expNames.includes(name))
      factoryMetric(
        ['酒神', '食铁兽'].includes(name)
          ? has(name)
            ? tier(name) === 1
              ? 35
              : name === '酒神'
                ? 20
                : 30
            : 0
          : has(name, 1)
            ? 35
            : 0,
        '经验'
      )
    else if (name === '阿罗玛')
      factoryMetric(
        (has(name) ? 25 : 0) + (has(name, 1) ? averageRamp(0, 2, 20, hours) : 0),
        '赤金'
      )
    else if (name === '引星棘刺')
      factoryMetric((has(name) ? 30 : 0) + (has(name, 1) ? options.trade * 3 : 0), '赤金')
    else if (name === '砾') factoryMetric(has(name, 1) ? 35 : 0, '赤金')
    else if (name === '褐果') factoryMetric((has(name) ? 15 : 0) + (has(name, 1) ? 30 : 0), '源石')
    else if (['炎熔', '地灵', '艾雅法拉', '谬因', '锡兰'].includes(name))
      factoryMetric(has(name, ['艾雅法拉', '谬因'].includes(name) ? 0 : 1) ? 35 : 0, '源石')
    else if (['吉星', '冻河'].includes(name))
      tradeMetric(
        has(name)
          ? (options.tradeResidents - 1) * (tier(name) === 1 ? 20 : name === '冻河' ? 15 : 10)
          : 0
      )
    else if (name === '孑') {
      if (has(name, 1)) {
        result.valid = false
        result.warnings.push('此条是精零孑推荐，请切换到未精英化假设或查看孑贸易组合')
      } else tradeMetric(has(name) ? options.orderCap * 4 : 0)
      detail('仅计算孑自身的空单贡献，不含其他干员带来的订单上限')
    } else if (name === '深巡')
      tradeMetric(
        has(name)
          ? (tier(name) === 1 ? 30 : 25) + (present('乌尔比安') ? (tier(name) === 1 ? 10 : 5) : 0)
          : 0
      )
    else if (name === '伺夜')
      tradeMetric(has(name, 1) ? Math.min(40, 25 + options.reception * 5) : 0)
    else if (name === '贝洛内')
      tradeMetric(
        has(name)
          ? (tier(name) === 1 ? 30 : 25) + (present('伺夜') ? (tier(name) === 1 ? 10 : 5) : 0)
          : 0
      )
    else if (name === '风絮')
      tradeMetric((has(name) ? 20 : 0) + (has(name, 1) ? options.suiRooms * 4 : 0))
    else if (name === '空弦')
      tradeMetric(has(name) ? options.dormLevels * (tier(name) === 1 ? 2 : 1) : 0)
    else if (name === '赫德雷')
      tradeMetric(
        has(name)
          ? (tier(name) === 1 ? 30 : 25) +
              (present('伊内丝') ? 5 : 0) +
              (tier(name) === 1 && present('W') ? 5 : 0)
          : 0
      )
    else if (name === '石英') tradeMetric(has(name, 1) ? 30 + options.formulaKinds * 2 : 0)
    else if (name === '雷狼龙S空爆') tradeMetric(has(name, 1) ? 35 : 0)
    else if (name === '雪雉')
      tradeMetric(
        has(name)
          ? Math.min(tier(name) === 1 ? 35 : 25, Math.floor(options.peerTradeEfficiency / 5) * 5)
          : 0
      )
    else if (['能天使', '海蒂'].includes(name))
      tradeMetric(has(name) ? (tier(name) === 1 ? 35 : 20) : 0)
    else if (group.facility === '发电') {
      let power
      if (name === '承曦格雷伊')
        power = has(name) ? Math.min(25, Math.floor(options.droneCap / 10)) : 0
      else if (name === '缪尔赛思') power = has(name, 1) ? 10 + options.rhineWorkers * 3 : 0
      else if (name === '空构') {
        const rate = 0.75 - (has(name, 1) ? 0.3 : 0)
        const hours = 24 / rate
        power = has(name)
          ? averageRamp(tier(name) === 1 ? 15 : 10, 1, tier(name) === 1 ? 20 : 15, hours)
          : 0
        detail(
          `从24心情开始，每小时消耗${Number(rate.toFixed(2))}，工作${Number(hours.toFixed(2))}小时；按用尽平均计算`
        )
      } else if (['烛煌', '炎狱炎熔', '天空盒', '时隙'].includes(name))
        power = has(name, 1) ? 20 : 0
      else
        power = has(name)
          ? name === '格雷伊' || tier(name) === 1
            ? 20
            : name === '澄闪'
              ? 10
              : 15
          : 0
      metric('无人机充能速度', power)
    } else throw new Error(`未定义单人推荐：${name}`)
    if (personalCost) {
      metric('自身心情消耗变化', personalCost, '/小时')
      detail(`技能使自身心情每小时消耗${personalCost > 0 ? '+' : ''}${personalCost}`)
    }
    if (!result.valid) result.metrics = []
    return result
  }
  if (group.id.startsWith('builtin-jaye-')) {
    if (on('孑') && has('孑', 1)) {
      result.valid = false
      result.warnings.push('此搭配限定精零孑，当前使用精一及以上技能；可手选未精英化进行假设比较')
    }
    if (options.orderCap !== 10) {
      result.valid = false
      result.warnings.push('此推荐限定三级贸易站，设施基础订单上限应为10')
    }
    const workers = [...group.core, ...group.support].filter((name) => name !== '八幡海铃')
    capacity(workers, '同一贸易站')
    let peers = 0,
      addedCap = 0
    if (group.id === 'builtin-jaye-siracusa') {
      const vigil = has('伺夜', 1) ? Math.min(40, 25 + options.reception * 5) : 0
      const belone = has('贝洛内')
        ? (tier('贝洛内') === 1 ? 30 : 25) + (on('伺夜') ? (tier('贝洛内') === 1 ? 10 : 5) : 0)
        : 0
      peers = vigil + belone + (has('八幡海铃', 1) ? count(['伺夜', '贝洛内']) * 5 : 0)
      addedCap = has('贝洛内', 1) && on('伺夜') ? 2 : 0
    } else if (group.id === 'builtin-jaye-hunters') {
      peers =
        (has('焰狐龙梓兰', 1) ? count(['焰狐龙梓兰', '雷狼龙S空爆']) * 20 : 0) +
        (has('雷狼龙S空爆', 1) ? 35 : 0)
      addedCap = has('焰狐龙梓兰', 1) ? 3 : 0
    } else if (group.id === 'builtin-jaye-penguin') {
      peers = has('德克萨斯') && on('拉普兰德') ? 65 : 0
      if (has('八幡海铃', 1) && on('拉普兰德')) peers += 5
      addedCap = has('拉普兰德') && on('德克萨斯') ? (tier('拉普兰德') === 1 ? 4 : 2) : 0
    } else {
      const catPoints =
        (externalHas('火龙S黑角') ? count(['火龙S黑角', '麒麟R夜刀'], present) * 2 : 0) +
        (externalHas('麒麟R夜刀') ? 8 : 0)
      for (const name of workers.filter((name) => name !== '孑' && on(name))) {
        let base = 0,
          cap = 0
        if (name === '泰拉大陆调查团' && has(name)) {
          base = 5 + catPoints * 3
          cap = 2
        }
        if (name === '赫德雷' && has(name)) {
          base =
            (tier(name) === 1 ? 30 : 25) +
            (present('伊内丝') ? 5 : 0) +
            (tier(name) === 1 && present('W') ? 5 : 0)
          const wisadel = externalSkill('维什戴尔')
          cap = wisadel ? (wisadel.skill_level === 1 ? 2 : 1) : 0
        }
        if (name === '瑰盐') {
          base = has(name, 1) ? 30 : 0
          cap = has(name) ? 3 : 0
        }
        if (name === '齐尔查克') {
          base =
            (has(name) ? 30 : 0) +
            (has(name, 1) && externalHas('森西', 1) ? options.cuisineDorm : 0)
          cap = has(name) ? 1 : 0
        }
        peers += base
        addedCap += cap
        metric(`${name}·搭档贡献`, base + (on('孑') ? cap * 4 : 0))
      }
      detail('搭档贡献已包含其订单上限为孑带来的加成；整站合计不重复计入')
    }
    const jaye = has('孑') ? (options.orderCap + addedCap) * 4 : 0
    tradeMetric(peers + jaye)
    detail(`其他干员 ${peers}% + 孑 ${jaye}%，空单状态，订单上限${options.orderCap + addedCap}`)
    if (!result.valid) result.metrics = []
    return result
  }
  switch (group.id) {
    case 'builtin-aroma': {
      capacity(group.core, '同一制造站')
      const hours = factoryWorkCycle(group.core, { 阿罗玛: has('阿罗玛') ? 0.25 : 0 })
      let aroma = 0,
        copy = 0
      for (let hour = 0; hour < hours; hour++) {
        const duration = Math.min(1, hours - hour)
        const current = (has('阿罗玛') ? 25 : 0) + (has('阿罗玛', 1) ? Math.min(20, hour * 2) : 0)
        aroma += current * duration
        const other = options.factoryResidents > count(group.core) ? options.thirdEfficiency : 0
        copy +=
          (has('槐琥', 1) ? Math.min(40, Math.floor((current + other) / 5) * 5) : 0) * duration
      }
      factoryMetric((aroma + copy) / hours, '赤金')
      detail(
        `阿罗玛平均${(aroma / hours).toFixed(4)}%，槐琥平均${(copy / hours).toFixed(4)}%；不含额外岗位自身生产力`
      )
      break
    }
    case 'builtin-ursus': {
      const winter = has('怒潮凛冬') ? 30 + (tier('怒潮凛冬') === 1 && on('烈夏') ? 10 : 0) : 0
      const leto = has('烈夏', 1) && on('古米') ? 35 : 0
      factoryMetric(winter + leto, '经验')
      if (has('古米')) tradeMetric(30)
      detail('制造站：怒潮凛冬、烈夏；贸易站：古米。古米离开贸易站后烈夏不再提供35%经验生产力')
      break
    }
    case 'builtin-laterano': {
      capacity(group.core, '同一贸易站')
      const laterano = count(group.core, (name) => on(name) && termIncludes('cc_g_laterano', name))
      const exusiai = group.core.some((name) => on(name) && termIncludes('cc_angel', name))
      tradeMetric(
        (has('安比尔', 1) ? 30 : 0) +
          (has('蕾缪安') ? 20 + (tier('蕾缪安') === 1 && exusiai ? 25 : 0) : 0) +
          (has('新约能天使', 1) ? laterano * 15 : 0)
      )
      detail('“能天使”术语包含新约能天使；“拉特兰”术语只计安比尔与蕾缪安，分别结算两种成员条件')
      break
    }
    case 'builtin-cuisine': {
      const cuisine = has('森西', 1) ? options.cuisineDorm : 0
      if (on('玛露西尔'))
        factoryMetric(
          (has('玛露西尔') ? (tier('玛露西尔') === 1 ? 30 : 20) : 0) +
            (has('玛露西尔', 1) ? cuisine : 0)
        )
      if (on('齐尔查克'))
        tradeMetric((has('齐尔查克') ? 30 : 0) + (has('齐尔查克', 1) ? cuisine : 0))
      detail(`森西提供${cuisine}点魔物料理；制造站、贸易站分别计算`)
      break
    }
    case 'builtin-smoke': {
      const smoke =
        (has('重岳') ? options.sui * 5 : 0) +
        (has('桑葚', 1) ? options.recruits * 10 : 0) +
        (has('令', 1) ? 15 : 0) +
        (has('夕') ? 15 : 0) +
        (has('乌有', 1) ? options.dorm : 0)
      metric('人间烟火', smoke, '点')
      if (has('重岳')) detail(`重岳：${options.sui}名岁 × 5 = ${options.sui * 5}烟火`)
      if (has('桑葚', 1))
        detail(`桑葚：${options.recruits}个额外招募位 × 10 = ${options.recruits * 10}烟火`)
      if (has('令', 1)) detail('令：烟火模式，心情大于12，提供15烟火')
      if (has('夕')) detail('夕：烟火模式，心情不高于12，提供15烟火')
      if (has('乌有', 1)) {
        detail(`乌有：${options.dorm}名宿舍干员提供${options.dorm}烟火`)
        tradeMetric(smoke)
      }
      if (has('桑葚')) metric('公招联络速度', tier('桑葚') === 1 ? 20 : 10)
      const cut =
        has('截云', 1) && has('截云') ? Math.floor(smoke / 5) * (tier('截云', 1) === 1 ? 2 : 1) : 0
      const shu = has('黍', 1) ? Math.floor(smoke / 3) : 0
      if (on('截云') || on('黍')) {
        factoryMetric(cut + shu)
        detail(`截云 ${cut}% + 黍 ${shu}%，每5/3点烟火按完整组折算`)
      }
      if (has('望')) {
        if (options.trade + options.power + options.virtualPower >= options.factories)
          metric('所有贸易站订单效率', 7)
        else metric('所有制造站·通用制造生产力', 2)
      }
      capacity(['重岳', '令', '夕', '望'], '中枢', 5)
      break
    }
    case 'builtin-perception': {
      const points =
        (has('迷迭香') ? options.dorm : 0) +
        (has('黑键') ? options.dorm : 0) +
        (has('絮雨', 1) && has('絮雨') ? options.recruits * 10 : 0) +
        (has('令', 1) ? 10 : 0) +
        (has('夕', 1) ? 10 : 0) +
        (has('车尔尼', 1) ? options.dormLevel : 0) +
        (has('爱丽丝', 1) ? options.dormLevel : 0)
      const resonance = (has('黑键') ? points : 0) + (has('塑心') ? options.roomResidents : 0)
      metric('感知信息', points, '点')
      if (has('迷迭香', 1)) factoryMetric(Math.floor(points / (tier('迷迭香', 1) === 1 ? 1 : 2)))
      if (has('黑键', 1)) {
        metric('无声共鸣', resonance, '点')
        tradeMetric(Math.floor(resonance / (tier('黑键', 1) === 1 ? 2 : 4)))
      }
      const recruitment = has('絮雨') ? 20 : 0
      if (on('絮雨') || on('琴柳'))
        metric('公招联络速度', recruitment + (has('琴柳', 1) && recruitment + 5 < 30 ? 20 : 0))
      for (const name of ['迷迭香', '黑键'])
        if (has(name)) detail(`${name}：${options.dorm}名宿舍干员提供${options.dorm}感知`)
      if (has('絮雨', 1)) detail(`絮雨：${options.recruits * 10}感知，心情耗尽后清空`)
      if (has('令', 1)) detail('令：感知模式，心情不高于12，提供10感知')
      if (has('夕', 1)) detail('夕：感知模式，心情大于12，提供10感知')
      for (const name of ['车尔尼', '爱丽丝'])
        if (has(name, 1)) detail(`${name}：${options.dormLevel}级宿舍提供${options.dormLevel}感知`)
      detail('琴柳按办公室基础联络速度5%判断；比例转换按完整组折算')
      break
    }
    case 'builtin-lgd': {
      if (has('斩业星熊', 1) && on('诗怀雅')) metric('所有制造站·通用制造生产力', 3)
      if (has('诗怀雅')) metric('所有贸易站订单效率', 7)
      detail('两人均进驻中枢')
      break
    }
    case 'builtin-monster-hunter': {
      const center = count(['火龙S黑角', '麒麟R夜刀'])
      const points = (has('火龙S黑角') ? center * 2 : 0) + (has('麒麟R夜刀') ? 8 : 0)
      metric('木天蓼', points, '点')
      if (center === 2 && has('火龙S黑角', 1)) metric('所有贸易站订单效率', 7)
      if (center === 2 && has('麒麟R夜刀', 1)) metric('所有制造站·通用制造生产力', 2)
      if (options.catRoom === '贸易站' && has('泰拉大陆调查团')) tradeMetric(5 + 3 * points)
      if (options.catRoom === '制造站' && has('泰拉大陆调查团', 1)) factoryMetric(5 + points)
      detail('黑角和夜刀进驻中枢，调查团按所选设施计算')
      break
    }
    case 'builtin-automation': {
      const center = options.eunectesRoom === '中枢'
      const virtualPower =
        options.power +
        (center && has('森蚺', 1) && present('Lancet-2') ? 2 : 0) +
        (has('承曦格雷伊', 1) && options.platforms === '无' ? 1 : 0)
      metric('计入技能的发电站', virtualPower, '间')
      const workers = ['温蒂', '清流', '冬时', ...(!center ? ['森蚺'] : [])]
      const staff = capacity(workers, '同一制造站')
      const suppressed = has('温蒂') || (!center && has('森蚺')) || has('冬时')
      const eunectes = !center && has('森蚺') ? virtualPower * (tier('森蚺') === 1 ? 10 : 5) : 0
      const weedy = has('温蒂') ? virtualPower * (tier('温蒂') === 1 ? 15 : 10) : 0
      const purestream = has('清流', 1) ? options.trade * 20 : 0
      const winter = tier('冬时') === 1 ? staff * 10 : 0
      factoryProducts(eunectes + weedy + winter, has('清流', 1) ? { 赤金: purestream } : {})
      detail(`森蚺 ${eunectes}% + 温蒂 ${weedy}% + 清流 ${purestream}% + 冬时 ${winter}%`)
      if (suppressed) detail('仅保留按设施数量提供的生产加成，其他普通生产力归零')
      if (has('承曦格雷伊'))
        metric('承曦格雷伊·无人机充能', Math.min(25, Math.floor(options.droneCap / 10)))
      if (has('流明'))
        metric(
          '流明·宿舍全员心情恢复',
          (tier('流明') === 1 ? 0.15 : 0.1) + options.power * 0.05,
          '/小时'
        )
      detail('Lancet-2按发电站在岗条件计数，不计算自身充能技能')
      break
    }
    case 'builtin-abyss': {
      const manufacturers = count(['斯卡蒂', '幽灵鲨', '乌尔比安', '安哲拉'])
      const stations = Array.from(
        { length: Math.ceil(manufacturers / options.targetHunters) },
        (_, index) => Math.min(options.targetHunters, manufacturers - index * options.targetHunters)
      )
      if (has('歌蕾蒂娅', 1)) {
        const perHunter = tier('歌蕾蒂娅', 1) === 1 ? 10 : 5
        const cap = tier('歌蕾蒂娅', 1) === 1 ? 90 : 45
        stations.forEach((hunters, index) =>
          metric(
            `制造站${'一二三四'[index]}·通用制造生产力`,
            Math.min(cap, manufacturers * hunters * perHunter)
          )
        )
      }
      if (has('深巡'))
        tradeMetric(
          (tier('深巡') === 1 ? 30 : 25) + (on('乌尔比安') ? (tier('深巡') === 1 ? 10 : 5) : 0)
        )
      detail(
        `歌蕾蒂娅在中枢，${manufacturers}名猎人分配到${stations.length}个制造站${stations.length ? `，${stations.map((hunters, index) => `第${index + 1}站${hunters}人`).join('、')}` : ''}`
      )
      break
    }
    case 'builtin-redpine': {
      capacity(['远牙', '灰毫', '野鬃', '砾'], '同一制造站')
      const pine = count(['远牙', '灰毫', '野鬃'])
      const knights = pine + (on('砾') ? 1 : 0)
      const base =
        (has('远牙', 1) ? (tier('远牙', 1) === 1 ? 25 : 15) : 0) +
        ['灰毫', '野鬃'].reduce(
          (sum, name) => sum + (has(name) ? (tier(name) === 1 ? 25 : 15) : 0),
          0
        )
      const generalBonus = has('薇薇安娜', 1) ? knights * 7 : 0
      const pineBonus = has('焰尾', 1) ? pine * 10 : 0
      const gold = has('砾', 1) ? 35 : 0
      const bonus = generalBonus + pineBonus
      factoryProducts(base + generalBonus, {
        ...(pineBonus ? { 经验: pineBonus } : {}),
        ...(pineBonus || gold ? { 赤金: gold - pineBonus } : {})
      })
      detail(`制造干员基础 ${base}% + 骑士/红松林加成 ${bonus}%`)
      detail('薇薇安娜、焰尾在中枢；焰尾增加经验生产、降低赤金生产；砾仅增加赤金生产')
      break
    }
    case 'builtin-tianmao': {
      const rooms = count(['机械师', '烛煌', '真言', '迷迭香', '煌', '逻各斯', '电弧'], present)
      metric('精英干员设施', rooms, '间')
      if (has('凯尔希·思衡托', 1)) metric('公招联络速度', 30 + Math.min(5, rooms) * 4)
      if (on('机械师')) {
        const hours = factoryWorkCycle(['机械师'])
        factoryMetric(
          (has('机械师') ? 30 : 0) +
            (has('机械师', 1) ? (10 * Math.max(0, hours - 12)) / hours : 0),
          '经验'
        )
      }
      if (has('烛煌', 1)) metric('无人机充能速度', 20)
      if (has('真言')) tradeMetric(tier('真言') === 1 ? 25 + Math.min(10, rooms) * 2 : 20)
      detail('凯尔希在办公室、机械师在制造站、烛煌在发电站、真言在贸易站')
      detail('精干设施数按已选精英干员人数计算，分别进驻不同设施；凯尔希最多计5间，真言最多计10间')
      if (on('机械师')) detail('机械师单独进驻制造站，挂件不叠加自身技能')
      break
    }
    case 'builtin-nasti': {
      capacity(['娜斯提', '多萝西', '淬羽赫默'], '同一制造站')
      const rhine = count(
        members.filter((name) => !['缪尔赛思', '淬羽赫默'].includes(name)),
        present
      )
      const capped = Math.min(5, rhine)
      const nastiCount = Math.min(5, rhine + (present('缪尔赛思') ? 1 : 0))
      metric('其他莱茵生命干员', capped, '人')
      const tech = familyCount(['娜斯提', '多萝西', '淬羽赫默'], '莱茵科技·')
      const nasti = (has('娜斯提') ? 25 : 0) + (has('娜斯提', 1) ? nastiCount * 3 : 0)
      const dorothy = (has('多萝西', 1) ? 25 : 0) + (has('多萝西') ? tech * 5 : 0)
      const silence = has('淬羽赫默', 1) ? 30 : 0
      if (on('娜斯提') || on('多萝西') || on('淬羽赫默'))
        factoryProducts(
          (has('娜斯提') ? 25 : 0) + dorothy + silence,
          has('娜斯提', 1) ? { 赤金: nastiCount * 3 } : {}
        )
      if (has('缪尔赛思', 1)) metric('无人机充能速度', 10 + capped * 3)
      detail(`娜斯提 ${nasti}% + 多萝西 ${dorothy}% + 淬羽赫默 ${silence}%；缪尔赛思在发电站`)
      detail('莱茵生命挂件不可0心情；淬羽赫默提供莱茵科技技能，不计入莱茵生命人数')
      detail('娜斯提的莱茵生命人数包含缪尔赛思，缪尔赛思的充能技能不计自身')
      break
    }
    case 'builtin-makoto': {
      const sees = Math.min(4, count(members, present))
      metric('S.E.E.S.在岗人数', sees, '人')
      if (has('结城理', 1)) factoryMetric(20 + sees * 5)
      if (has('埃癸斯')) metric('无人机充能速度', 15 + (on('结城理') ? 5 : 0))
      detail('结城理在制造站，埃癸斯在发电站，挂件仅提供S.E.E.S.人数')
      break
    }
    case 'builtin-pozy': {
      capacity(['鸿雪', '图耶', '绮良'], '同一贸易站')
      const durin = Math.min(4, count(['杜林', '桃金娘', '至简', '褐果', '特克诺'], present))
      const baseLines = options.goldLines + (has('鸿雪', 1) ? durin : 0)
      const extraLines = has('绮良')
        ? Math.floor(options.goldLines / (tier('绮良') === 1 ? 2 : 4)) * 2
        : 0
      const lines = baseLines + extraLines
      metric('赤金生产线', lines, '条')
      const pozy = has('鸿雪') ? lines * 5 : 0
      const tuye = has('图耶') ? 5 + Math.floor(lines / (tier('图耶') === 1 ? 2 : 4)) * 15 : 0
      tradeMetric(pozy + tuye + (has('绮良') ? 5 : 0))
      detail(
        `实际${options.goldLines}条 + 鸿雪杜林${has('鸿雪', 1) ? durin : 0}条 + 绮良${extraLines}条，绮良仅按实际赤金生产线计算`
      )
      detail(`鸿雪 ${pozy}% + 图耶 ${tuye}% + 绮良 ${has('绮良') ? 5 : 0}%`)
      if (on('褐果')) {
        factoryProducts(has('褐果') ? 15 : 0, has('褐果', 1) ? { 源石: 30 } : {})
        detail('褐果在另一个制造站，源石结果包含通用加成；杜林族须有心情')
      }
      break
    }
    case 'builtin-siracusa': {
      const vigil = has('伺夜', 1) ? Math.min(40, 25 + options.reception * 5) : 0
      const belone = has('贝洛内')
        ? (tier('贝洛内') === 1 ? 30 : 25) + (on('伺夜') ? (tier('贝洛内') === 1 ? 10 : 5) : 0)
        : 0
      const bonus = has('八幡海铃', 1) ? count(['伺夜', '贝洛内']) * 5 : 0
      tradeMetric(vigil + belone + bonus)
      if (has('八幡海铃')) metric('公招联络速度', 10)
      detail(`伺夜 ${vigil}% + 贝洛内 ${belone}% + 海铃中枢加成 ${bonus}%`)
      break
    }
    case 'builtin-exusiai': {
      tradeMetric(
        (has('能天使') ? (tier('能天使') === 1 ? 35 : 20) : 0) +
          (has('蕾缪安') ? 20 + (tier('蕾缪安') === 1 && on('能天使') ? 25 : 0) : 0)
      )
      detail('能天使与蕾缪安进驻同一贸易站')
      break
    }
    case 'builtin-glasgow': {
      const gang = count(['摩根', '推进之王'])
      const morgan = has('摩根', 1) ? gang * 20 + (on('推进之王') ? 35 : 0) : 0
      const vinas = has('维娜·维多利亚')
        ? 30 + (tier('维娜·维多利亚') === 1 && gang > 0 ? 10 : 0)
        : 0
      tradeMetric(morgan + vinas + (has('戴菲恩', 1) ? gang * 10 : 0))
      detail('戴菲恩进驻中枢，其余勾选成员进驻同一贸易站')
      detail('推进之王在贸易站仅提供阵营人数，不计宿舍技能')
      break
    }
    case 'builtin-karlan': {
      const workers = ['孑', '银灰', '琳琅诗怀雅', '崖心', '锏']
      capacity(workers, '同一贸易站')
      const karlan = count(['银灰', '崖心', '锏'])
      const silver = has('银灰') ? (tier('银灰') === 1 ? 20 : 15) : 0
      const cliff = has('崖心', 1) ? 15 : 0
      const degen = has('锏') ? (tier('锏') === 1 ? 25 : 20) : 0
      const gnosis = has('灵知', 1) ? karlan * 6 : 0
      const positiveCap =
        (has('银灰') ? (tier('银灰') === 1 ? 4 : 2) : 0) + (has('崖心', 1) ? 4 : 0) + gnosis
      const negativeCap = has('锏') ? (tier('锏') === 1 ? 6 : 2) : 0
      const addedCap = positiveCap - negativeCap
      const degenBonus = has('锏', 1)
        ? Math.min(100, Math.floor(Math.max(0, addedCap) / 5) * 25)
        : 0
      const beforeSwire =
        silver +
        cliff +
        degen +
        (has('琳琅诗怀雅') ? 20 : 0) +
        degenBonus -
        (has('灵知', 1) ? karlan * 15 : 0)
      // Champion's Bearing resolves before Basic Needs; Investment Solicitations resolves after it.
      const reduction = has('孑', 1) ? Math.floor(Math.max(0, beforeSwire) / 10) : 0
      const cap = Math.max(1, options.orderCap + addedCap - reduction)
      const swireBonus = has('琳琅诗怀雅', 1) ? Math.max(0, addedCap - reduction) * 4 : 0
      const peers = beforeSwire + swireBonus
      const jaye = has('孑') ? cap * 4 : 0
      metric('订单上限', cap, '笔')
      tradeMetric(peers + jaye)
      if (has('孑')) {
        const source = followJayeProgression
          ? assumeUnowned('孑')
            ? '未拥有满练度假设'
            : assumeMaximum('孑')
              ? '无数据满练度假设'
              : '森空岛练度'
          : '手动选择'
        detail(`孑${has('孑', 1) ? '精一及以上' : '未精英化'}，使用${source}`)
      }
      detail(`其他干员 ${peers}% + 孑 ${jaye}%，按空单状态估算`)
      detail(`订单上限增加${positiveCap}，锏减少${negativeCap}，孑减少${reduction}，上限至少1`)
      if (has('琳琅诗怀雅', 1) || has('锏', 1))
        detail(
          `琳琅诗怀雅 ${swireBonus}% + 锏 ${degenBonus}%，仅转换干员净增加的订单上限，不含设施基础值`
        )
      detail('灵知在中枢；先结算锏的订单转效率，再计孑的扣减，最后结算琳琅诗怀雅的订单转效率')
      break
    }
    case 'builtin-gold': {
      capacity(members, '同一制造站')
      const metal = familyCount(members, '金属工艺·')
      const base =
        (has('苍苔') ? 30 : 0) +
        (has('引星棘刺') ? 30 : 0) +
        (has('砾', 1) ? 35 : 0) +
        (has('斑点', 1) ? 30 : 0) +
        (has('夜烟') ? 30 : 0) +
        (has('温米', 1) ? 30 : 0)
      const bonus = (has('苍苔', 1) ? metal * 5 : 0) + (has('引星棘刺', 1) ? options.trade * 3 : 0)
      factoryProducts(has('苍苔', 1) ? metal * 5 : 0, {
        赤金: base + (has('引星棘刺', 1) ? options.trade * 3 : 0)
      })
      detail(`基础金属技能 ${base}% + 苍苔/引星棘刺加成 ${bonus}%`)
      break
    }
    case 'builtin-bubble': {
      capacity(members, '同一制造站')
      const hours = on('刻俄柏') ? factoryWorkCycle(members) : 0
      const vulcanCap = has('火神') ? (tier('火神') === 1 ? 19 : 16) : 0
      const caps = [
        has('泡泡') ? 10 : 0,
        vulcanCap,
        has('圣约送葬人', 1) ? 4 : 0,
        has('贝娜') ? 17 : 0,
        has('刻俄柏') ? 8 : 0
      ]
      const base =
        (has('火神') ? -5 : 0) +
        (has('圣约送葬人') ? (tier('圣约送葬人') === 1 ? 30 : 20) : 0) +
        (has('贝娜') ? -20 : 0) +
        (has('刻俄柏', 1) ? averageRamp(20, 1, 25, hours) : 0)
      const bonus = has('泡泡', 1)
        ? caps.reduce((sum, cap) => sum + cap * (cap > 16 ? 3 : 1), 0)
        : 0
      metric(
        '仓库容量加成',
        caps.reduce((sum, cap) => sum + cap, 0),
        '格'
      )
      const exp =
        (has('圣约送葬人') ? (tier('圣约送葬人') === 1 ? 30 : 20) : 0) +
        (has('泡泡', 1) && has('圣约送葬人', 1) ? 4 : 0)
      factoryProducts(base + bonus - exp, on('圣约送葬人') ? { 经验: exp } : {})
      detail(`基础 ${base}% + 每名干员各自仓库折算 ${bonus}%`)
      break
    }
    case 'builtin-cloud': {
      capacity(members, '同一制造站')
      const hours = factoryWorkCycle(members)
      const cap =
        (has('红云') ? 8 : 0) +
        (has('稀音', 1) ? 12 : 0) +
        (has('帕拉斯') ? 8 : 0) +
        (has('刻俄柏') ? 8 : 0)
      const base =
        (has('稀音') ? averageRamp(15, 2, 25, hours) : 0) +
        (has('帕拉斯', 1) ? 25 : 0) +
        (has('刻俄柏', 1) ? averageRamp(20, 1, 25, hours) : 0)
      const bonus = has('红云', 1) ? cap * 2 : 0
      metric('仓库容量加成', cap, '格')
      const exp = (has('帕拉斯', 1) ? 25 : 0) + (has('红云', 1) && has('稀音', 1) ? 24 : 0)
      factoryProducts(base + bonus - exp, exp ? { 经验: exp } : {})
      detail(`用尽平均：基础 ${base}% + 红云仓库折算 ${bonus}%`)
      break
    }
    case 'builtin-standardization': {
      const workers = ['水月', '杰西卡', '香草', '杏仁', '褐果']
      capacity(workers, '同一制造站')
      const standardSkills = workers
        .filter(on)
        .flatMap((name) =>
          skillsFor(name).filter(
            (entry) => entry.status === 'active' && entry.skillname?.startsWith('标准化·')
          )
        )
      const standards = standardSkills.length
      const base = standardSkills.reduce(
        (total, entry) =>
          total + ({ '标准化·α': 15, '标准化·β': 25, '标准化·γ': 30 }[entry.skillname] || 0),
        0
      )
      const bonus =
        (has('水月') ? standards * 5 : 0) +
        (has('涤火杰西卡', 1) ? count(['杰西卡', '香草', '杏仁']) * 5 : 0)
      const blacksteel = Math.min(3, count(['杰西卡', '香草', '杏仁'], present))
      const almond = (has('杏仁') ? 25 : 0) + (has('杏仁', 1) ? blacksteel * 2 : 0)
      factoryProducts(base + bonus, {
        ...(on('杏仁') ? { 赤金: almond } : {}),
        ...(has('褐果', 1) ? { 源石: 30 } : {})
      })
      detail(`标准化 ${base}% + 水月/涤火杰西卡加成 ${bonus}%`)
      if (on('杏仁')) detail(`杏仁 ${almond}%赤金生产力，计入${blacksteel}名黑钢干员（最多3名）`)
      detail('水月、杰西卡、香草、杏仁、褐果从中选择至多3人进驻同一制造站，涤火杰西卡进驻中枢')
      break
    }
    default:
      throw new Error(`未定义组合估算规则：${group.id}`)
  }
  if (!result.valid) result.metrics = []
  return result
}
