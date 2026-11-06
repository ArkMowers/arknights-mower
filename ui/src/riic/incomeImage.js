import {
  CALCULATOR_REVISION,
  MOWER_REFERENCE,
  incomeImageMetrics,
  incomeFacilities,
  incomeWorkspace,
  incomeWeights
} from './income'

import { MOWER_RAW_MATERIALS } from './vendor/domain/simulationInventory'
import { incomeInitialInventory } from './incomeCache'
import { incomeOrderDistribution } from './incomeOrders'
import { incomeAlgorithmLabel } from '@/utils/incomeSettings'

const number = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export function incomeReportLines(result, settings, plan, label) {
  const finite = settings.finiteInventory || result.inventoryMode === 'finite'
  const initialMood =
    result.initialConditions?.fiammettaMorale == null
      ? '初始心情 24（受个人上限约束）'
      : `菲亚梅塔初始心情 ${result.initialConditions.fiammettaMorale}；其他干员从个人心情上限开始（未设置时为 24）`
  const provenance = result.modelProvenance
  const expected =
    result.simulationReport?.production?.assumptions.expectationMode ??
    settings.expectationMode ??
    false
  const theoretical = provenance?.timingModel === 'theoretical-events-v1'
  const continuous = expected && result.simulationReport?.production?.expected
  const thresholdDrones =
    result.simulationReport?.production?.assumptions.droneAllocationModel === 'threshold-v1'
  const seed = result.simulationReport?.production?.assumptions.seed ?? settings.seed
  const target = incomeFacilities(plan).find((f) => f.roomId === settings.droneRoom)
  const levels = Object.values(incomeWorkspace(plan).mainPlan.facilities)
    .filter((f) => f.level > 0)
    .map((f) => `${f.roomId}=${f.level}`)
    .join('；')
  return [
    `原图：${label}；二维码包含完整主副表和高级设置，可在 Mower「导入排班」中读取。`,
    `预热 ${settings.warmupDays} 天，不计入收益；统计 ${number(result.observedHours / 24)} 天，共 ${settings.warmupDays + settings.sampleDays} 天；${expected ? (theoretical ? '理论期望模式' : continuous ? '数学期望模式（连续产出）' : '数学期望模式（平均订单模型）') : `随机种子 ${seed}`}。`,
    ...(expected
      ? [
          theoretical
            ? `理论期望模式按换班、心情、技能、生产及材料事件推进，安排即时完成、产物及时收取，不模拟页面操作。各项产出和材料成本按有效工作时间累计小数数量。${thresholdDrones ? '无人机沿用配置的检查间隔、制造保留阈值和贸易加速规则，在使用时计入当时产物；未使用或溢出的无人机不折算产出。' : '无人机按新生成能力连续加速目标设施。'}调度与库存阈值耦合下仍为近似期望，不代表已达到稳态。`
            : continuous
              ? '数学期望模式按有效工作时间和即时效率累计经验、赤金、源石碎片、订单及材料消耗的小数数量；公招、线索和回收次数同样保留小数。无人机按统计期生成的加速能力折算到所选设施，不计期初库存，也不重复计入实际使用的加速收益。排班、缺料和库存阈值耦合下仍为近似期望。'
              : '数学期望模式按开始时的订单分布平均获取耗时，完成时逐档应用特殊效果后平均奖励与消耗。固定效率与概率下，长期收益率为期望奖励除以期望耗时；换班、缺料及库存阈值耦合下为近似期望。裁缝暖机概率沿用未经实测核验的近似曲线。'
        ]
      : []),
    `无人机：${target?.label ?? '不使用'}；${finite ? `有限库存：连续记账；${settings.allowMaterialDebt ? '允许原材料亏空，负数表示缺口' : settings.allowGoldDebt ? '允许赤金透支，其他材料缺料停产或暂停交付' : '缺料停产或暂停交付'}。` : '潜在产出：不受初始库存限制，不能视为可交付收入。'}`,
    ...(Object.values(settings.dailyExternalResources ?? {}).some((value) => value > 0)
      ? [
          `日均外源材料：${MOWER_RAW_MATERIALS.filter(
            (item) => settings.dailyExternalResources[item.resource] > 0
          )
            .map(
              (item) => `${item.label} ${number(settings.dailyExternalResources[item.resource])}`
            )
            .join('；')}。按时间补入库存，外源补入不计产出或加权收益。`
        ]
      : []),
    ...(result.stability?.drones
      ? [
          `统计期无人机：期初 ${number(result.stability.drones.opening)}，期末 ${number(result.stability.drones.closing)}，差额 ${number(result.stability.drones.change)}；生成 ${number(result.stability.drones.generated)}，消耗 ${number(result.stability.drones.consumed)}，溢出 ${number(result.stability.drones.overflow)}。${continuous ? (thresholdDrones ? `本次计入收益的有效加速为 ${number(continuous.droneAllocated)} 架；先消耗期初库存且不计其收益，采样期新生成部分在使用时计入。未使用部分保留库存。` : `收益另按生成的加速能力计算，本次可折算 ${number(continuous.droneAllocated)} 架；该表为调度库存观察。`) : '差额未折算收益。'}`,
          '初始心情与轮换阶段的影响未自动消除；前后半段效率和驻岗占比仅供比较，不构成达到稳态的证明。'
        ]
      : []),
    ...(finite
      ? [
          `初始库存（${settings.inventorySource === 'cache' ? '森空岛缓存，可手动补充修改' : '手动设定'}）：${
            Object.entries(incomeInitialInventory(settings))
              .map(([key, value]) => `${key}=${value}`)
              .join('；') || '全部为 0'
          }。初始数量不计入收益。`
        ]
      : []),
    ...(finite
      ? [
          `赤金余额：初始 ${number(result.goldInventory.initial)}；统计开始 ${number(result.goldInventory.sampleOpening)}；期末 ${number(result.goldInventory.closing)}。负数表示赤金缺口，不代表实物库存。`
        ]
      : []),
    ...(settings.operatorMode === 'cache' || (finite && settings.inventorySource === 'cache')
      ? [
          `缓存库存同步时间：${settings.cacheObservedAt ? new Date(settings.cacheObservedAt * 1000).toLocaleString('zh-CN') : '缓存未提供时间'}；缓存不代表当前游戏即时状态。`
        ]
      : []),
    `干员：${settings.operatorMode === 'cache' ? '森空岛缓存的实际拥有和练度' : settings.operatorMode === 'custom' ? '按本次填写的拥有和练度' : '全部干员满配假设'}；${initialMood}；孑精零 ${settings.jayeElite0 ? '开启' : '关闭'}。`,
    settings.masteryPlanPresent === undefined
      ? '本次演算固定为无未完成训练计划且未在训练，不模拟训练进度或计划完成时刻。'
      : `历史演算的未完成训练计划：${settings.masteryPlanPresent ? '有' : '无'}，整段演算保持此条件，不模拟训练完成。`,
    '赤金等价龙门币为制造赤金 × 500 加特殊订单溢价，不扣除交付消耗的赤金；该项不是实际龙门币入账。',
    '制造配方默认已解锁，当前制造站等级不限制配方；各站容量及材料库存仍按本次配置计算。',
    continuous
      ? '龙门币产出与制造源石碎片消耗的龙门币、固源岩及装置分别显示；消耗按统计期有效工作量分摊，保留小数，排除预热部分。'
      : '龙门币产出与制造源石碎片消耗的龙门币、固源岩及装置分别显示；消耗按统计期实际开工批次计算，包含尚未完成的批次，预热期已支付的材料不重复计入。',
    `收益权重（${settings.weightMode === 'mower' ? incomeAlgorithmLabel(settings.mowerAlgorithm) : '本次自定义'}）：${Object.entries(
      incomeWeights(settings)
    )
      .map(([key, value]) => `${key}=${value}`)
      .join('；')}。加权产出不是龙门币结算额。`,
    theoretical
      ? '模型假设：理想跑单；按关键事件推进，忽略页面操作耗时；宿舍氛围按等级上限。'
      : '模型假设：理想跑单；部分读房与调度耗时已建模，其余点击识别耗时忽略；宿舍氛围按等级上限。',
    provenance?.moodControlStrategyVersion
      ? provenance.moodControlStrategyVersion === 'ordinary-threshold-v1'
        ? `轮班策略 ${provenance.moodControlStrategyVersion}；实时心情计算调控${provenance.predictiveMoodControl ? '开启' : '关闭'}。两种模式均模拟心情变化，按正常下班阈值轮休，不为避免替班断档而提前下班；普通救急召回须能坚持到对应主班回满。`
        : `轮班策略 ${provenance.moodControlStrategyVersion}；实时心情计算调控${provenance.predictiveMoodControl ? '开启' : '关闭'}。两种模式均模拟心情变化。`
      : '这份历史记录未保存轮班策略版本，重新演算后可比较当前策略。',
    `本次设施等级（优先使用排班保存值，未设置时推断）：${levels}。`,
    provenance
      ? `计算器基线 ${provenance.calculatorBaseRevision}，选择性同步 ${provenance.calculatorSyncRevision}（含本地适配）；调度基线 Mower alpha ${provenance.mowerBaseReference}，本轮核对 ${provenance.mowerCheckedRevision}，后续本体逻辑不自动同步。`
      : `计算器 ${CALCULATOR_REVISION}（含本地完成时刻精度、赤金透支、制造成本观察、公招与线索观察适配）；调度参考 Mower alpha ${MOWER_REFERENCE}，后续本体逻辑不自动同步。`,
    '公招刷新按办公室驻员、心情与已解锁技能计算联络产出；初始进度为零，预热进度延续但预热完成次数不计。假设及时使用刷新次数，不模拟存满 3 次停工，不计入加权收益。',
    ...(result.summary?.clueCount == null
      ? ['这份历史记录未统计会客室线索，重新演算后可查看。']
      : [
          '会客室线索仅统计驻员搜集完成的个数，初始进度为零，预热进度延续但预热完成数不计；假设及时领取及清理库存，不模拟满库停工、每日赠送和好友赠送，不计算信用点或加权收益。',
          result.clueExchangeMode === 'always-on'
            ? '线索产量按全程开启交流计算，计入已解锁且非涣散驻员的交流加速技能；不模拟集齐线索或交流开关，调度侧 Party Time 仍为空。'
            : '这份历史记录按线索交流关闭计算；重新演算后按全程开启交流计算线索产量。'
        ]),
    '回收站仅统计产出次数，不推算随机材料，不增加材料库存，也不计材料收益价值。',
    '这是离线模型估算，不是实测收益或实际排班可执行性的证明。图片导入不恢复本次计算参数和结果。'
  ]
}

