import { operatorFor, hasOperatorSkill } from './vendor/domain/operatorContext'
import { matchesRiicIdentity } from './vendor/domain/riicIdentity'
import { buildRiicGlobalContext } from './vendor/engine/globalContext'
import { isSupportOperatorWorking } from './vendor/engine/supportFacilities/conditions'

// building_data: humanResourceLimit / hireData.phases[].resSpeed = 43200 seconds.
// https://github.com/Kengxxiao/ArknightsGameData/blob/17759cc8cdf37388414145d16262a3a06f3ab25e/zh_CN/gamedata/excel/building_data.json
// Empty offices stop; exhausted occupants retain only baseline contact progress.
// https://prts.wiki/w/罗德岛基建/办公室
export function recruitmentEfficiency(config) {
  if (!config.facilities.office || !config.facilityOperatorIds.office.length) return 0
  let bonus = 0
  const working = (id) => isSupportOperatorWorking(config, id)
  for (const id of config.facilityOperatorIds.office.filter(working)) {
    bonus += 5
    for (const skill of operatorFor(config, id)?.skills ?? []) {
      if (skill.roomType !== 'HIRE') continue
      const fixed = skill.description.match(/^进驻人力办公室时，人脉资源的联络速度\+([\d.]+)%/)
      bonus += Number(fixed?.[1] ?? 0)
      switch (skill.buffId) {
        case 'hire_spd_cost&extra[000]':
          bonus += Math.max(0, config.facilities.office - 1) * 10
          break
        case 'hire_spd_dorm&lv[000]':
        case 'hire_spd_dorm&lv[010]':
          bonus +=
            config.facilities.dormitories.reduce((sum, level) => sum + level, 0) *
            (skill.buffId === 'hire_spd_dorm&lv[010]' ? 2 : 1)
          break
        case 'hire_spd_tag[000]':
          bonus += Math.min(5, buildRiicGlobalContext(config).eliteFacilities) * 4
          break
        case 'hire_spd_cost&char[001]':
          if (config.controlOperatorIds.includes('char_1045_svash2') && working('char_1045_svash2'))
            bonus += 10
          break
        case 'hire_spd_blitz[000]': {
          const control = config.controlOperatorIds
          const intelligence =
            control.includes('char_456_ash') &&
            working('char_456_ash') &&
            hasOperatorSkill(config, 'char_456_ash', 'control_mp_bd[000]')
              ? control.filter((peer) => {
                  const operator = operatorFor(config, peer)
                  return operator && matchesRiicIdentity(operator, 'teamId', 'rainbow')
                }).length
              : 0
          bonus += (intelligence + buildRiicGlobalContext(config).ursuSpecialDrink) * 5
          break
        }
        case 'hire_spd_bd_n1_n1[200]':
        case 'hire_spd_bd_n1_n1[300]':
        case 'hire_spd_bd_n1[000]':
          break
        default:
          if (!fixed) throw new Error(`尚未支持的办公室技能：${skill.name}（${skill.buffId}）`)
      }
    }
  }
  return 1 + bonus / 100
}

// Observe the existing intervals without adding dispatches or changing production.
export function createRecruitmentObservation(warmupHours) {
  let progress = 0
  let warmupCompleted = 0
  const completed = () => Math.floor(progress + 1e-9)
  return {
    observe(config, start, end) {
      const speed = recruitmentEfficiency(config) / 12
      const warmupDuration = Math.max(0, Math.min(end, warmupHours) - start)
      progress += speed * warmupDuration
      if (start < warmupHours) warmupCompleted = completed()
      progress += speed * (end - start - warmupDuration)
    },
    result() {
      return { completed: completed() - warmupCompleted, progress: progress - completed() }
    }
  }
}
