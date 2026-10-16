import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {createRosterRuntime,compiledScheduleToRuntimeConfig} from './rosterRuntime'
import {makeMowerSchedulingData} from './mowerSourceRuntime'
import {createBackupPlanController} from './backupPlans'
import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {alphaFindDormSlot,alphaPrioritizeRecovery,alphaPosition} from './mowerAlphaDorm'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerTaskPlan} from './mowerTaskQueue'
function fixture(ordinaryFirst=false){
 const operators:Record<string,MowerOperatorState>={}
 const plan:MowerTaskPlan={room_1_1:['Provider','Worker']},dorms:MowerDormState[]=[]
 for(const [index,name] of ['Provider','Worker'].entries())operators[name]=new MowerOperatorState({name,room:'room_1_1',index,currentRoom:'room_1_1',currentIndex:index,operatorType:'high',restingPriority:'high',mood:6+index,timeStampMicros:0,singleRecoveryManager:name==='Provider'})
 for(const [room,count] of [['dormitory_1',3],['dormitory_2',1]] as const){
  plan[room]=Array.from({length:5},(_,i)=>i>=5-count?'Free':room+'K'+i)
  plan[room].forEach((name,index)=>{if(name==='Free')dorms.push(new MowerDormState([room,index]));else operators[name]=new MowerOperatorState({name,room,index,currentRoom:room,currentIndex:index,operatorType:'high',mood:24,timeStampMicros:0})})
 }
 return new MowerSchedulingData({alpha:true,plan,operators,dorms,nowMicros:0,dormOrder:ordinaryFirst?['dormitory_1','dormitory_1_low','dormitory_2','dormitory_3','dormitory_4']:undefined})
}
const position=(data:MowerSchedulingData,index:number|undefined)=>index===undefined?undefined:data.dorms[index]!.position
const arrival:MowerTaskPlan={room_1_1:['Free','Free'],dormitory_1:['Current','Current','Provider','Current','Current'],dormitory_2:['Current','Current','Current','Current','Worker']}
describe('single-recovery skill workers use compatible recovery beds',()=>{
 it('routes a new provider to the sole-Free room while preserving the first bed for another worker',()=>{
  const data=fixture(),slot=alphaFindDormSlot(data,'Provider',new Set())
  expect(position(data,slot)).toEqual(['dormitory_2',4])
  expect(position(data,alphaFindDormSlot(data,'Worker',new Set([slot!])))).toEqual(['dormitory_1',2])
 })
 it('keeps explicit ordinary-bed order ahead of a later sole-Free room',()=>{
  const data=fixture(true)
  expect(position(data,alphaFindDormSlot(data,'Provider',new Set()))).toEqual(['dormitory_1',3])
 })
 it('uses ordinary beds when the sole-Free slot is reserved and still rests when only a first bed remains',()=>{
  const data=fixture(),reserved=new Set([alphaPosition('dormitory_2',4)])
  expect(position(data,alphaFindDormSlot(data,'Provider',new Set(),undefined,{},reserved))).toEqual(['dormitory_1',3])
  expect(position(data,alphaFindDormSlot(data,'Provider',new Set([1,2]),undefined,{},reserved))).toEqual(['dormitory_1',2])
 })
 it('counts an activated occupied group bed when identifying multi-Free rooms',()=>{
  const data=fixture(),resident=new MowerOperatorState({name:'Resident',room:'dormitory_1',index:3,currentRoom:'dormitory_1',currentIndex:3,group:'g',replacement:['Free'],operatorType:'high',restingPriority:'high',mood:5,timeStampMicros:0})
  data.operators.Resident=resident;data.plan.dormitory_1![3]='Resident';data.plan.dormitory_1![4]='Fixed'
  data.dorms=[data.dorms[0]!,new MowerDormState(['dormitory_1',3],'Resident',undefined,true),data.dorms[3]!]
  expect(position(data,alphaFindDormSlot(data,'Provider',new Set(),new Set(['g'])))).toEqual(['dormitory_2',4])
 })
 it('does not take a higher-priority resident to obtain a compatible slot',()=>{
  const data=fixture(),op=data.operators.Worker!,bed=data.dorms[3]!
  op.currentRoom='dormitory_2';op.currentIndex=4;bed.name=op.name;data.restingPriorityNames.push(op.name)
  expect(position(data,alphaFindDormSlot(data,'Provider',new Set()))).toEqual(['dormitory_1',3])
  expect(bed.name).toBe('Worker')
 })
 it('reprioritization swaps same-tier recipients and stays stable after observation',()=>{
  const data=fixture(),result=alphaPrioritizeRecovery(data,arrival),final=projectMowerArrangements(data,[result])
  expect([final.operators.Provider!.currentRoom,final.operators.Provider!.currentIndex]).toEqual(['dormitory_2',4])
  expect([final.operators.Worker!.currentRoom,final.operators.Worker!.currentIndex]).toEqual(['dormitory_1',2])
  expect(alphaPrioritizeRecovery(final,result)).toEqual(result)
 })
 it('reprioritization preserves explicit ordinary-bed order',()=>{
  const data=fixture(true),final=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,arrival)])
  expect([final.operators.Provider!.currentRoom,final.operators.Provider!.currentIndex]).toEqual(['dormitory_1',3])
 })
 it('gives the earlier compatible bed to the provider with the larger existing mood deficit',()=>{
  const data=fixture();data.operators.Provider!.mood=1
  data.operators.OtherProvider=new MowerOperatorState({name:'OtherProvider',room:'room_1_1',index:2,currentRoom:'room_1_1',currentIndex:2,operatorType:'high',restingPriority:'high',mood:10,timeStampMicros:0,singleRecoveryManager:true})
  data.plan.room_1_1!.push('OtherProvider')
  const plan=structuredClone(arrival);plan.room_1_1!.push('Free');plan.dormitory_1![3]='OtherProvider'
  const final=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,plan)])
  expect([final.operators.Provider!.currentRoom,final.operators.Provider!.currentIndex]).toEqual(['dormitory_2',4])
  expect([final.operators.OtherProvider!.currentRoom,final.operators.OtherProvider!.currentIndex]).toEqual(['dormitory_1',3])
  expect([final.operators.Worker!.currentRoom,final.operators.Worker!.currentIndex]).toEqual(['dormitory_1',2])
 })
 it('does not move reserved residents or cross tiers for a compatible room',()=>{
  const data=fixture();data.restingPriorityNames.push('Worker')
  const final=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,arrival)])
  expect([final.operators.Worker!.currentRoom,final.operators.Worker!.currentIndex]).toEqual(['dormitory_1',2])
  const reserved=projectMowerArrangements(fixture(),[alphaPrioritizeRecovery(fixture(),arrival,{},new Set([alphaPosition('dormitory_2',4)]))])
  expect([reserved.operators.Worker!.currentRoom,reserved.operators.Worker!.currentIndex]).toEqual(['dormitory_2',4])
 })
})

