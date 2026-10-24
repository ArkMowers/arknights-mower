/** Stable public entry point; each new support mechanism owns its rules separately. */
export { supportSkillConditionMatches } from './supportFacilities/conditions'
export { evaluateNewContactAndClueSkills } from './supportFacilities/contactAndClue'
export { RECYCLE_RULES, evaluateRecycleEfficiency, type RecycleEfficiency } from './supportFacilities/recycle'
export { WORKSHOP_FORMULAS, evaluateHomeboundByproduct } from './supportFacilities/workshop'
