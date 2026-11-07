// Reduced from a schedule whose backup removes the shared groups of cross-covering primaries.
export function backupWarningPlan() {
  const slot = (agent, group, replacement, group_bindings = []) => ({
    agent,
    group,
    replacement,
    group_bindings
  })
  const shared = [
    slot('结城理', 'sees', ['贝娜'], [{ group: '深海', replacement: ['贝娜'] }]),
    slot('斯卡蒂', '深海', ['泡泡'], [{ group: 'sees', replacement: ['泡泡'] }]),
    slot('幽灵鲨', '深海', ['火神'], [{ group: 'sees', replacement: ['火神'] }])
  ]
  return {
    default: 'plan1',
    conf: {},
    facility_levels: { dormitory_1: 5 },
    plan1: {
      room_1_1: {
        name: '制造站',
        product: 'gold',
        plans: [
          slot('苍苔', 'sees', ['斯卡蒂']),
          slot('砾', 'sees', ['幽灵鲨']),
          slot('安哲拉', '深海', ['结城理'])
        ]
      },
      room_2_1: { name: '制造站', product: 'gold', plans: shared },
      room_1_3: { name: '发电站', plans: [] },
      room_2_3: { name: '发电站', plans: [] },
      dormitory_1: { name: '', plans: Array.from({ length: 5 }, () => slot('Free', '', [])) }
    },
    backup_plans: [
      {
        name: '鸿雪下班',
        trigger: 'False',
        conf: {},
        task: {},
        plan: {
          room_2_1: {
            name: '制造站',
            product: 'exp3',
            plans: shared.map((value) => ({ ...value, group_bindings: [] }))
          }
        }
      }
    ]
  }
}
