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
import { i18n } from '@/i18n'
import { incomeResourceLabel, incomeWeightLabel } from '@/i18n/income'

const { t, locale } = i18n.global

const number = (value) => Number(value).toLocaleString(locale.value, { maximumFractionDigits: 2 })
export function incomeReportLines(result, settings, plan, label) {
  const finite = settings.finiteInventory || result.inventoryMode === 'finite'
  const initialMood =
    result.initialConditions?.fiammettaMorale == null
      ? t('income.initialMorale')
      : t('income.initialFiammettaMorale', { value: result.initialConditions.fiammettaMorale })
  const provenance = result.modelProvenance
  const target = incomeFacilities(plan).find((f) => f.roomId === settings.droneRoom)
  const levels = Object.values(incomeWorkspace(plan).mainPlan.facilities)
    .filter((f) => f.level > 0)
    .map((f) => `${f.roomId}=${f.level}`)
    .join('；')
  return [
    t('income.sourceImage', { label }),
    t('income.sampleSummary', {
      warmup: settings.warmupDays,
      sample: number(result.observedHours / 24),
      total: settings.warmupDays + settings.sampleDays,
      seed: settings.seed
    }),
    t('income.droneInventorySummary', {
      target: target?.label ?? t('plans.noDrones'),
      inventory: finite
        ? t('income.finiteInventorySummary', {
            shortage: t(settings.allowGoldDebt ? 'plans.goldDebtHelp' : 'plans.shortageHelp')
          })
        : t('income.potentialInventorySummary')
    }),
    ...(finite
      ? [
          t('income.initialInventorySummary', {
            source: t(
              settings.inventorySource === 'cache'
                ? 'income.cachedInventorySource'
                : 'plans.manualInventory'
            ),
            inventory:
              Object.entries(incomeInitialInventory(settings))
                .map(([key, value]) => `${incomeResourceLabel(key)}=${value}`)
                .join('; ') || t('income.allZero')
          })
        ]
      : []),
    ...(finite
      ? [
          t('income.goldBalanceSummary', {
            initial: number(result.goldInventory.initial),
            opening: number(result.goldInventory.sampleOpening),
            closing: number(result.goldInventory.closing)
          })
        ]
      : []),
    ...(settings.operatorMode === 'cache' || (finite && settings.inventorySource === 'cache')
      ? [
          t('income.cacheDateSummary', {
            date: settings.cacheObservedAt
              ? new Date(settings.cacheObservedAt * 1000).toLocaleString(locale.value)
              : t('income.noCacheDate')
          })
        ]
      : []),
    t('income.operatorAssumptions', {
      source: t(
        settings.operatorMode === 'cache'
          ? 'income.cachedOperatorsSource'
          : settings.operatorMode === 'custom'
            ? 'income.manualOperatorsSource'
            : 'income.maximumOperatorsSource'
      ),
      initialMorale: initialMood,
      jaye: t(settings.jayeElite0 ? 'income.enabled' : 'income.disabled')
    }),
    settings.masteryPlanPresent === undefined
      ? t('income.noTrainingAssumption')
      : t('income.historicalTrainingAssumption', {
          present: t(settings.masteryPlanPresent ? 'income.present' : 'income.absent')
        }),
    t('income.goldEquivalentAssumption'),
    t('income.weightAssumptions', {
      source:
        settings.weightMode === 'mower'
          ? incomeAlgorithmLabel(settings.mowerAlgorithm)
          : t('plans.customWeights'),
      weights: Object.entries(incomeWeights(settings))
        .map(([key, value]) => `${incomeWeightLabel(key)}=${value}`)
        .join('; ')
    }),
    t('income.modelAssumptions'),
    provenance?.moodControlStrategyVersion
      ? provenance.moodControlStrategyVersion === 'ordinary-threshold-v1'
        ? t('income.thresholdStrategyAssumption', {
            version: provenance.moodControlStrategyVersion,
            enabled: t(provenance.predictiveMoodControl ? 'income.enabled' : 'income.disabled')
          })
        : t('income.strategyAssumption', {
            version: provenance.moodControlStrategyVersion,
            enabled: t(provenance.predictiveMoodControl ? 'income.enabled' : 'income.disabled')
          })
      : t('income.noStrategyAssumption'),
    t('income.facilityLevelsAssumption', { levels }),
    provenance
      ? t('income.provenanceAssumption', {
          base: provenance.calculatorBaseRevision,
          sync: provenance.calculatorSyncRevision,
          mowerBase: provenance.mowerBaseReference,
          mowerChecked: provenance.mowerCheckedRevision
        })
      : t('income.legacyProvenanceAssumption', {
          calculator: CALCULATOR_REVISION,
          mower: MOWER_REFERENCE
        }),
    t('income.recruitmentAssumption'),
    ...(result.summary?.clueCount == null
      ? [t('income.noClueAssumption')]
      : [
          t('income.clueAssumption'),
          result.clueExchangeMode === 'always-on'
            ? t('income.clueExchangeAssumption')
            : t('income.legacyClueExchangeAssumption')
        ]),
    t('income.recyclingAssumption'),
    t('income.offlineAssumption')
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
      t('income.sampleAnnotation', { algorithm: algorithmLines[0], days: number(days) })
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
    write(t('income.dailyWeightedIncome'), 28, 24, 13)
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
    write(t('income.orderDistribution'), 302, 24, 12, muted)
    ctx.textAlign = 'right'
    write(
      orders ? t('income.totalOrders', { count: number(orders.total) }) : t('income.noStatistics'),
      536,
      24,
      12,
      foreground,
      'bold'
    )
    ctx.textAlign = 'center'
    if (orders) {
      ctx.fillStyle = dark ? '#1c2d30' : '#f1f5f3'
      ctx.beginPath()
      ctx.roundRect(296 * scale, 33 * scale, 248 * scale, 54 * scale, 5 * scale)
      ctx.fill()
      orders.rows.forEach((row, index) => {
        const x = 338 + index * 82
        write(t('income.orderGold', { count: row.gold }), x, 47, 10, muted)
        write(number(row.count), x, 66, 17, foreground, 'bold')
        write(orders.total ? `${number(row.ratio * 100)}%` : '—', x, 81, 10, stampColor)
      })
      if (orders.other) {
        write(
          t('income.otherOrders', {
            count: number(orders.other),
            percent: number((orders.other / orders.total) * 100)
          }),
          420,
          100,
          9,
          muted
        )
      }
    } else {
      write(t('income.noSavedOrders'), 420, 65, 11, muted)
    }
    ctx.textAlign = 'left'

    write(t('income.dailyOutput'), 570, 24, 12, muted)
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
        const value = `${compactIncomeNumber(metric.daily)}${metric.key === 'clue' ? t('income.itemUnit') : ['recycle', 'recruitment'].includes(metric.key) ? t('income.countUnit') : ''}`
        ctx.font = `${14 * scale}px sans-serif`
        ctx.fillStyle = color
        ctx.fillText(value, (x + 30) * scale, (y + 17) * scale, 89 * scale)
      })
    annotationLines.forEach((line, index) => {
      write(line, 28, annotationTop + 16 + index * 16, 10, muted)
    })
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error(t('income.imageFailed')))),
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
    ...(author ? [t('income.imageAuthor', { author })] : []),
    ...(remarks ? [t('income.imageRemarks', { remarks })] : [])
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
    t('income.custom'),
    t('income.imageWeights', {
      experience: weights.exp,
      gold: weights.gold,
      orders: weights.orders
    }),
    t('income.imageFragmentWeights', { fragments: weights.fragments, orundum: weights.orundum })
  ]
}
export function compactIncomeNumber(value) {
  const magnitude = Math.abs(value)
  const unit = magnitude >= 1e6 ? ['m', 1e6] : magnitude >= 1e3 ? ['k', 1e3] : ['', 1]
  return `${Number((value / unit[1]).toFixed(unit[1] === 1 ? 2 : 1))}${unit[0]}`
}
export function incomeImageFilename(name, result) {
  const safe =
    Array.from(name?.trim() || t('plans.planFallback'), (character) =>
      character.charCodeAt(0) < 32 || /[<>:"/\\|?*]/.test(character) ? '_' : character
    )
      .join('')
      .replace(/[. ]+$/g, '')
      .slice(0, 60) || t('plans.planFallback')
  const score = Number(result.summary.totalScore82.toFixed(2))
  const days = Number((result.observedHours / 24).toFixed(2))
  return t('income.imageFilename', { name: safe, score, days })
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
