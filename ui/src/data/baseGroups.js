import groups from '../../../arknights_mower/data/riic/combinations.json'
import singles from '../../../arknights_mower/data/riic/single_recommendations.json'

function freezeGroups(entries) {
  return Object.freeze(
    entries.map((group) =>
      Object.freeze({
        ...group,
        variants: freezeGroups(group.variants || []),
        note: group.note || '',
        core: Object.freeze(group.core),
        support: Object.freeze(group.support || []),
        accessory: Object.freeze(group.accessory || []),
        memberNotes: Object.freeze(group.memberNotes || {}),
        placements: Object.freeze(group.placements || {}),
        recommended: group.recommended ? Object.freeze(group.recommended) : undefined,
        defaultAccessories: group.defaultAccessories
          ? Object.freeze(group.defaultAccessories)
          : undefined
      })
    )
  )
}
export const builtinGroups = freezeGroups(
  groups.filter((group) => group.id !== 'builtin-run-order')
)
export const singleRecommendations = freezeGroups([
  {
    ...groups.find((group) => group.id === 'builtin-run-order'),
    kind: 'roster',
    facility: '贸易',
    coreTitle: '跑单干员'
  },
  ...singles
])
export const allGroupOptions = Object.freeze(
  builtinGroups.flatMap((group) => [group, ...group.variants])
)
