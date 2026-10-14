import {
  CALCULATOR_REVISION,
  MOWER_REFERENCE,
  incomeImageMetrics,
  incomeFacilities,
  incomeWorkspace,
  incomeWeights
} from './income'

import { incomeInitialInventory } from './incomeCache'
import { incomeAlgorithmLabel } from '@/utils/incomeSettings'

const number = (value) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export function incomeReportLines(result, settings, plan, label) {
  const finite = settings.finiteInventory || result.inventoryMode === 'finite'
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
    `干员：${settings.operatorMode === 'cache' ? '森空岛缓存的实际拥有和练度' : settings.operatorMode === 'custom' ? '按本次填写的拥有和练度' : '全部干员满配假设'}；初始心情 24（受个人上限约束）；孑精零 ${settings.jayeElite0 ? '开启' : '关闭'}。`,
    `未完成训练计划：${settings.masteryPlanPresent ? '有' : '无'}，整段演算保持此条件，不模拟训练完成。`,
    `收益权重（${settings.weightMode === 'mower' ? incomeAlgorithmLabel(settings.mowerAlgorithm) : '本次自定义'}）：${Object.entries(
      incomeWeights(settings)
    )
      .map(([key, value]) => `${key}=${value}`)
      .join('；')}。加权产出不是龙门币结算额。`,
    `模型假设：理想跑单；部分读房与调度耗时已建模，其余点击识别耗时忽略；宿舍氛围按等级上限。`,
    `本次设施等级（优先使用排班保存值，未设置时推断）：${levels}。`,
    `计算器 ${CALCULATOR_REVISION}（含本地完成时刻精度、全 Free 宿舍、赤金透支、制造成本观察及心情记录适配）；调度参考 Mower alpha ${MOWER_REFERENCE}，后续本体逻辑不自动同步。`,
    '公招刷新按办公室驻员、心情与已解锁技能计算联络产出；初始进度为零，预热进度延续但预热完成次数不计。假设及时使用刷新次数，不模拟存满 3 次停工，不计入加权收益。',
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

export async function renderIncomeImage(
  planImage,
  result,
  settings,
  plan,
  theme = 'light',
  roomBounds = {}
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
    const headerHeight = Math.ceil(
      Math.max(145, 28 + Math.ceil(metrics.length / 2) * 36 + 8) * scale
    )
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = source.naturalHeight + headerHeight
    const ctx = canvas.getContext('2d')
    const dark = theme === 'dark'
    const foreground = dark ? '#eef2f8' : '#172338'
    ctx.fillStyle = dark ? '#000000' : '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source, 0, headerHeight)
    const droneTargets = incomeFacilities(plan)
    for (const room of result.droneRooms ?? []) {
      const bounds = roomBounds[room]
      if (!bounds) continue
      const trading = droneTargets.find((target) => target.roomId === room)?.target === 'trading'
      const size = 20 * scale
      const x = bounds.x + bounds.width - size - 3 * scale
      const y = headerHeight + bounds.y + 2 * scale
      const badge = document.createElement('canvas')
      badge.width = badge.height = Math.ceil(size - 4 * scale)
      const badgeCtx = badge.getContext('2d')
      badgeCtx.drawImage(drone, 0, 0, badge.width, badge.height)
      badgeCtx.globalCompositeOperation = 'source-in'
      badgeCtx.fillStyle = trading ? '#2587dc' : '#e4ad08'
      badgeCtx.fillRect(0, 0, badge.width, badge.height)
      ctx.fillStyle = trading ? '#e5f2ff' : '#fff5cf'
      ctx.fillRect(x, y, size, size)
      ctx.drawImage(badge, x + 2 * scale, y + 2 * scale, size - 4 * scale, size - 4 * scale)
    }
    const write = (text, x, y, size, color = foreground, weight = 'normal') => {
      ctx.font = `${weight} ${size * scale}px sans-serif`
      ctx.fillStyle = color
      ctx.fillText(text, x * scale, y * scale)
    }
    write('日均加权收益', 28, 37, 17)
    const score = number(result.summary.totalScore82)
    let scoreSize = 38
    ctx.font = `bold ${scoreSize * scale}px sans-serif`
    while (ctx.measureText(score).width > 252 * scale && scoreSize > 18) {
      scoreSize--
      ctx.font = `bold ${scoreSize * scale}px sans-serif`
    }
    write(score, 26, 84, scoreSize, dark ? '#88e0b5' : '#237345', 'bold')
    const algorithmLines = incomeImageAlgorithmLines(settings)
    algorithmLines.forEach((line, index) => {
      const size = algorithmLines.length === 1 ? 12 : index === 0 ? 11 : 10
      const y = algorithmLines.length === 1 ? 112 : 104 + index * 15
      ctx.font = `${size * scale}px sans-serif`
      ctx.fillStyle = dark ? '#a5b3ad' : '#687a70'
      ctx.fillText(line, 28 * scale, y * scale, 252 * scale)
    })

    const stampColor = dark ? '#88cbb1' : '#35896c'
    ctx.strokeStyle = stampColor
    ctx.lineWidth = 2 * scale
    ctx.strokeRect(302 * scale, 27 * scale, 234 * scale, 91 * scale)
    ctx.lineWidth = scale
    ctx.strokeRect(307 * scale, 32 * scale, 224 * scale, 81 * scale)
    ctx.textAlign = 'center'
    const days = result.observedHours / 24
    write('收益演算验证', 419, 57, 20, stampColor, 'bold')
    write(`演算 ${number(settings.warmupDays + days)} 天`, 419, 81, 16, stampColor)
    write(
      `预热 ${number(settings.warmupDays)} 天 · 采样 ${number(days)} 天`,
      419,
      102,
      12,
      stampColor
    )
    ctx.textAlign = 'left'

    write('日均产出', 570, 20, 12, dark ? '#a5b3ad' : '#687a70')
    const colors = {
      exp: ['#f7d833', '#172338'],
      lmd: ['#087ead', '#ffffff'],
      gold: ['#f36c3e', '#ffffff'],
      fragment: ['#9d7940', '#ffffff'],
      orundum: ['#be4c51', '#ffffff'],
      recycle: ['#398d83', '#ffffff'],
      recruitment: ['#657385', '#ffffff']
    }
    const order = ['exp', 'lmd', 'gold', 'fragment', 'orundum', 'recycle', 'recruitment']
    metrics
      .map((metric, index) => ({ ...metric, image: icons[index] }))
      .sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key))
      .forEach((metric, index) => {
        const x = 570 + (index % 2) * 192
        const y = 28 + Math.floor(index / 2) * 36
        const [background, color] = colors[metric.key]
        ctx.fillStyle = background
        ctx.fillRect((x + 18) * scale, (y + 4) * scale, 151 * scale, 26 * scale)
        if (metric.key === 'recycle' || metric.key === 'recruitment') {
          // Draw only the inner recognition symbol; replace the template's frame with a circle.
          ctx.save()
          ctx.translate((x + 17) * scale, (y + 17) * scale)
          ctx.scale(scale, scale)
          ctx.beginPath()
          ctx.arc(0, 0, 16, 0, Math.PI * 2)
          ctx.fillStyle = '#2e2e2e'
          ctx.shadowColor = '#17233840'
          ctx.shadowBlur = 2 * scale
          ctx.shadowOffsetY = scale
          ctx.fill()
          ctx.shadowColor = 'transparent'
          if (metric.key === 'recruitment') {
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
          ctx.drawImage(metric.image, x * scale, y * scale, 34 * scale, 34 * scale)
        }
        const value = `${metric.signed && metric.daily > 0 ? '+' : ''}${compactIncomeNumber(metric.daily)}${metric.unit === '次' ? '次' : ''}`
        write(value, x + 42, y + 24, 18, color)
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
    (name?.trim() || '排班')
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
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
