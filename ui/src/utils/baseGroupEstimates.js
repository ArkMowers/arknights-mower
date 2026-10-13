import catalog from '../../../arknights_mower/data/building_skill.json'

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
// Compare time-dependent skills over the same right-side-max, 30-hour work cycle.
const workCycle = 30
const averageRamp = (initial, step, cap) =>
  Array.from({ length: workCycle }, (_, hour) => Math.min(cap, initial + hour * step)).reduce(
    (sum, value) => sum + value,
    0
  ) / workCycle

export function estimateFields(group) {
  switch (group.id) {
    case 'builtin-smoke':
      return [
        dorm(),
        recruits(),
        number('sui', '工作设施内岁人数', 5, 5),
        trade(),
        power(),
        number('factories', '制造站数', 5, 5)
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
    case 'builtin-tianmao':
    case 'builtin-cloud':
      return [{ key: 'average', label: '按照平均效率计算', type: 'checkbox', value: true }]
    case 'builtin-pozy':
      return [number('goldLines', '实际赤金生产线', 4, 5)]
    case 'builtin-siracusa':
      return [number('reception', '会客室等级', 3, 3, 1)]
    case 'builtin-karlan':
      return [
        choice('jayeStage', '孑的精英阶段', '未精英化', ['未精英化', '精一及以上']),
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
    const value = source[field.key]
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
  return [...group.accessory]
}

export function estimateGroup(group, selection, input = {}, items = [], maxLevel = false) {
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
  const skillsFor = (name) =>
    name === '孑'
      ? maxSkills
          .get(name)
          .filter((entry) => entry.skill_key === 0 || options.jayeStage === '精一及以上')
      : maxLevel
        ? maxSkills.get(name)
        : roster.get(name)?.childSkill
  const result = {
    metrics: [],
    details: [],
    warnings: [],
    valid: true,
    hasSelection: active.size > 0 && group.id !== 'builtin-run-order'
  }
  if (!result.hasSelection) return result
  for (const name of active) {
    const item = roster.get(name)
    if (item?.ownership === 'unowned' && !maxLevel && name !== '孑') {
      result.warnings.push(`${name}未拥有，无法按实际练度计算`)
    } else if (
      !skillsFor(name)?.length ||
      skillsFor(name).some((skill) => skill.status === 'unknown')
    ) {
      result.warnings.push(`${name}缺少森空岛练度，请同步后计算`)
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
  // Accessories supply roster conditions only; known unowned accessories do not count.
  const present = (name) =>
    selected.has(name) && (maxLevel || roster.get(name)?.ownership !== 'unowned')
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
  switch (group.id) {
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
        if (options.trade + options.power >= options.factories) metric('所有贸易站订单效率', 7)
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
      if (on('机械师'))
        factoryMetric(
          (has('机械师') ? 30 : 0) +
            (has('机械师', 1) ? (options.average ? (10 * (workCycle - 12)) / workCycle : 10) : 0),
          '经验'
        )
      if (has('烛煌', 1)) metric('无人机充能速度', 20)
      if (has('真言')) tradeMetric(tier('真言') === 1 ? 25 + Math.min(10, rooms) * 2 : 20)
      detail('凯尔希在办公室、机械师在制造站、烛煌在发电站、真言在贸易站')
      detail('精干设施数按已选精英干员人数计算，分别进驻不同设施；凯尔希最多计5间，真言最多计10间')
      if (on('机械师'))
        detail(
          options.average
            ? '机械师按右满30小时工作周期取平均，挂件不叠加自身技能'
            : '机械师按工作满12小时后的最高效率计算，挂件不叠加自身技能'
        )
      break
    }
    case 'builtin-nasti': {
      const rhine = count(
        members.filter((name) => name !== '缪尔赛思'),
        present
      )
      const capped = Math.min(5, rhine)
      metric('其他莱茵生命干员', capped, '人')
      const tech = familyCount(['娜斯提', '多萝西'], '莱茵科技·')
      const nasti = (has('娜斯提') ? 25 : 0) + (has('娜斯提', 1) ? capped * 3 : 0)
      const dorothy = (has('多萝西', 1) ? 25 : 0) + (has('多萝西') ? tech * 5 : 0)
      if (on('娜斯提') || on('多萝西'))
        factoryProducts(
          (has('娜斯提') ? 25 : 0) + dorothy,
          has('娜斯提', 1) ? { 赤金: capped * 3 } : {}
        )
      if (has('缪尔赛思', 1)) metric('无人机充能速度', 10 + capped * 3)
      detail(`娜斯提 ${nasti}% + 多萝西 ${dorothy}%；缪尔赛思在发电站`)
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
      const vulcanCap = has('火神') ? (tier('火神') === 1 ? 19 : 16) : 0
      const caps = [
        has('泡泡') ? 10 : 0,
        vulcanCap,
        has('圣约送葬人', 1) ? 4 : 0,
        has('贝娜') ? 17 : 0
      ]
      const base =
        (has('火神') ? -5 : 0) +
        (has('圣约送葬人') ? (tier('圣约送葬人') === 1 ? 30 : 20) : 0) +
        (has('贝娜') ? -20 : 0)
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
      const cap =
        (has('红云') ? 8 : 0) +
        (has('稀音', 1) ? 12 : 0) +
        (has('帕拉斯') ? 8 : 0) +
        (has('刻俄柏') ? 8 : 0)
      const base =
        (has('稀音') ? (options.average ? averageRamp(15, 2, 25) : 25) : 0) +
        (has('帕拉斯', 1) ? 25 : 0) +
        (has('刻俄柏', 1) ? (options.average ? averageRamp(20, 1, 25) : 25) : 0)
      const bonus = has('红云', 1) ? cap * 2 : 0
      metric('仓库容量加成', cap, '格')
      const exp = (has('帕拉斯', 1) ? 25 : 0) + (has('红云', 1) && has('稀音', 1) ? 24 : 0)
      factoryProducts(base + bonus - exp, exp ? { 经验: exp } : {})
      detail(
        `${options.average ? '按右满30小时工作周期取平均' : '按时间技能的最高效率计算'}：基础 ${base}% + 红云仓库折算 ${bonus}%`
      )
      break
    }
    case 'builtin-standardization': {
      const workers = ['水月', '杰西卡', '香草']
      capacity(workers, '同一制造站')
      const standards = familyCount(workers, '标准化·')
      const base = standards * 25
      const bonus =
        (has('水月') ? standards * 5 : 0) +
        (has('涤火杰西卡', 1) ? count(['杰西卡', '香草']) * 5 : 0)
      factoryMetric(base + bonus)
      detail(`标准化 ${base}% + 水月/涤火杰西卡加成 ${bonus}%`)
      detail('水月、杰西卡、香草在同一制造站，涤火杰西卡进驻中枢')
      break
    }
    default:
      throw new Error(`未定义组合估算规则：${group.id}`)
  }
  if (!result.valid) result.metrics = []
  return result
}
