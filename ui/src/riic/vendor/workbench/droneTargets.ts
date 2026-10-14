import { MOWER_OUTPUT_ROOM_IDS, type RosterWorkspace } from '../domain/roster'

export function droneFacilities(workspace: RosterWorkspace) {
  return MOWER_OUTPUT_ROOM_IDS.flatMap(id => {
    const f = workspace.mainPlan.facilities[id]
    if (!f || (f.type !== 'manufacture' && f.type !== 'trading')) return []
    const target = f.type === 'trading' ? 'trading' : f.product === 'exp' ? 'exp' : 'gold'
    const product = f.type === 'trading' ? '贸易站' : `制造站 · ${f.product === 'exp' ? '作战记录' : f.product === 'fragment' ? '源石碎片' : '赤金'}`
    return [{ roomId: id, target: target as 'gold' | 'exp' | 'trading', label: `B${id[5]}0${id[7]} ${product}` }]
  })
}
