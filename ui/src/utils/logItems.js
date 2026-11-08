import droneIcon from '@/assets/log/drone.png?url&no-inline'
import { BASE_PRODUCT_COLORS, ORDER_COLORS } from './baseReport.js'

const resourceBase = import.meta.env.BASE_URL
const icon = (name) => `${resourceBase}depot/${encodeURIComponent(name)}.webp`
const product = (text, item, key) => ({
  text,
  icon: icon(item),
  lightColor: BASE_PRODUCT_COLORS.light[key],
  darkColor: BASE_PRODUCT_COLORS.dark[key]
})

const items = [
  product('源石碎片（固源岩）', '源石碎片', 'orundum'),
  product('源石碎片（装置）', '源石碎片', 'orundum'),
  product('基础作战记录', '基础作战记录', 'experience'),
  product('初级作战记录', '初级作战记录', 'experience'),
  product('中级作战记录', '中级作战记录', 'experience'),
  product('高级作战记录', '高级作战记录', 'experience'),
  product('龙门币订单', '龙门币', 'order'),
  product('合成玉订单', '合成玉', 'orundum'),
  product('龙门商法', '龙门币', 'order'),
  product('开采协力', '合成玉', 'orundum'),
  product('作战记录', '中级作战记录', 'experience'),
  product('作战录像', '中级作战记录', 'experience'),
  product('源石碎片', '源石碎片', 'orundum'),
  product('赤金', '赤金', 'gold'),
  product('合成玉', '合成玉', 'orundum'),
  {
    text: '无人机',
    icon: droneIcon,
    lightColor: BASE_PRODUCT_COLORS.light.special,
    darkColor: BASE_PRODUCT_COLORS.dark.special
  }
].sort((a, b) => b.text.length - a.text.length)
const definitions = new Map(items.map((item) => [item.text, item]))
const escapePattern = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const itemPattern = new RegExp(items.map((item) => escapePattern(item.text)).join('|'), 'gu')
const orderPattern =
  /当前为 (?<kind>但书(?:_\d+)?|龙舌兰|佩佩|可露希尔|漏单(?:_\d+)?|未知) 订单[，,]\s*订单价值为[：:]?\s*(?<price>\d+)/gu

function workshopItems(text, event) {
  if (event?.type !== 'workshop-result') return []
  const changes = event.changes
  if (
    !Array.isArray(changes) ||
    !changes.length ||
    changes.length > 512 ||
    changes.some(
      (item) =>
        !item ||
        typeof item.name !== 'string' ||
        !item.name ||
        item.name.length > 256 ||
        !Number.isSafeInteger(item.delta) ||
        !item.delta
    )
  )
    return []
  const label = '库存变化：'
  const suffix = changes
    .map((item) => `${item.name}${item.delta > 0 ? '+' : ''}${item.delta}`)
    .join('、')
  if (!text.endsWith(label + suffix)) return []
  const matches = []
  let cursor = text.length - suffix.length
  for (const item of changes) {
    const value = `${item.name}${item.delta > 0 ? '+' : ''}${item.delta}`
    matches.push({
      start: cursor,
      end: cursor + value.length,
      type: 'inventory-change',
      text: value,
      name: item.name,
      delta: item.delta,
      icon: icon(item.name)
    })
    cursor += value.length + 1
  }
  const prefix = text.slice(0, text.length - suffix.length - label.length)
  const names = [...new Set(changes.map((item) => item.name))].sort((a, b) => b.length - a.length)
  for (const match of prefix.matchAll(new RegExp(names.map(escapePattern).join('|'), 'gu'))) {
    matches.push({
      start: match.index,
      end: match.index + match[0].length,
      type: 'item',
      text: match[0],
      icon: icon(match[0])
    })
  }
  return matches
}

function reportedItems(text, event) {
  if (!['base-report', 'operation-drops'].includes(event?.type)) return []
  const values = event.items
  if (
    !Array.isArray(values) ||
    !values.length ||
    values.length > 512 ||
    values.some(
      (entry) =>
        !entry || typeof entry.name !== 'string' || !entry.name.trim() || entry.name.length > 256
    )
  )
    return []
  let body
  let parts
  if (event.type === 'operation-drops') {
    if (values.some((entry) => !Number.isSafeInteger(entry.count) || entry.count <= 0)) return []
    parts = values.map((entry) => `${entry.name}×${entry.count}`)
    body = '本次Mower刷理智掉落结果已计入库存：' + parts.join('、')
  } else {
    if (
      typeof event.date !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}$/u.test(event.date) ||
      values.length > 64 ||
      values.some(
        (entry) =>
          typeof entry.unit !== 'string' ||
          !entry.unit.trim() ||
          entry.unit.length > 32 ||
          typeof entry.item !== 'string' ||
          !entry.item.trim() ||
          entry.item.length > 256 ||
          (entry.value !== null && (!Number.isSafeInteger(entry.value) || entry.value < 0))
      )
    )
      return []
    const reportParts = (gap) =>
      values.map(
        (entry) =>
          `${entry.name}：${entry.value === null ? '未读出' : `${entry.value}${gap}${entry.unit}`}`
      )
    parts = reportParts(' ')
    body = `已保存 ${event.date} 的基报：\n` + parts.join('\n')
    if (!text.endsWith(body)) {
      parts = reportParts('')
      body = `已保存${event.date}基报：\n` + parts.join('\n')
    }
  }
  if (!text.endsWith(body)) return []
  let cursor = text.length - body.length
  const matches = []
  for (let index = 0; index < parts.length; index += 1) {
    const start = text.indexOf(parts[index], cursor)
    matches.push({
      type: 'item',
      start,
      end: start + parts[index].length,
      text: parts[index],
      icon: icon(values[index].item ?? values[index].name)
    })
    cursor = start + parts[index].length
  }
  return matches
}

export function logItemMatches(value, event = null) {
  const text = String(value ?? '')
  const matches = [...workshopItems(text, event), ...reportedItems(text, event)]
  for (const match of text.matchAll(orderPattern)) {
    const { kind, price } = match.groups
    const key = ['但书', '漏单'].includes(kind) ? `${kind}_${price}` : kind
    const name = kind.replace(/_\d+$/u, '')
    const namedOperator = ['但书', '龙舌兰', '佩佩', '可露希尔'].includes(kind)
    const label = namedOperator ? kind : `${kind} 订单`
    const start = match.index + '当前为 '.length
    matches.push({
      start,
      end: start + label.length,
      type: namedOperator ? 'order-operator' : 'item',
      text: label,
      ...(namedOperator ? { name } : { icon: icon('龙门币') }),
      lightColor: ORDER_COLORS.light[key] ?? ORDER_COLORS.light.未知订单,
      darkColor: ORDER_COLORS.dark[key] ?? ORDER_COLORS.dark.未知订单
    })
  }
  for (const match of text.matchAll(itemPattern)) {
    const start = match.index
    const end = start + match[0].length
    if (matches.some((item) => start < item.end && end > item.start)) continue
    matches.push({ ...definitions.get(match[0]), start, end, type: 'item' })
  }
  return matches.sort((a, b) => a.start - b.start)
}
