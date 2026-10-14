import {
  CALCULATOR_REVISION,
  MOWER_REFERENCE,
  incomeMetrics,
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
    `计算器 ${CALCULATOR_REVISION}（含本地完成时刻精度、全 Free 宿舍及赤金透支适配）；调度参考 Mower alpha ${MOWER_REFERENCE}，后续本体逻辑不自动同步。`,
    '回收站仅统计产出次数，不推算随机材料，不增加材料库存，也不计材料收益价值。',
    '这是离线模型估算，不是实测收益或实际排班可执行性的证明。图片导入不恢复本次计算参数和结果。'
  ]
}

export async function renderIncomeImage(planImage, result, settings, plan, label, theme = 'light') {
  const sourceUrl = URL.createObjectURL(planImage)
  try {
    const source = new Image()
    source.src = sourceUrl
    await source.decode()
    const width = source.naturalWidth
    const scale = width / 980
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    const margin = 28 * scale
    const lineHeight = 24 * scale
    const lines = incomeReportLines(result, settings, plan, label)
    const metrics = incomeMetrics(result.summary, result.observedHours / 24)
    const diagnostics = result.diagnostics.slice(0, 12).map((d) => d.message)
    ctx.font = `${12 * scale}px sans-serif`
    function wrap(text) {
      const chunks = []
      let line = ''
      for (const char of text) {
        if (ctx.measureText(line + char).width > width - 2 * margin) {
          chunks.push(line)
          line = ''
        }
        line += char
      }
      if (line) chunks.push(line)
      return chunks
    }
    const notes = lines.flatMap(wrap)
    const warnings = diagnostics.flatMap(wrap)
    const contributions = [
      ['经验', result.summary.scoreBreakdown.weightedExp],
      ['赤金及等价赤金', result.summary.scoreBreakdown.weightedGold],
      ['贸易', result.summary.scoreBreakdown.weightedOrders],
      ['碎片', result.summary.scoreBreakdown.weightedFragments],
      ['合成玉', result.summary.scoreBreakdown.weightedOrundum]
    ]
    canvas.width = width
    canvas.height = Math.ceil(
      source.naturalHeight +
        scale * 180 +
        lineHeight * (metrics.length + contributions.length + notes.length + warnings.length + 4)
    )
    ctx.fillStyle = theme === 'dark' ? '#000000' : '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source, 0, 0)
    let y = source.naturalHeight + 45 * scale
    const foreground = theme === 'dark' ? '#eef2f8' : '#172338'
    const write = (text, size = 13, x = margin) => {
      ctx.font = `${size * scale}px sans-serif`
      ctx.fillStyle = foreground
      ctx.fillText(text, x, y)
    }
    write('排班收益估算', 24)
    y += 35 * scale
    write(
      `日均加权产出 ${number(result.summary.totalScore82)} · 统计期 ${number(result.observedHours / 24)} 天`,
      16
    )
    y += lineHeight * 1.5
    write('产出项目')
    write('日均', 13, width * 0.45)
    write('统计期合计', 13, width * 0.7)
    y += lineHeight
    for (const metric of metrics) {
      write(metric.label)
      write(`${number(metric.daily)} ${metric.unit}`, 13, width * 0.45)
      write(`${number(metric.total)} ${metric.unit}`, 13, width * 0.7)
      y += lineHeight
    }
    y += lineHeight / 2
    write('日均加权产出构成', 16)
    y += lineHeight
    const max = Math.max(1, ...contributions.map(([, value]) => value))
    for (const [name, value] of contributions) {
      write(name, 12)
      ctx.fillStyle = '#45a68c'
      ctx.fillRect(
        width * 0.25,
        y - 12 * scale,
        (Math.max(0, value) / max) * width * 0.4,
        14 * scale
      )
      write(number(value), 12, width * 0.7)
      y += lineHeight
    }
    y += lineHeight / 2
    for (const line of notes) {
      write(line, 12)
      y += lineHeight
    }
    if (warnings.length) {
      y += lineHeight / 2
      write(`演算诊断（显示 ${diagnostics.length} / ${result.diagnostics.length} 条）`, 14)
      y += lineHeight
      for (const line of warnings) {
        write(line, 12)
        y += lineHeight
      }
    }
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('收益图片生成失败'))),
        'image/png'
      )
    )
  } finally {
    URL.revokeObjectURL(sourceUrl)
  }
}
export function downloadIncomeImage(blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'mower-income.png'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