describe('active single-recovery skill classification survives scheduler adaptation',()=>{
 it('marks workers outside dorm manager slots and honors an explicitly empty active skill snapshot',()=>{
  const workspace=createDefaultWorkspace()
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:id('流明')},groupId:null,replacements:[id('芬')]}]
  const config=compiledScheduleToRuntimeConfig(compileRosterSchedule(workspace));config.mowerSingleRecoverySkillNames=[id('流明')]
  const state=createRosterRuntime(config),data=makeMowerSchedulingData(state)
  expect(data.operators[id('流明')]!.singleRecoveryManager).toBe(true)
  expect(data.operators[id('芬')]!.singleRecoveryManager).toBe(false)
  state.config.mowerSingleRecoverySkillNames=[]
  expect(makeMowerSchedulingData(state,{data}).operators[id('流明')]!.singleRecoveryManager).toBe(false)
  // The catalog's current Lumen snapshot has no unlocked single-target skill; later skillSlots do not count.
  delete state.config.mowerSingleRecoverySkillNames
  expect(makeMowerSchedulingData(state,{data}).operators[id('流明')]!.singleRecoveryManager).toBe(false)
 })
 it.each([false,true])('preserves active skill classification across backup config replacement, alpha=%s',alpha=>{
  const workspace=createDefaultWorkspace()
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:id('芬')},groupId:null,replacements:[id('香草')]}]
  workspace.compatibility.backupPlans=[{trigger:'True',conf:{exhaust_require:['芬']}}]
  const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
  config.mowerAlpha=alpha;config.mowerSingleRecoverySkillNames=[id('流明')]
  const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state)
  controller.evaluate('END')
  expect(controller.active).toEqual([true])
  expect(state.config.mowerSingleRecoverySkillNames).toEqual([id('流明')])
 })
})
