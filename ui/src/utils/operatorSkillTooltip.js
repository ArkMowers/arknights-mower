import { computed } from 'vue'
import { useBasementSkill } from '@/stores/basementSkill'
import { removeRichTextTag } from '@/stores/richText2HTML'

const { skill } = useBasementSkill()
const skillsByName = computed(
  () => new Map(skill.value.map((operator) => [operator.name, operator.child_skill]))
)

export function getOperatorSkillDetails(name) {
  const skills =
    skillsByName.value.get(name) || skillsByName.value.get(name?.replace(/（[^）]+）$/, '')) || []
  return skills.map((skill) => ({
    name: skill.skillname,
    facility: skill.roomType === '中枢' ? '控制中枢' : skill.roomType,
    unlock: skill.phase_level,
    description: removeRichTextTag(skill.des).replace(/<[^>]*>/g, '')
  }))
}
