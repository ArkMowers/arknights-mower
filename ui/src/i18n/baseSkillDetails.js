import { i18n } from '@/i18n'
import details from './data/baseSkillDetails.json'

const sourceFields = ['skillname', 'des', 'skillIcon', 'phase_level', 'roomType']
const skillsByIdAndName = new Map(
  Object.values(details.operators).flatMap((skills) =>
    skills.map((entry) => [`${entry.buffId}\0${entry.source.skillname}`, entry])
  )
)

export function baseSkillDisplayNameById(buffId, originalName) {
  return (
    skillsByIdAndName.get(`${buffId}\0${originalName}`)?.locales[i18n.global.locale.value]
      ?.skillname || originalName
  )
}

export function localizedBaseSkill(operatorOriginalName, skill) {
  const entry = details.operators[operatorOriginalName]?.find((candidate) =>
    sourceFields.every((field) => candidate.source[field] === skill[field])
  )
  return { ...skill, ...entry?.locales[i18n.global.locale.value] }
}

export function localizedBaseTerm(id, term) {
  if (!term) return term
  const entry = details.terms[id]
  const compatible =
    entry?.source.termName === term.termName && entry.source.description === term.description
  return { ...term, ...(compatible ? entry.locales[i18n.global.locale.value] : undefined) }
}