async function loadImage(url) {
  const image = new Image()
  image.src = url
  await image.decode()
  return image
}

function imageTopWhitespace(image, scale, dark) {
  const probe = document.createElement('canvas')
  probe.width = image.naturalWidth
  probe.height = Math.min(image.naturalHeight, Math.ceil(16 * scale))
  const ctx = probe.getContext('2d')
  ctx.drawImage(image, 0, 0)
  const { data } = ctx.getImageData(0, 0, probe.width, probe.height)
  for (let y = 0; y < probe.height; y++) {
    for (let x = 0; x < probe.width; x++) {
      const i = (y * probe.width + x) * 4
      if (!data[i + 3]) continue
      const empty = dark
        ? Math.max(data[i], data[i + 1], data[i + 2]) <= 5
        : Math.min(data[i], data[i + 1], data[i + 2]) >= 250
      if (!empty) return Math.max(0, y - Math.ceil(2 * scale))
    }
  }
  return Math.max(0, probe.height - Math.ceil(2 * scale))
}

export async function renderIncomeImage(
  planImage,
  result,
  settings,
  plan,
  theme = 'light',
  roomBounds = {},
  exportDetails = {}
) {
  const sourceUrl = URL.createObjectURL(planImage)
  try {
    const metrics = incomeImageMetrics(result.summary, result.observedHours / 24)
    const [source, drone, ...icons] = await Promise.all([
      loadImage(sourceUrl),
      loadImage('/product/drone.svg'),
      ...metrics.map((row) => loadImage(row.icon))
    ])
    const width = source.naturalWidth
    const scale = width / 980
    const algorithmLines = incomeImageAlgorithmLines(settings)
    const days = result.observedHours / 24
    const canvas = document.createElement('canvas')
    canvas.width = width
    const ctx = canvas.getContext('2d')
    ctx.font = `${10 * scale}px sans-serif`
    const weightLines = algorithmLines
      .slice(1)
      .flatMap((line) =>
        incomeImageAnnotationLines({}, (text) => ctx.measureText(text).width / scale, 252, line)
      )
    const annotationLines = incomeImageAnnotationLines(
      exportDetails,
      (text) => ctx.measureText(text).width / scale,
      516,
      `${algorithmLines[0]} · ${number(days)} 天采样`
    )
    const orders = result.orderDistribution ?? incomeOrderDistribution(result.simulationReport)
    const annotationTop = Math.max(73 + weightLines.length * 14, orders?.other ? 100 : 87)
    const headerHeight = Math.ceil(
      Math.max(100, annotationTop + annotationLines.length * 16 + 3) * scale
    )
    const dark = theme === 'dark'
    const planTop = headerHeight - imageTopWhitespace(source, scale, dark)
    canvas.height = source.naturalHeight + planTop
    const foreground = dark ? '#eef2f8' : '#172338'
    ctx.fillStyle = dark ? '#000000' : '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source, 0, planTop)
    const droneTargets = incomeFacilities(plan)
    for (const room of settings.droneRoom ? [settings.droneRoom] : []) {
      const bounds = roomBounds[room]
      if (!bounds) continue
      const trading = droneTargets.find((target) => target.roomId === room)?.target === 'trading'
      const size = 20 * scale
      const x = bounds.x + bounds.width - size - 3 * scale
      const y = planTop + bounds.y + 2 * scale
      const badge = document.createElement('canvas')
      badge.width = badge.height = Math.ceil(size - 4 * scale)
      const badgeCtx = badge.getContext('2d')
      badgeCtx.drawImage(drone, 0, 0, badge.width, badge.height)
      badgeCtx.globalCompositeOperation = 'source-in'
      badgeCtx.fillStyle = trading ? '#8ccaff' : '#f7d86a'
      badgeCtx.fillRect(0, 0, badge.width, badge.height)
      ctx.drawImage(badge, x + 2 * scale, y + 2 * scale, size - 4 * scale, size - 4 * scale)
    }
    const write = (text, x, y, size, color = foreground, weight = 'normal') => {
      ctx.font = `${weight} ${size * scale}px sans-serif`
      ctx.fillStyle = color
      ctx.fillText(text, x * scale, y * scale)
    }
    write('日均加权收益', 28, 24, 13)
    const score = number(result.summary.totalScore82)
    let scoreSize = 38
    ctx.font = `bold ${scoreSize * scale}px sans-serif`
    while (ctx.measureText(score).width > 252 * scale && scoreSize > 18) {
      scoreSize--
      ctx.font = `bold ${scoreSize * scale}px sans-serif`
    }
    write(score, 26, 69, scoreSize, dark ? '#88e0b5' : '#237345', 'bold')
    weightLines.forEach((line, index) => {
      write(line, 28, 84 + index * 14, 10, dark ? '#a5b3ad' : '#687a70')
    })

    const stampColor = dark ? '#88cbb1' : '#35896c'
    const muted = dark ? '#a5b3ad' : '#687a70'
    write(orders?.expected ? '订单期望分布 · 原始档位' : '订单分布 · 原始档位', 302, 24, 12, muted)
    ctx.textAlign = 'right'
    write(orders ? `共 ${number(orders.total)} 单` : '暂无统计', 536, 24, 12, foreground, 'bold')
    ctx.textAlign = 'center'
    if (orders) {
      ctx.fillStyle = dark ? '#1c2d30' : '#f1f5f3'
      ctx.beginPath()
      ctx.roundRect(296 * scale, 33 * scale, 248 * scale, 54 * scale, 5 * scale)
      ctx.fill()
      orders.rows.forEach((row, index) => {
        const x = 338 + index * 82
        write(`${row.gold} 赤金`, x, 47, 10, muted)
        write(number(row.count), x, 66, 17, foreground, 'bold')
        write(orders.total ? `${number(row.ratio * 100)}%` : '—', x, 81, 10, stampColor)
      })
      if (orders.other) {
        write(
          `其他 ${number(orders.other)} 单 · ${number((orders.other / orders.total) * 100)}%`,
          420,
          100,
          9,
          muted
        )
      }
    } else {
      write('该记录未保存订单统计', 420, 65, 11, muted)
    }
    ctx.textAlign = 'left'

    write('日均产出', 570, 24, 12, muted)
    const colors = {
      exp: ['#f7d833', '#172338'],
      lmd: ['#087ead', '#ffffff'],
      gold: ['#f36c3e', '#ffffff'],
      fragment: ['#9d7940', '#ffffff'],
      lmdCost: ['#735456', '#ffffff'],
      orirockCost: ['#735456', '#ffffff'],
      deviceCost: ['#735456', '#ffffff'],
      orundum: ['#be4c51', '#ffffff'],
      recycle: ['#398d83', '#ffffff'],
      recruitment: ['#657385', '#ffffff'],
      clue: ['#756791', '#ffffff']
    }
    const withIcons = new Map(
      metrics.map((metric, index) => [metric.key, { ...metric, image: icons[index] }])
    )
    const pick = (keys) => keys.map((key) => withIcons.get(key)).filter(Boolean)
    const products = pick(['exp', 'lmd', 'gold'])
    const originium = pick(['fragment', 'orundum'])
    const costs = pick(['lmdCost', 'orirockCost', 'deviceCost'])
    const bottomHasRoom = !(withIcons.has('orirockCost') && withIcons.has('deviceCost'))
    if (originium[0]?.key === 'fragment' && bottomHasRoom) costs.unshift(originium.shift())
    const productVacancies = 3 - products.length
    products.push(...originium.splice(-productVacancies, productVacancies))
    const rows = [originium, products, pick(['clue', 'recruitment', 'recycle']), costs]
    rows
      .flatMap((metrics, row) =>
        metrics.map((metric, index) => ({ ...metric, row, column: index + (row === 0 ? 1 : 0) }))
      )
      .forEach((metric) => {
        const { column, row } = metric
        const x = 570 + column * 130
        const y = 4 + row * 24
        const [background, color] = colors[metric.key]
        ctx.fillStyle = background
        ctx.fillRect((x + 12) * scale, (y + 3) * scale, 110 * scale, 18 * scale)
        if (['recycle', 'recruitment', 'clue'].includes(metric.key)) {
          // Draw only the inner recognition symbol; replace the template's frame with a circle.
          ctx.save()
          ctx.translate((x + 12) * scale, (y + 12) * scale)
          ctx.scale((scale * 24) / 34, (scale * 24) / 34)
          ctx.beginPath()
          ctx.arc(0, 0, 16, 0, Math.PI * 2)
          ctx.fillStyle = '#2e2e2e'
          ctx.shadowColor = '#17233840'
          ctx.shadowBlur = 2 * scale
          ctx.shadowOffsetY = scale
          ctx.fill()
          ctx.shadowColor = 'transparent'
          if (metric.key === 'clue') {
            ctx.drawImage(metric.image, 15, 24, 42, 28, -12, -8, 24, 16)
          } else if (metric.key === 'recruitment') {
            ctx.drawImage(metric.image, 22, 20, 30, 35, -9, -10.5, 18, 21)
          } else {
            ctx.save()
            ctx.scale(0.55, 0.55)
            ctx.translate(-26, -28.5)
            ctx.beginPath()
            ctx.moveTo(26, 7)
            ctx.lineTo(45, 18)
            ctx.lineTo(45, 38)
            ctx.lineTo(26, 49)
            ctx.lineTo(5, 38)
            ctx.lineTo(5, 18)
            ctx.closePath()
            ctx.clip()
            ctx.drawImage(metric.image, 0, 0)
            ctx.restore()
          }
          ctx.beginPath()
          ctx.arc(0, 0, 15, 0, Math.PI * 2)
          ctx.strokeStyle = metric.key === 'recruitment' ? '#e8e8e8' : '#78aaa1'
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.restore()
        } else {
          ctx.drawImage(metric.image, x * scale, y * scale, 24 * scale, 24 * scale)
        }
        const negative = metric.daily < 0
        const value = `${compactIncomeNumber(Math.abs(metric.daily))}${metric.key === 'clue' ? '个' : metric.unit === '次' ? '次' : ''}`
        ctx.font = `${14 * scale}px sans-serif`
        ctx.fillStyle = color
        const baseline = (y + 17) * scale
        let valueX = (x + 30) * scale
        if (negative) {
          const digits = ctx.measureText('0')
          const center =
            baseline - (digits.actualBoundingBoxAscent - digits.actualBoundingBoxDescent) / 2
          ctx.fillRect(valueX, center - 0.5 * scale, 6 * scale, scale)
          valueX += 8 * scale
        }
        ctx.fillText(value, valueX, baseline, (negative ? 81 : 89) * scale)
      })
    annotationLines.forEach((line, index) => {
      write(line, 28, annotationTop + 16 + index * 16, 10, muted)
    })
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('收益图片生成失败'))),
        'image/jpeg',
        0.95
      )
    )
  } finally {
    URL.revokeObjectURL(sourceUrl)
  }
}
export function incomeImageAnnotationLines(details, measure, maxWidth, prefix = '') {
  const text = (key, limit) =>
    Array.from(typeof details?.[key] === 'string' ? details[key].trim() : '')
      .slice(0, limit)
      .join('')
  const author = text('author', 40).replace(/\s+/g, ' ')
  const remarks = text('remarks', 300)
  const paragraphs = [
    ...(prefix ? [prefix] : []),
    ...(author ? [`作者：${author}`] : []),
    ...(remarks ? [`备注：${remarks}`] : [])
  ].join('　')
  const lines = []
  if (!paragraphs) return lines
  for (const part of paragraphs.split(/\r?\n/)) {
    let line = ''
    for (const char of part) {
      if (line && measure(line + char) > maxWidth) {
        lines.push(line)
        line = ''
      }
      line += char
    }
    lines.push(line)
  }
  return lines
}
export function incomeImageAlgorithmLines(settings) {
  if (settings.weightMode !== 'custom' && settings.mowerAlgorithm !== -1) {
    return [incomeAlgorithmLabel(settings.mowerAlgorithm).split('（')[0].trim()]
  }
  const weights = incomeWeights(settings)
  return [
    '自定义',
    `经验 ${weights.exp} · 赤金 ${weights.gold} · 订单 ${weights.orders}`,
    `源石碎片 ${weights.fragments} · 合成玉 ${weights.orundum}`
  ]
}
export function compactIncomeNumber(value) {
  const magnitude = Math.abs(value)
  const unit = magnitude >= 1e6 ? ['m', 1e6] : magnitude >= 1e3 ? ['k', 1e3] : ['', 1]
  return `${Number((value / unit[1]).toFixed(unit[1] === 1 ? 2 : 1))}${unit[0]}`
}
export function incomeImageFilename(name, result) {
  const safe =
    Array.from(name?.trim() || '排班', (character) =>
      character.charCodeAt(0) < 32 || /[<>:"/\\|?*]/.test(character) ? '_' : character
    )
      .join('')
      .replace(/[. ]+$/g, '')
      .slice(0, 60) || '排班'
  const score = Number(result.summary.totalScore82.toFixed(2))
  const days = Number((result.observedHours / 24).toFixed(2))
  return `${safe}_日均收益${score}_${days}天.jpg`
}
export function downloadIncomeImage(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
