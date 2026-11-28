import { OPERATOR_MAP } from '../domain/operators'
import type { OperatorInventory } from '../domain/operatorInventory'
import type { EfficiencyResources } from '../domain/types'
import type { CompiledSchedule } from './types'
import { compiledScheduleToRuntimeConfig } from './scheduleAdapter'

export interface ScheduleInventoryDiagnostic {code:string;message:string;operatorName?:string}
/** Validate ownership and input stages; skill selection belongs to each simulation. */
export function validateScheduleInventory(schedule: CompiledSchedule, inventory: OperatorInventory, resources?: Partial<EfficiencyResources>, scope: 'all' | 'efficiency-resources' = 'all') {
  const diagnostics: ScheduleInventoryDiagnostic[] = inventory.diagnostics.map(d=>({code:'INVENTORY_INVALID',message:d.message}))
  const runtime=scope==='all'?compiledScheduleToRuntimeConfig(schedule):undefined
  const references=new Set([
    ...(runtime?.positions.flatMap(p=>[p.primary,...p.candidates])??[]),
    ...(runtime?.runOrderPolicies?.flatMap(p=>p.orderedOperatorIds)??[]),
    ...(runtime?.fiammetta?[runtime.fiammetta.operatorId,...runtime.fiammetta.orderedTargets]:[]),
    ...(runtime?.idleOperators??[]),
    ...(resources?.extraWorkplaceOperatorIds??[]),...(resources?.trainingOperatorIds??[]),
  ])
  const owned=new Map(inventory.operators.map(o=>[o.charId,o]))
  for(const id of references){
    const name=OPERATOR_MAP.get(id)?.name??id, operator=owned.get(id)
    if(!operator)diagnostics.push({code:'INVENTORY_OPERATOR_NOT_OWNED',operatorName:name,message:`${name}：参与排班或联动，但未录入干员库`})
  }
  return {valid:inventory.valid&&diagnostics.length===0,diagnostics,participantIds:[...references]}
}
