import { computed } from 'vue'
import { useBasementSkill } from '@/stores/basementSkill'
import { removeRichTextTag } from '@/stores/richText2HTML'
import { annotateBasementSkills } from '@/utils/basementSkills'

const { skill, snapshot } = useBasementSkill()
const skillsByName = computed(
  () =>
    new Map(
      annotateBasementSkills(skill.value, snapshot.value).map((operator) => [
        operator.avatar,
        {
          ownership: operator.ownership,
          progression: operator.progression,
          skills: operator.childSkill.map((skill) => ({
            name: skill.skillname,
            facility: skill.roomType === '中枢' ? '控制中枢' : skill.roomType,
            unlock: skill.phase_level,
            status: skill.status,
            description: removeRichTextTag(skill.des).replace(/<[^>]*>/g, '')
          }))
        }
      ])
    )
)

const maximumSkillsByName = computed(
  () =>
    new Map(
      skill.value.map((operator) => {
        const slots = new Map()
        for (const entry of operator.child_skill) {
          if (
            !slots.has(entry.skill_key) ||
            slots.get(entry.skill_key).skill_level < entry.skill_level
          )
            slots.set(entry.skill_key, entry)
        }
        return [
          operator.name,
          {
            ownership: 'unknown',
            progression: '',
            skills: [...slots.values()].map((entry) => ({
              name: entry.skillname,
              facility: entry.roomType === '中枢' ? '控制中枢' : entry.roomType,
              unlock: entry.phase_level,
              status: '',
              description: removeRichTextTag(entry.des).replace(/<[^>]*>/g, '')
            }))
          }
        ]
      })
    )
)

export function getOperatorSkillDetails(name, { maximum = false, unpromoted = false } = {}) {
  const source = maximum ? maximumSkillsByName.value : skillsByName.value
  const details = source.get(name) ||
    source.get(name?.replace(/（[^）]+）$/, '')) || {
      ownership: 'unknown',
      progression: '',
      skills: []
    }
  return maximum && unpromoted
    ? { ...details, skills: details.skills.filter((entry) => /^精(?:英)?0\s/.test(entry.unlock)) }
    : details
}
