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

export function getOperatorSkillDetails(name) {
  return (
    skillsByName.value.get(name) ||
    skillsByName.value.get(name?.replace(/（[^）]+）$/, '')) || {
      ownership: 'unknown',
      progression: '',
      skills: []
    }
  )
}
