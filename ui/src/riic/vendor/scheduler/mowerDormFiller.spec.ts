import {runScheduleSimulationBridge} from '../workbench/scheduleSimulationBridge'
import {mowerAlphaDormCandidates} from './mowerAlphaCandidates'
import {getOperatorName,getOperatorAvatarUrl} from '../workbench/operatorHelpers'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createBackupPlanController} from './backupPlans'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {describe,it,expect} from 'vitest'
import {isMowerDormFiller,mowerDormFillerId,MOWER_DORM_FILLER_NAME} from './mowerDormFiller'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {createDefaultConfig} from '../domain/defaults'
import {evaluateDormitoryRecovery} from '../engine/dormitoryRecovery'

const proviso='char_4032_provs',nightingale='char_179_cgbird'
function fixture(tired=false){
 const config:RuntimeConfig={mowerAlpha:true,mowerDormFillers:true,mowerRunOrderEnabled:false,mowerTheoreticalMode:true,
  positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']}],
  beds:[0,1,2,3,4].map(i=>({id:'dormitory_1_'+i,roomId:'dormitory_1',vip:i===0})),
  initialMorale:{A:24,R:tired?5:24,[proviso]:24},idleOperators:[],availableIdleOperators:[proviso,nightingale],excludedCandidates:[proviso],
  runOrderPolicies:[{roomId:'room_1_1',orderedOperatorIds:[proviso]}],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[],freeRoom:true},
  mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:Array.from({length:5},()=>({agent:'Free',group:'',replacement:[]}))},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false;source.initialStaffingPending=false
 for(const op of Object.values(source.data.operators)){op.mood=state.morale[op.name]??24;op.timeStampMicros=0}
 Object.assign(source.data.operators.A!,{currentRoom:'room_1_1',currentIndex:0})
 return {state,source,rates:{workRate:()=>1,recoveryRate:()=>4}}
}

describe('neutral dormitory fillers',()=>{
 it('fills every unused bed with a distinct neutral identity instead of full runners or idle skill providers',()=>{
  const {state,source,rates}=fixture()
  for(let i=0;i<3;i++)settleRoster(state,rates)
  const occupants=Object.values(state.bedOccupants)
  expect(occupants).toHaveLength(5)
  expect(occupants.every(isMowerDormFiller)).toBe(true)
  expect(new Set(occupants).size).toBe(5)
  for(const id of occupants){expect(state.morale[id]).toBe(24);expect(source.data.operators[id]!.nativeName).toBe(MOWER_DORM_FILLER_NAME);expect(source.data.getDormByName(id)).toBeUndefined()}
  expect(source.data.dorms.every(bed=>!isMowerDormFiller(bed.name))).toBe(true)
  expect(state.morale[proviso]).toBe(24)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.data.operators.R!.currentRoom).toBe('')
  expect(source.data.operators[nightingale]).toBeUndefined()
  expect(source.trace.some(task=>Object.values(task.plan).flat().includes(proviso))).toBe(false)
  expect(source.trace.some(task=>task.type==='RELEASE_DORM')).toBe(false)
 })
 it('admits real tired replacements before padding and stops using them as fillers after recovery',()=>{
  const {state,source,rates}=fixture(true)
  for(let i=0;i<3;i++)settleRoster(state,rates)
  expect(Object.values(state.bedOccupants)).toContain('R')
  expect(Object.values(state.bedOccupants).filter(isMowerDormFiller)).toHaveLength(4)
  for(let tick=0;tick<200&&state.time<5;tick++){
   const dt=Math.min(5-state.time,nextRosterActionHours(state,rates))
   if(dt>0)advanceRoster(state,dt,rates)
   settleRoster(state,rates)
  }
  expect(state.time).toBe(5)
  expect(state.morale.R).toBe(24)
  expect(source.data.operators.R!.currentRoom).toBe('')
  expect(Object.values(state.bedOccupants).every(isMowerDormFiller)).toBe(true)
 })
 it('does not add a dormitory recovery skill to the configured recovery rate',()=>{
  const c=createDefaultConfig(),fang='char_123_fang',fillers=[1,2,3,4].map(i=>mowerDormFillerId('dormitory_1',i))
  c.facilities.dormitories=[5];c.facilityOperatorIds.dormitories=[[fang,...fillers]];c.dormitoryOccupantCount=5
  const recovery=evaluateDormitoryRecovery(c,0,new Map([[fang,12],...fillers.map(id=>[id,24] as [string,number])]),5000)
  expect(recovery.rates.get(fang)).toBe(4)
  expect(fillers.every(id=>!recovery.rates.has(id))).toBe(true)
 })
})


