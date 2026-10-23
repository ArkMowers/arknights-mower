import {alphaPosition,alphaRestingTier,mowerMatchReplacements} from './mowerAlphaDorm'
import {mowerArrangementGroupTransitions} from './mowerSharedGroups'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTaskPlan} from './mowerTaskQueue'

/** Group-managed Free capacity belongs to that group's primaries, independent of physical bed. */
export function mowerDormCapacityAllows(data:MowerSchedulingData,name:string,position:readonly [string,number],plan:MowerTaskPlan={},activeGroups:ReadonlySet<string>=new Set()):boolean {
 if(alphaRestingTier(data,name)>3)return true
 if(!Object.entries(data.plan).some(([room,row])=>room.startsWith('dorm')&&row.some(owner=>owner!=='Free'&&(data.operators[owner]?.replacement.includes('Free')||data.operators[owner]?.groupBindings.some(binding=>binding.replacement.includes('Free'))))))return true
 const transitions={...data.pendingGroupTransitions,...mowerArrangementGroupTransitions(data,plan),...Object.fromEntries([...activeGroups].map(group=>[group,true]))}
 const active=new Set(Object.keys(transitions).filter(group=>transitions[group])),inactive=new Set(Object.keys(transitions).filter(group=>!transitions[group]))
 const moving=new Set([...Object.values(plan).flat().filter(member=>!['','Current','Free'].includes(member)),name])
 const capacities:(Set<string>|undefined)[]=[],residents=new Set<string>()
 for(const bed of data.dorms){
  if(!data.effectiveFreeSlot(bed,inactive,active))continue
  const [room,index]=bed.position,ownerName=data.plan[room]?.[index],owner=data.operators[ownerName??'']
  const groups=owner?.multiGroup?owner.groupBindings.map(binding=>binding.group):[owner?.group??'']
  capacities.push(ownerName==='Free'?undefined:new Set(groups.filter(group=>owner?.replacementsForGroup(group).includes('Free')&&!inactive.has(group)&&(active.has(group)||data.groupIsResting(group)))))
  let resident=plan[room]?.[index]??'Current'
  if(resident==='Current'){resident=data.currentOperator(room,index)?.name??'';if(moving.has(resident))resident=''}
  if(alphaPosition(room,index)===alphaPosition(...position))resident=name
  if(data.operators[resident]&&resident!==ownerName&&alphaRestingTier(data,resident)<=3)residents.add(resident)
 }
 residents.add(name)
 const choices=Object.fromEntries([...residents].sort().map(resident=>{
  const op=data.operators[resident],groups=op?.multiGroup?op.groupBindings.map(binding=>binding.group):[op?.group??'']
  const allowed=capacities.flatMap((capacity,index)=>capacity===undefined||op?.isHigh()&&!op.room.startsWith('dorm')&&groups.some(group=>capacity.has(group))?[index]:[])
  allowed.sort((a,b)=>Number(capacities[a]===undefined)-Number(capacities[b]===undefined))
  return [resident,allowed.map(String)]
 }))
 return mowerMatchReplacements(choices)!==undefined
}
