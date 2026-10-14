import groups from '../../../arknights_mower/data/riic/combinations.json'

export const builtinGroups = Object.freeze(
  groups.map((group) =>
    Object.freeze({
      ...group,
      note: group.note || '',
      core: Object.freeze(group.core),
      support: Object.freeze(group.support || []),
      accessory: Object.freeze(group.accessory || []),
      memberNotes: Object.freeze(group.memberNotes || {})
    })
  )
)
