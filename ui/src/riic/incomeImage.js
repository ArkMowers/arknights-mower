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
    `推断等级：${levels}。`,
    `计算器 ${CALCULATOR_REVISION}（含本地完成时刻精度、全 Free 宿舍、赤金透支、制造成本观察及心情记录适配）；调度参考 Mower alpha ${MOWER_REFERENCE}，后续本体逻辑不自动同步。`,
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
  label,
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
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = source.naturalHeight + Math.ceil((155 + metrics.length * 55) * scale)
    const ctx = canvas.getContext('2d')
    const dark = theme === 'dark'
    const foreground = dark ? '#eef2f8' : '#172338'
    ctx.fillStyle = dark ? '#000000' : '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source, 0, 0)
    for (const room of result.droneRooms ?? []) {
      const bounds = roomBounds[room]
      if (!bounds) continue
      const size = 18 * scale
      const x = bounds.x + bounds.width - size - 3 * scale
      const y = bounds.y + 2 * scale
      ctx.fillStyle = '#e2f4e6'
      ctx.fillRect(x, y, size, size)
      ctx.drawImage(drone, x + 2 * scale, y + 2 * scale, size - 4 * scale, size - 4 * scale)
    }
    const margin = 28 * scale
    let y = source.naturalHeight + 42 * scale
    const write = (text, size = 15, x = margin) => {
      ctx.font = `${size * scale}px sans-serif`
      ctx.fillStyle = foreground
      ctx.fillText(text, x, y)
    }
    let title = `${label?.trim() || '排班'} · 收益估算`
    ctx.font = `${24 * scale}px sans-serif`
    while (ctx.measureText(title).width > width - margin * 2 && title.length > 8)
      title = title.slice(0, -2) + '…'
    write(title, 24)
    y += 34 * scale
    write(
      `日均加权产出 ${number(result.summary.totalScore82)} · 统计期 ${number(result.observedHours / 24)} 天`,
      16
    )
    y += 36 * scale
    write('产物')
    write('日均', 15, width * 0.45)
    write('统计期合计', 15, width * 0.72)
    y += 18 * scale
    metrics.forEach((metric, index) => {
      ctx.fillStyle = dark ? '#17212a' : '#f2f6f4'
      ctx.fillRect(margin, y, width - margin * 2, 49 * scale)
      ctx.drawImage(icons[index], margin + 9 * scale, y + 3 * scale, 43 * scale, 43 * scale)
      y += 31 * scale
      const value = (n) => `${metric.signed && n > 0 ? '+' : ''}${number(n)} ${metric.unit}`
      write(value(metric.daily), 17, width * 0.45)
      write(value(metric.total), 17, width * 0.72)
      y += 24 * scale
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
