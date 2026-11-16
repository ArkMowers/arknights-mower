import { importMowerJson } from '@/riic/vendor/workbench/compat/mowerJson'

export function planRecommendationConditions(plan = {}, levels = {}) {
  if (!Object.keys(plan).length && !Object.keys(levels).length) return {}
  const workspace = importMowerJson(
    JSON.stringify({
      default: 'plan1',
      plan1: plan,
      facility_levels: levels,
      conf: {},
      backup_plans: []
    })
  )
  const facilities = Object.values(workspace.mainPlan.facilities).filter((room) => room.level > 0)
  const result = {}
  const output = facilities.filter((room) =>
    ['trading', 'manufacture', 'power'].includes(room.type)
  )
  if (output.length) {
    result.trade = output.filter((room) => room.type === 'trading').length
    result.factories = output.filter((room) => room.type === 'manufacture').length
    result.power = output.filter((room) => room.type === 'power').length
    const factories = output.filter((room) => room.type === 'manufacture')
    const products = new Set(factories.map((room) => room.product).filter(Boolean))
    if (products.size) result.formulaKinds = products.size
    result.goldLines = factories.filter((room) => room.product === 'gold').length
  }
  const dorms = facilities.filter((room) => room.type === 'dormitory')
  if (dorms.length) {
    result.dormLevel = Math.max(...dorms.map((room) => room.level))
    result.dormLevels = dorms.reduce((sum, room) => sum + room.level, 0)
  }
  const meeting = workspace.mainPlan.facilities.meeting
  const office = workspace.mainPlan.facilities.contact
  if (meeting.level) result.reception = meeting.level
  if (office.level) result.recruits = office.level - 1
  if (result.power === 3) result.dormLayout = '三电 · 40%'
  else if (result.power === 2 && dorms.length === 4) {
    const layout = dorms
      .map((room) => room.level)
      .sort((a, b) => b - a)
      .join('')
    if (['1111', '2111', '3111'].includes(layout))
      result.dormLayout = `二电 · ${layout}宿舍 · ${layout === '1111' ? 28 : 30}%`
  }
  return result
}
