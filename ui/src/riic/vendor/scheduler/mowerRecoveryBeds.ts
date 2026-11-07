import type {RuntimeConfig} from './rosterRuntime'

/** Alpha group beds must exist in both the planner and physical integrator. */
export function normalizeMowerRecoveryBeds(config:RuntimeConfig):void {
 if(!config.mowerAlpha)return
 const bedIds=new Set(config.beds.map(bed=>bed.id))
 for(const [room,slots] of Object.entries(config.mowerSourcePlan??{}))if(room.startsWith('dormitory_'))slots.forEach((slot,index)=>{
  if(!slot.group||![slot.replacement,...(slot.groupBindings??[]).map(binding=>binding.replacement)].some(replacements=>replacements.includes('Free')))return
  const id=room+'_'+index
  if(bedIds.has(id))return
  config.beds.push({id,roomId:room,vip:false,managedRecovery:true})
  bedIds.add(id)
 })
}
