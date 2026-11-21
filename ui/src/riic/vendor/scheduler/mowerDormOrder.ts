import {mowerRestingBindingGroups,mowerSharedReplacements} from './mowerSharedGroups'
import { effectiveMowerDormOrder } from '../domain/mowerDormOrder'
import type { MowerSchedulingData } from './mowerSchedulingData'

/** Each room's first currently usable bed is its high-priority position. */
export function orderMowerAlphaDormIndices(data: MowerSchedulingData, activeGroups?: Set<string>): number[] {
  const order = effectiveMowerDormOrder(data.dormOrder)
  order.push(...order.filter(room => !room.endsWith('_low') && !order.includes(room + '_low')).map(room => room + '_low'))
  const first = new Map<string, number>()
  const effective = data.dorms.map(bed => {
    if(data.effectiveFreeSlot(bed))return true
    const owner=data.operators[data.plan[bed.position[0]]?.[bed.position[1]]??'']
    if(!bed.autoFree||!owner)return false
    if(!owner.multiGroup)return Boolean(activeGroups?.has(owner.group))
    const groups=mowerRestingBindingGroups(data,owner,Object.fromEntries([...(activeGroups??[])].map(group=>[group,true])))
    return groups.length>0&&mowerSharedReplacements(owner,groups).includes('Free')
  })
  data.dorms.forEach((bed, i) => {
    if (effective[i]) first.set(bed.position[0], Math.min(first.get(bed.position[0]) ?? Infinity, bed.position[1]))
  })
  const rank = (index: number) => {
    const [room, slot] = data.dorms[index]!.position
    return order.indexOf(first.get(room) === slot ? room : room + '_low')
  }
  return data.dorms.map((_, i) => i).sort((a, b) => Number(effective[b]) - Number(effective[a]) || rank(a) - rank(b) || data.dorms[a]!.position[1] - data.dorms[b]!.position[1])
}
