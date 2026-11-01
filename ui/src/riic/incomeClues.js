import { operatorFor, hasOperatorSkill } from './vendor/domain/operatorContext'
import {
  compileOperatorInventory,
  fullCatalogIdleInventory
} from './vendor/domain/operatorInventory'
import { matchesRiicIdentity } from './vendor/domain/riicIdentity'
import { buildRiicGlobalContext } from './vendor/engine/globalContext'
import { isSupportOperatorWorking } from './vendor/engine/supportFacilities/conditions'

// Reception formula, including passive rarity/promotion bonuses on exhausted occupants:
// https://prts.wiki/w/罗德岛基建/会客室#线索搜集速度
// 20 hours per clue; dormitories use the simulator's level-dependent maximum ambience.
export function clueEfficiency(config, phases, tenure = new Map()) {
  const ids = config.facilityOperatorIds.reception
  if (!config.facilities.reception || !ids.length) return 0
  const awake = ids.filter((id) => isSupportOperatorWorking(config, id))
  const ambience = config.facilities.dormitories.reduce((sum, level) => sum + level * 1000, 0)
  let bonus =
    5 +
    2 * config.facilities.reception +
    (ambience >= 4000 ? 15 : ambience >= 3000 ? 10 : ambience >= 2000 ? 5 : 0)
  let global
  const resources = () => (global ??= buildRiicGlobalContext(config))
  const controlWorking = (id) =>
    config.controlOperatorIds.includes(id) && isSupportOperatorWorking(config, id)
  for (const id of ids) {
    const operator = operatorFor(config, id)
    const phase = phases.get(id)
    if (!operator || phase === undefined) throw new Error(`缺少会客室干员练度：${id}`)
    bonus += ({ 4: 2, 5: 4, 6: 5 }[operator.rarity] ?? 0) + phase * 8
    if (!awake.includes(id)) continue
    bonus += 5
    for (const skill of operator.skills) {
      if (skill.roomType !== 'MEETING') continue
      const description = skill.description
      const fixed = description.match(/^进驻会客室时，线索搜集速度提升([\d.]+)%/)
      bonus += Number(fixed?.[1] ?? 0)
      if (description.includes('只有自身处于工作状态')) {
        if (awake.length === 1)
          bonus += Number(description.match(/搜集速度提升([\d.]+)%/)?.[1] ?? 0)
        continue
      }
      switch (skill.buffId) {
        case 'meet_spd&exchange[000]':
        case 'meet_spd&exchange[001]':
        case 'meet_spd&exchange[999]':
          bonus += 30
          break
        case 'meet_spd&cost_char[000]':
          if (awake.some((peer) => peer !== id)) bonus += 15
          break
        case 'meet_spd&bd[100]':
          if (awake.includes('char_358_lisa')) bonus += 30
          break
        case 'meet_spd&sami[000]':
        case 'meet_spd&sami[100]':
        case 'meet_spd&sami[110]': {
          const sami = skill.buffId === 'meet_spd&sami[000]'
          if (
            awake.some(
              (peer) =>
                peer !== id &&
                matchesRiicIdentity(
                  operatorFor(config, peer),
                  sami ? 'nationId' : 'groupId',
                  sami ? 'sami' : 'blacksteel'
                )
            )
          )
            bonus += sami ? 5 : skill.buffId === 'meet_spd&sami[100]' ? 15 : 20
          break
        }
        case 'meet_spd&sami[210]':
          if (
            awake.some(
              (peer) =>
                peer !== id && matchesRiicIdentity(operatorFor(config, peer), 'teamId', 'student')
            )
          )
            bonus += 20
          break
        case 'meet_spd&bd[000]':
        case 'meet_spd&bd[010]':
          if (awake.includes('char_2012_typhon')) bonus += 15
          break
        case 'meet_spd_ext&P[000]':
          if (
            config.facilityOperatorIds.dormitories.some((room) => room.includes('char_300_phenxi'))
          )
            bonus += 10
          break
        case 'meet_spd_bd[000]':
          if (
            controlWorking('char_456_ash') &&
            hasOperatorSkill(config, 'char_456_ash', 'control_mp_bd[000]')
          )
            bonus +=
              5 *
              config.controlOperatorIds.filter((peer) =>
                matchesRiicIdentity(operatorFor(config, peer), 'teamId', 'rainbow')
              ).length
          break
        case 'meet_spd_bd[001]':
          bonus += resources().monsterCuisine * 2
          break
        case 'meet_spd_bd[002]':
          bonus += Math.floor(resources().worldlyFireworks / 10)
          break
        case 'meet_spd&clue[000]':
          bonus += Math.max(0, config.facilities.office - 1) * 5
          break
        case 'meet_spd_hast[000]':
          bonus += Math.min(10, (tenure.get(id) ?? 0) * 2)
          break
        case 'meet_spd_notOwned_P[000]':
          if (controlWorking('char_1048_orchd2')) bonus += 10
          break
        default:
          // Clue exchange is assumed always active for production; clue-type probabilities do not change counts.
          if (!fixed && !/更容易获得|线索.*概率|线索倾向/.test(description))
            throw new Error(`尚未支持的会客室技能：${skill.name}（${skill.buffId}）`)
      }
    }
  }
  return 1 + bonus / 100
}

export function createClueObservation(warmupHours, inventory = fullCatalogIdleInventory()) {
  const compiled = compileOperatorInventory(inventory)
  if (!compiled.valid) throw new Error(compiled.diagnostics.map((item) => item.message).join('；'))
  const phases = new Map(
    compiled.operators.map((operator) => [operator.charId, operator.elitePhase])
  )
  const tenure = new Map()
  let positions = new Map()
  let progress = 0
  let warmupCompleted = 0
  const completed = () => Math.floor(progress + 1e-9)
  function advance(config, start, end) {
    if (end <= start) return
    const awake = config.facilities.reception
      ? config.facilityOperatorIds.reception.filter((id) => isSupportOperatorWorking(config, id))
      : []
    for (const id of tenure.keys()) if (!awake.includes(id)) tenure.delete(id)
    const duration = end - start
    const midTenure = new Map(awake.map((id) => [id, (tenure.get(id) ?? 0) + duration / 2]))
    // Split at Ines's five-hour cap so midpoint integration is exact on both linear pieces.
    const ines = 'char_4087_ines'
    const untilCap = 5 - (tenure.get(ines) ?? 0)
    if (awake.includes(ines) && untilCap > 1e-9 && untilCap < duration - 1e-9) {
      advance(config, start, start + untilCap)
      advance(config, start + untilCap, end)
      return
    }
    progress += (clueEfficiency(config, phases, midTenure) * duration) / 20
    for (const id of awake) tenure.set(id, (tenure.get(id) ?? 0) + duration)
  }
  return {
    observe(config, start, end, workHours) {
      const current = new Map(config.facilityOperatorIds.reception.map((id, index) => [id, index]))
      for (const id of tenure.keys()) {
        if (!current.has(id) || positions.get(id) !== current.get(id)) tenure.delete(id)
      }
      positions = current
      if (workHours) {
        for (const id of current.keys()) tenure.set(id, workHours.get(id) ?? 0)
      }
      const split = Math.min(end, warmupHours)
      if (start < warmupHours) {
        advance(config, start, split)
        warmupCompleted = completed()
      }
      advance(config, Math.max(start, warmupHours), end)
    },
    result() {
      return { completed: completed() - warmupCompleted, progress: progress - completed() }
    }
  }
}