it('keeps neutral filling through backup preview reconstruction and activation',()=>{
 const workspace=createDefaultWorkspace()
 workspace.mainPlan.facilities.room_1_1.type='trading';workspace.mainPlan.facilities.room_1_1.product='money';workspace.mainPlan.facilities.room_1_1.level=3
 workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
 workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free'},groupId:null,replacements:[]}))
 workspace.compatibility.backupPlans=[{name:'switch',trigger:'True',plan:{},task:{}}]
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true;config.mowerDormFillers=true
 const state=createRosterRuntime(config)
 createBackupPlanController(schedule,state)
 const source=getMowerSourceRuntime(state),model=state.mowerShiftModel!
 expect(model.swap(source.data,[true]).useDormFillers).toBe(true)
 model.activate([true],new MowerTask({type:T.SELF_CORRECTION}))
 expect(state.config.mowerDormFillers).toBe(true)
 expect(getMowerSourceRuntime(state).data.useDormFillers).toBe(true)
})


it('keeps neutral identities fully known without requiring a physical recovery observation',()=>{
 const {source}=fixture()
 const data=source.data
 data.policy.predictiveMoodControl=true
 data.calculatedMoodSnapshot={timeMicros:0,values:{A:24,R:24}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 const candidates=mowerAlphaDormCandidates(data)
 expect(candidates.unknown.some(isMowerDormFiller)).toBe(false)
 expect(candidates.full.filter(isMowerDormFiller)).toHaveLength(5)
})

it('runs complete compiled previews with neutral padding across repeated ordinary rotations',()=>{
 const workspace=createDefaultWorkspace()
 workspace.mainPlan.facilities.room_1_1.type='trading';workspace.mainPlan.facilities.room_1_1.product='money';workspace.mainPlan.facilities.room_1_1.level=3
 workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern','char_4032_provs']}]
 workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free'},groupId:null,replacements:[]}))
 workspace.compatibility.backupPlans=[{name:'switch',trigger:'True',plan:{},task:{}}]
 const result=runScheduleSimulationBridge(workspace,{schedulingModel:'mower-alpha',sampleHours:48,warmupHours:0,maxEvents:4400,recordSegments:true,production:{outputMode:'potential',runOrderMode:'ideal',droneTarget:'none'}},{restingThreshold:.65,theoreticalMode:true})
 expect(result.report?.success,result.error??JSON.stringify(result.report?.diagnostics)).toBe(true)
 expect(workspace.mainPlan.facilities.dormitory_1.slots.every(slot=>slot.occupant.kind==='free')).toBe(true)
 const report=result.report!,fillers=report.operators.filter(op=>isMowerDormFiller(op.operatorId))
 expect(report.assumptions.dormFreeFillModel).toBe('neutral-filler-v1')
 expect(fillers.reduce((sum,op)=>sum+op.restHours,0)).toBeGreaterThan(0)
 expect(fillers.every(op=>op.workHours===0&&op.exhaustedHours===0&&op.finalMorale===24)).toBe(true)
 expect(report.operators.find(op=>op.operatorId==='char_4032_provs')?.restHours??0).toBe(0)
 expect(report.events.filter(event=>event.type==='shift-off').length).toBeGreaterThan(1)
 for(const filler of fillers){expect(getOperatorName(filler.operatorId)).toBe('填充干员');expect(getOperatorAvatarUrl(filler.operatorId)).toContain('Free.webp')}
})


it('counts neutral occupied places for an explicit roommate-count skill without giving fillers skills',()=>{
 const c=createDefaultConfig(),provider='provider',fillers=[1,2,3,4].map(i=>mowerDormFillerId('dormitory_1',i))
 c.facilities.dormitories=[5];c.facilityOperatorIds.dormitories=[[provider,...fillers]];c.dormitoryOccupantCount=5
 c.operatorRecords={[provider]:{charId:provider,name:'provider',appellation:'provider',rarity:0,profession:'',isAlter:false,nationId:null,groupId:null,teamId:null,skills:[{buffId:'dorm_rec_oneself2[000]',name:'roommate count',roomType:'DORMITORY',skillIcon:'',description:'',unlockPhase:0,unlockLevel:0}]}}
 const recovery=evaluateDormitoryRecovery(c,0,new Map([[provider,12],...fillers.map(id=>[id,24] as [string,number])]),5000)
 expect(recovery.rates.get(provider)).toBeCloseTo(4.9)
 expect(fillers.every(id=>!recovery.rates.has(id))).toBe(true)
})
