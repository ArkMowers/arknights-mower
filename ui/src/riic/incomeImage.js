import {
  CALCULATOR_REVISION,
  MOWER_REFERENCE,
  incomeImageMetrics,
  incomeFacilities,
  incomeWorkspace,
  incomeWeights
} from './income'

import { incomeInitialInventory } from './incomeCache'
import { incomeOrderDistribution } from './incomeOrders'
import { incomeAlgorithmLabel } from '@/utils/incomeSettings'

const number = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export const signedIncomeNumber = (value) => `${value > 0 ? '+' : ''}${number(value)}`

export function incomeValuationRows(summary) {
  const valuation = summary?.valuation
  if (!valuation) return []
  return [
    ['exp', '制造经验', '经验值'],
    ['gold', '制造赤金', '个'],
    ['orderLmd', '贸易龙门币', '龙门币'],
    ['virtualGold', '特殊订单溢价', '赤金等价个数'],
    ['fragments', '制造源石碎片', '个'],
    ['orundum', '贸易合成玉', '个']
  ]
    .map(([key, label, unit]) => ({
      key,
      label,
      unit,
      opening: valuation.opening.amounts[key] ?? 0,
      closing: valuation.closing.amounts[key] ?? 0,
      adjustment: valuation.adjustment.amounts[key] ?? 0
    }))
    .filter((row) =>
      [row.opening, row.closing, row.adjustment].some((value) => Math.abs(value) > 1e-8)
    )
}

export function incomeImageSummaryLine(result, settings) {
  const valuation = result.summary?.valuation
  return `${incomeImageAlgorithmLines(settings)[0]} · ${number(result.observedHours / 24)} 天采样${
    valuation
      ? ` · 含在制品估值 · 估值净调整（日均）${signedIncomeNumber(valuation.adjustment.score.daily)}`
      : ''
  }`
}

export function incomeReportLines(result, settings, plan, label) {
  const finite = settings.finiteInventory || result.inventoryMode === 'finite'
  const outputMode =
    result.simulationReport?.production?.assumptions.outputMode ??
    (finite ? 'settled' : 'potential')
  const initialMood =
    result.initialConditions?.fiammettaMorale == null
      ? '初始心情 24（受个人上限约束）'
      : `菲亚梅塔初始心情 ${result.initialConditions.fiammettaMorale}；其他干员从个人心情上限开始（未设置时为 24）`
  const provenance = result.modelProvenance
  const target = incomeFacilities(plan).find((f) => f.roomId === settings.droneRoom)
  const levels = Object.values(incomeWorkspace(plan).mainPlan.facilities)
    .filter((f) => f.level > 0)
    .map((f) => `${f.roomId}=${f.level}`)
    .join('；')
  return [
    `原图：${label}；二维码包含完整主副表和高级设置，可在 Mower「导入排班」中读取。`,
    `预热 ${settings.warmupDays} 天，不计入收益；统计 ${number(result.observedHours / 24)} 天，共 ${settings.warmupDays + settings.sampleDays} 天；随机种子 ${settings.seed}。`,
    `无人机：${target?.label ?? '不使用'}；${finite ? `有限库存：无外源收入，连续记账；${settings.allowGoldDebt ? '赤金可透支，其他材料缺料停产或暂停交付' : '缺料停产或暂停交付'}。` : '潜在产出：不受初始库存限制，不能视为可交付收入。'}`,
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
    `收益权重（${settings.weightMode === 'mower' ? incomeAlgorithmLabel(settings.mowerAlgorithm) : '本次自定义'}）：${Object.entries(
      incomeWeights(settings)
    )
      .map(([key, value]) => `${key}=${value}`)
      .join('；')}。加权产出不是龙门币结算额。`,
    ...(result.summary?.valuation
      ? [
          `日均加权收益含在制品估值：已完成产出日均 ${number(result.summary.valuation.completedScore.daily)}；在制品期初加权估值 ${number(result.summary.valuation.opening.score.total)}，期末 ${number(result.summary.valuation.closing.score.total)}，净调整 ${signedIncomeNumber(result.summary.valuation.adjustment.score.total)}，日均贡献 ${signedIncomeNumber(result.summary.valuation.adjustment.score.daily)}。`,
          `在制品按采样边界的生产进度及技能快照估值；贸易订单最终完成奖励可能变化。估值不进入库存，也不触发库存副表。${outputMode === 'settled' ? '产物数量为采样期产出且已收取量' : '产物数量为采样期完成量'}。预热期完成后在采样期领取的成品保留在库存收支中，不计入采样收益。`
        ]
      : []),
    `模型假设：理想跑单；部分读房与调度耗时已建模，其余点击识别耗时忽略；宿舍氛围按等级上限。`,
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
    const contentBottom = Math.max(100, 28 + Math.ceil(metrics.length / 3) * 24)
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
      incomeImageSummaryLine(result, settings)
    )
    const orders = result.orderDistribution ?? incomeOrderDistribution(result.simulationReport)
    const annotationTop = Math.max(73 + weightLines.length * 14, orders?.other ? 100 : 87)
    const headerHeight = Math.ceil(
      Math.max(contentBottom, annotationTop + annotationLines.length * 16 + 3) * scale
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
    write(result.summary.valuation ? '日均加权收益（含在制品估值）' : '日均加权收益', 28, 24, 13)
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
    write('订单分布 · 原始档位', 302, 24, 12, muted)
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
      orundum: ['#be4c51', '#ffffff'],
      recycle: ['#398d83', '#ffffff'],
      recruitment: ['#657385', '#ffffff'],
      clue: ['#756791', '#ffffff']
    }
    const order = ['exp', 'lmd', 'gold', 'fragment', 'orundum', 'clue', 'recruitment', 'recycle']
    metrics
      .map((metric, index) => ({ ...metric, image: icons[index] }))
      .sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key))
      .forEach((metric, index) => {
        const x = 570 + (index % 3) * 130
        const y = 28 + Math.floor(index / 3) * 24
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
        const value = `${compactIncomeNumber(metric.daily)}${metric.key === 'clue' ? '个' : metric.unit === '次' ? '次' : ''}`
        ctx.font = `${14 * scale}px sans-serif`
        ctx.fillStyle = color
        ctx.fillText(value, (x + 30) * scale, (y + 17) * scale, 89 * scale)
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
