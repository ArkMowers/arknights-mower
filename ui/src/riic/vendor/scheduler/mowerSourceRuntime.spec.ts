import {describe,it,expect} from 'vitest'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,makeMowerSchedulingData} from './mowerSourceRuntime'
import {mowerUpdateDetail,projectMowerArrangements} from './mowerObservations'
import {mowerSchedulingMoodObservation} from './mowerSchedulingMood'
import {alphaRestingTier} from './mowerAlphaDorm'
import {mowerReplacementCandidates,hasRestingMood,restingMood} from './mowerOperatorState'
import {planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {planMowerCorrection,mowerOffDutyFullRecoveryMembers,mowerCorrectionPlan} from './mowerCorrection'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {evaluateBackupExpression} from './backupPlans'
import {retainMowerFailedTask} from './mowerTaskFailure'
const rates={workRate:()=>1,recoveryRate:()=>4}
function fixture():RuntimeConfig {
 const keepers=['K1','K2','K3','K4']
 return {positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},...keepers.map((name,i)=>({id:'dormitory_1_'+i,roomId:'dormitory_1',primary:name,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:16,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(name=>({agent:name,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
}
describe('integrated Mower source scheduler',()=>{
 it('retains source mood context when effective rules rebuild a position projection',()=>{
  const state=createRosterRuntime({...fixture(),mowerAlpha:true}),source=getMowerSourceRuntime(state)
  source.data.nowMicros=3_600_000_000
  Object.assign(source.data.operators.A!,{currentRoom:'room_1_1',currentIndex:0,mood:19,timeStampMicros:0,depletionRate:1})
  const projected=projectMowerArrangements(source.data,[{dormitory_1:['Current','Current','Current','Current','A']}])
  const rebuilt=makeMowerSchedulingData(state,{data:projected});rebuilt.nowMicros=source.data.nowMicros
  expect(mowerSchedulingMoodObservation(rebuilt,'A')).toEqual([18,0])
  expect(mowerSchedulingMoodObservation(source.data,'A')).toEqual([18,0])
 })
 it('keeps ordinary primaries working above their normal departure threshold in either mood mode',()=>{
  for(const enabled of [false,true]){
   const config=fixture();config.mowerAlpha=true
   config.mowerPolicy={...config.mowerPolicy!,restingThreshold:0,predictiveMoodControl:enabled,groupRestInFullOnMoodGap:false}
   config.positions[0]!.candidates=['R'];config.positions[0]!.shiftOffThreshold=0
   config.positions.push({id:'room_1_2_0',roomId:'room_1_2',primary:'B',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:0})
   config.mowerSourcePlan!.room_1_2=[{agent:'B',group:'',replacement:['R']}]
   config.mowerSourceRules!.restInFull=['A','B'];config.initialMorale={A:2,B:3,R:24}
   const runtime=createRosterRuntime(config),predictiveRates={workRate:()=>1,recoveryRate:()=>24,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(n=>[n,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(n=>[n,24]))})}
   settleRoster(runtime,predictiveRates);getMowerSourceRuntime(runtime).queue.tasks.push(new MowerTask());settleRoster(runtime,predictiveRates)
   expect(runtime.occupants.room_1_1_0).toBe('A')
   expect(runtime.occupants.room_1_2_0).toBe('B')
   expect(getMowerSourceRuntime(runtime).trace.some(t=>t.type==='SHIFT_OFF')).toBe(false)
   expect(getMowerSourceRuntime(runtime).queue.tasks.some(t=>t.moodControlEvent||t.moodControlEvidence)).toBe(false)
   expect(runtime.diagnostics.some(d=>d.code==='mower-plan-solver-exception')).toBe(false)
  }
 })
 it.each(['dispatch','next-action'] as const)('discards an old predictive wake before %s',path=>{
  const state=createRosterRuntime({...fixture(),mowerAlpha:true}),source=getMowerSourceRuntime(state)
  source.initial=false;source.firstInit=false
  const wake=new MowerTask({time:0});wake.moodControlEvent={fingerprint:'old',timeMicros:0}
  source.queue.tasks=[wake]
  if(path==='dispatch')settleRoster(state,rates)
  else nextRosterActionHours(state,rates)
  expect(source.queue.tasks).not.toContain(wake)
  expect(source.trace.some(t=>t.type==='SHIFT_OFF')).toBe(false)
  expect(state.occupants.room_1_1_0).toBe('A')
 })
 it('reuses an existing due ordinary wake when discarding an old predictive wake',()=>{
  const state=createRosterRuntime({...fixture(),mowerAlpha:true}),source=getMowerSourceRuntime(state)
  source.initial=false;source.firstInit=false
  const wake=new MowerTask();wake.moodControlEvent={fingerprint:'old',timeMicros:0}
  const ordinary=new MowerTask()
  source.queue.tasks=[wake,ordinary]
  nextRosterActionHours(state,rates)
  expect(source.queue.tasks).toEqual([ordinary])
  expect(ordinary.timeMicros).toBe(0)
 })
 it.each(['ordinary','backup','explicit','product'] as const)('replaces an unstarted saved early departure with normal threshold planning despite a later %s marker',marker=>{
  const state=createRosterRuntime({...fixture(),mowerAlpha:true}),source=getMowerSourceRuntime(state)
  source.initial=false;source.firstInit=false
  const task=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['K1','K2','K3','K4','A']}})
  task.moodControlEvidence={version:'predictive-mood-control-v1'};task.ordinaryCoordination=true;task.coordinationRequestNames=['A']
  if(marker==='backup')task.backupShiftActive=true
  else if(marker==='explicit')task.backupExplicitSlots.add('room_1_1\0'+'0')
  else if(marker==='product')task.productShiftLocked=true
  source.queue.tasks=[task]
  settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(task)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.trace.some(t=>t.type==='SHIFT_OFF')).toBe(false)
 })
 it.each(['retained','started'] as const)('retains an old concrete arrangement and its original deadline after %s work',protection=>{
  const state=createRosterRuntime({...fixture(),mowerAlpha:true}),source=getMowerSourceRuntime(state)
  source.initial=false;source.firstInit=false
  const task=new MowerTask({time:1,type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['K1','K2','K3','K4','A']}})
  task.moodControlEvidence={version:'predictive-mood-control-v1'};task.ordinaryCoordination=true;task.coordinationRequestNames=['A']
  if(protection==='retained')task.executionRetained=true
  else task.arrangementStarted=true
  const plan=structuredClone(task.plan),time=task.timeMicros
  source.queue.tasks=[task]
  nextRosterActionHours(state,rates)
  expect(source.queue.tasks).toContain(task)
  expect(task.plan).toEqual(plan)
  expect(task.timeMicros).toBe(time)
 })
 it('retains standby identity and full-mood idle tier when rebuilding scheduling data',()=>{
  const config=fixture();config.mowerAlpha=true;config.mowerSourceRules!.standby=['A']
  config.mowerSourcePlan!.room_1_1![0]!.group='g'
  config.mowerPolicy!.groupMoodGapExclusions=['other','saved']
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
  mowerUpdateDetail(source.data,'A',0,'dormitory_1',4,true)
  mowerUpdateDetail(source.data,'A',24,'dormitory_1',4,true)
  source.data.groupShiftState.g=true
  source.data.groupRecoveryFullMembers.g=['A']
  source.data.groupRecoveryReturnMicros.g=12345
  const rebuilt=makeMowerSchedulingData(state,source),op=rebuilt.operators.A!
  expect(rebuilt.groupMoodGapExclusions).toEqual(['other','saved'])
  rebuilt.groupMoodGapExclusions.push('extra')
  expect(source.data.groupMoodGapExclusions).toEqual(['other','saved'])
  expect(config.mowerPolicy!.groupMoodGapExclusions).toEqual(['other','saved'])
  expect(rebuilt.groupRecoveryReturnMicros.g).toBe(12345)
  rebuilt.groupRecoveryReturnMicros.g=67890
  expect(source.data.groupRecoveryReturnMicros.g).toBe(12345)
  expect(op).not.toBe(source.data.operators.A)
  expect(op.mood).toBe(24)
  expect(alphaRestingTier(rebuilt,'A')).toBe(6)
  expect(rebuilt.canStandby(op)).toBe(true)
  expect(rebuilt.isGroupShiftAnchor(op)).toBe(false)
  mowerUpdateDetail(rebuilt,'A',24,'room_1_1',0,true)
  expect(alphaRestingTier(rebuilt,'A')).toBe(6)
 })
 it('wakes from retained tasks rather than ordinary morale threshold crossings',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('A');expect(s.bedOccupants.dormitory_1_4).toBe('R')
  expect(nextRosterActionHours(s,rates)).toBe(2.5)
  advanceRoster(s,.4,rates)
  expect(nextRosterActionHours(s,rates)).toBeCloseTo(2.1)
  advanceRoster(s,2.1,rates);settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('R');expect(s.bedOccupants.dormitory_1_4).toBe('A')
  const source=getMowerSourceRuntime(s),bed=source.data.dorms[0]!
  expect(bed.timeMicros!/3_600_000_000).toBeCloseTo(5.125)
  expect(nextRosterActionHours(s,rates)).toBeCloseTo(2.625-8/60)
 })
 it('records a completed return so only an immediate repeat receives the stability delay',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates)
  advanceRoster(s,2.5,rates);settleRoster(s,rates)
  advanceRoster(s,nextRosterActionHours(s,rates),rates);settleRoster(s,rates)
  const data=getMowerSourceRuntime(s).data
  expect(s.occupants.room_1_1_0).toBe('A')
  expect(data.recentShiftOnByRestUnit.get('operator:A')).toBe(data.nowMicros)
 })
 it('evaluates backup moods from the source cache rather than physical simulation values',()=>{
  const c=fixture(),id='char_237_gravel';c.positions[0]!.primary=id;c.mowerSourcePlan!.room_1_1![0]!.agent=id;c.initialMorale={[id]:10,R:24}
  const s=createRosterRuntime(c),data=getMowerSourceRuntime(s).data,op=data.operators[id]!
  op.mood=10;op.timeStampMicros=0;op.depletionRate=1;op.currentRoom='room_1_1';op.currentIndex=0
  s.time=1;data.nowMicros=3_600_000_000;s.morale[id]=8
  expect(evaluateBackupExpression("op_data.operators['砾'].current_mood() < 8.5",s)).toBe(false)
  expect(evaluateBackupExpression("op_data.operators['砾'].current_mood() == 9",s)).toBe(true)
 })
 it('keeps a task one microsecond in the future pending until the actual source clock advances',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates);const source=getMowerSourceRuntime(s),task=new MowerTask({type:T.NOT_SPECIFIC});task.timeMicros=1;source.queue.tasks.push(task)
  settleRoster(s,rates);expect(source.queue.tasks).toContain(task);expect(nextRosterActionHours(s,rates)).toBe(1/3_600_000_000)
  advanceRoster(s,1/3_600_000_000,rates);settleRoster(s,rates);expect(source.queue.tasks).not.toContain(task)
 })
 it('does not execute a derived task removed during the BEGINNING phase',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates);const source=getMowerSourceRuntime(s),old=new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['R']}});source.queue.tasks.unshift(old)
  settleRoster(s,rates,0,phase=>{if(phase==='BEGINNING'&&source.queue.tasks.includes(old))source.queue.consume(old);return false})
  expect(s.occupants.room_1_1_0).toBe('A');expect(source.trace.some(t=>t.type==='SHIFT_ON'&&t.plan.room_1_1?.includes('R'))).toBe(false)
 })
 it('preserves an old observation when a Current-only room task is an exact no-op',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates);const source=getMowerSourceRuntime(s),task=new MowerTask({time:1,plan:{room_1_1:['Current']}});source.queue.tasks.push(task)
  advanceRoster(s,1,rates);settleRoster(s,rates)
  expect(source.data.operators.A!.timeStampMicros).toBe(0);expect(source.data.operators.A!.mood).toBe(16)
 })
 it('checks BEGINNING once when task execution and ordinary planning belong to the same run',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates);const source=getMowerSourceRuntime(s),phases:string[]=[];source.queue.tasks.push(new MowerTask({time:1,plan:{room_1_1:['Current']}}))
  advanceRoster(s,1,rates);settleRoster(s,rates,0,phase=>{phases.push(phase);return false})
  expect(phases.filter(phase=>phase==='BEGINNING')).toEqual(['BEGINNING'])
 })
 it('checks AFTER_PLANNING after a blocked EXHAUST_OFF when the first retained task is SHIFT_ON',()=>{
  const s=createRosterRuntime(fixture());settleRoster(s,rates);const source=getMowerSourceRuntime(s),phases:string[]=[]
  source.data.operators.A!.replacement=[]
  source.queue.tasks=[new MowerTask({type:T.EXHAUST_OFF,metadata:'A'}),new MowerTask({time:1,type:T.SHIFT_ON,plan:{room_1_1:['A']}})]
  settleRoster(s,rates,0,phase=>{phases.push(phase);return false})
  expect(phases.filter(phase=>phase==='AFTER_PLANNING')).toEqual(['AFTER_PLANNING'])
 })
 it('advances the production clock between rooms without repeating the run entry or rebuilding metadata early',()=>{
  const c=fixture();c.mowerDeviceTiming={roomReturnMicros:500_000}
  const s=createRosterRuntime(c);settleRoster(s,rates)
  const source=getMowerSourceRuntime(s)
  expect(nextRosterActionHours(s,rates)).toBe(500_000/3_600_000_000)
  advanceRoster(s,500_000/3_600_000_000,rates);settleRoster(s,rates)
  const startedAt=s.time,phases:{phase:string;time:number}[]=[]
  source.queue.tasks=[new MowerTask({time:s.time,type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['K1','K2','K3','K4','A']}})]
  settleRoster(s,rates,0,phase=>{phases.push({phase,time:s.time});return false})
  expect(s.occupants.room_1_1_0).toBe('R');expect(s.bedOccupants.dormitory_1_4).toBeUndefined()
  expect(source.execution).toBeDefined();expect(phases.map(p=>p.phase)).not.toContain('BEFORE_PLANNING')
  advanceRoster(s,500_000/3_600_000_000,rates);settleRoster(s,rates)
  expect(s.bedOccupants.dormitory_1_4).toBe('A')
  expect(source.data.operators.A!.timeStampMicros).toBe(1_000_000)
  expect(source.queue.tasks.some(t=>t.type===T.SHIFT_ON)).toBe(false)
  advanceRoster(s,500_000/3_600_000_000,rates);settleRoster(s,rates)
  expect(source.execution).toBeUndefined();expect(source.queue.tasks.some(t=>t.type===T.SHIFT_ON)).toBe(true)
  expect(phases.filter(p=>p.phase==='BEGINNING')).toEqual([{phase:'BEGINNING',time:startedAt}])
  // A protected complete shift does not expose its intermediate occupancy to backups.
  expect(phases.some(p=>p.phase==='BEFORE_DORM')).toBe(false)
  expect(phases.find(p=>p.phase==='BEFORE_PLANNING')?.time).toBeCloseTo(startedAt+1_000_000/3_600_000_000,12)
 })
 it('preserves the actual working departure observation while waiting for a dorm room',()=>{
  const c=fixture();c.mowerAlpha=true;c.mowerDeviceTiming={roomReturnMicros:500_000}
  const s=createRosterRuntime(c);settleRoster(s,rates)
  advanceRoster(s,nextRosterActionHours(s,rates),rates);settleRoster(s,rates)
  const source=getMowerSourceRuntime(s),op=source.data.operators.A!
  s.morale.A=5;op.mood=16;op.timeStampMicros=0;op.depletionRate=1
  source.queue.tasks=[new MowerTask({time:s.time,type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['K1','K2','K3','K4','A']}})]
  settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('R')
  expect(op.currentRoom).toBe('')
  expect(op.mood).toBe(5)
  expect(op.timeStampMicros).toBe(source.data.nowMicros)
  expect(op.moodIsPrediction).toBe(false)
  expect(op.depletionRate).toBe(0)
  expect(op.currentMood(source.data.nowMicros+3_600_000_000)).toBe(5)
 })
 it.each([undefined,0])('does not promote an unread working departure with timestamp %s',stamp=>{
  const c=fixture();c.mowerAlpha=true;c.mowerDeviceTiming={roomReturnMicros:500_000}
  const s=createRosterRuntime(c);settleRoster(s,rates)
  advanceRoster(s,nextRosterActionHours(s,rates),rates);settleRoster(s,rates)
  const source=getMowerSourceRuntime(s),op=source.data.operators.A!
  s.morale.A=5;op.mood=16;op.timeStampMicros=stamp;op.depletionRate=1
  // A Fiammetta restoration does not read the departing work-room operator.
  source.queue.tasks=[new MowerTask({time:s.time,type:T.FIAMMETTA,plan:{room_1_1:['R']}})]
  settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('R')
  expect(op.currentRoom).toBe('')
  expect(op.mood).toBe(16)
  expect(op.timeStampMicros).toBeUndefined()
 })
 it('establishes recovery before an exact dorm no-op and preserves the final list',()=>{
  const c=fixture(),s=createRosterRuntime(c);settleRoster(s,rates)
  const source=getMowerSourceRuntime(s),data=source.data
  data.priorityReplacement=['R']
  data.operators.K1!.singleRecoveryManager=true
  data.operators.R!.mood=10;s.morale.R=10
  const list=['K1','K2','K3','K4','R'],task=new MowerTask({plan:{dormitory_1:list}})
  source.queue.tasks=[task];settleRoster(s,rates)
  expect(list).toEqual(['K1','K2','K3','K4','R'])
  expect(data.operators.R!.dormRecoveryRoom).toBe('dormitory_1')
  expect(data.operators.R!.dormRecoveryIndex).toBe(4)
  expect(Object.values(s.bedOccupants)).toContain('R')
 })

 it('preserves strict run entry and advances only at a completed run boundary',()=>{
  const c=fixture();c.mowerRunLoopClock={minimumClockStepMicros:1,notificationSleepMicros:1_000_000}
  const s=createRosterRuntime(c);s.bedOccupants.dormitory_1_4='R'
  const source=getMowerSourceRuntime(s)
  const initial=source.queue.tasks[0]!,future=new MowerTask({time:1});source.queue.tasks.push(future)
  settleRoster(s,rates)
  expect(source.queue.tasks).not.toContain(initial)
  expect(source.queue.tasks.some(t=>t!==future&&t.timeMicros===0)).toBe(true)
  expect(s.time).toBe(0);expect(nextRosterActionHours(s,rates)).toBe(1/3_600_000_000)
  advanceRoster(s,1/3_600_000_000,rates);settleRoster(s,rates)
  expect(source.queue.tasks).toEqual([future])
  expect(nextRosterActionHours(s,rates)).toBe(1_000_000/3_600_000_000)
  advanceRoster(s,1_000_000/3_600_000_000,rates);settleRoster(s,rates)
  expect(source.queue.tasks).toEqual([future]);expect(future.timeMicros).toBe(3_600_000_000)
  expect(s.time*3_600_000_000).toBeCloseTo(1_000_001,5)
 })

 it('vacates a Current dorm bed when its operator is explicitly moved to another bed',()=>{
  const c=fixture();c.idleOperators=['X','Y'];c.mowerDeviceTiming={roomReturnMicros:500_000};c.mowerRunLoopClock={minimumClockStepMicros:1,notificationSleepMicros:1_000_000}
  c.positions=c.positions.filter(p=>p.id!=='dormitory_1_3')
  c.beds=[{id:'dormitory_1_3',roomId:'dormitory_1',vip:true},{id:'dormitory_1_4',roomId:'dormitory_1',vip:false}]
  c.mowerSourcePlan!.dormitory_1=[...['K1','K2','K3'].map(agent=>({agent,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]}]
  const s=createRosterRuntime(c),source=getMowerSourceRuntime(s);source.initial=false
  s.occupants.room_1_1_0='R';s.bedOccupants.dormitory_1_4='A';s.morale.A=8
  for(const [index,name] of ['K1','K2','K3','','A'].entries())if(name){const op=source.data.operators[name]!;op.currentRoom='dormitory_1';op.currentIndex=index;op.mood=s.morale[name]??24;op.timeStampMicros=0}
  source.data.operators.R!.currentRoom='room_1_1';source.data.operators.R!.currentIndex=0;source.data.operators.K1!.singleRecoveryManager=true
  const task=new MowerTask({plan:{dormitory_1:['Current','Current','Current','A','Current']}});source.queue.tasks=[task]
  for(let attempt=0;attempt<20&&source.queue.tasks.includes(task);attempt++){
   settleRoster(s,rates)
   if(source.queue.tasks.includes(task))advanceRoster(s,Math.max(nextRosterActionHours(s,rates),1/3_600_000_000),rates)
  }
  expect(source.queue.tasks).not.toContain(task)
  expect(source.error).toBeFalsy()
  expect(s.bedOccupants.dormitory_1_3).toBe('A')
  expect(Object.values(s.bedOccupants).filter(name=>name==='A')).toHaveLength(1)
  expect(s.diagnostics.some(d=>d.code==='mower-task-exception')).toBe(false)
 })

})

 it('selects Fiammetta targets from cached mood without an extra candidate-room read',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.initialMorale={A:24,R:24,[fia]:24};config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:true,threshold:1}
  const state=createRosterRuntime(config);settleRoster(state,rates)
  const source=getMowerSourceRuntime(state),candidate=source.data.operators.A!
  // Resume an already charged cycle; the initial-condition contract is tested separately.
  state.morale[fia]=24;source.data.operators[fia]!.mood=24
  expect(candidate.mood).toBe(24);candidate.depletionRate=0;candidate.timeStampMicros=source.data.nowMicros
  state.morale.A=10;source.queue.tasks=[new MowerTask({time:state.time,type:T.FIAMMETTA})]
  settleRoster(state,rates)
  expect(state.events.find(event=>event.type==='fiammetta')).toBeUndefined()
  expect(state.morale.A).toBe(10);expect(state.morale[fia]).toBe(24)
  expect(candidate.mood).toBe(24)
  expect(source.queue.tasks.some(task=>task.type===T.FIAMMETTA)).toBe(false)
 })

 it('resets learned working depletion after Fiammetta charge-room restoration',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.initialMorale={A:24,R:24,[fia]:24};config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:true,threshold:21.6}
  const state=createRosterRuntime(config);settleRoster(state,rates)
  const source=getMowerSourceRuntime(state);source.data.operators.A!.depletionRate=.7;source.data.operators.A!.mood=10;state.morale.A=10
  source.queue.tasks=[new MowerTask({time:state.time,type:T.FIAMMETTA})]
  settleRoster(state,rates)
  expect(state.events.some(e=>e.type==='fiammetta')).toBe(true)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.data.operators.A!.depletionRate).toBe(0)
 })

 it.each([false,true])('refreshes alpha dorm timers after a confirmed arrangement (exact no-op=%s)',same=>{
  const config=fixture();config.mowerAlpha=true;config.idleOperators=['X']
  const state=createRosterRuntime(config);settleRoster(state,rates)
  const source=getMowerSourceRuntime(state),op=source.data.operators.R!,bed=source.data.getDormByName('R')![1]
  state.time=1;source.data.nowMicros=3_600_000_000
  state.morale.R=24;op.mood=24;op.timeStampMicros=0;op.depletionRate=.75;bed.timeMicros=5*3_600_000_000
  source.queue.tasks=[new MowerTask({time:1,type:T.NOT_SPECIFIC,plan:{dormitory_1:[same?'K1':'X','K2','K3','K4','R']}})]
  settleRoster(state,rates)
  expect(op.timeStampMicros).toBe(3_600_000_000)
  expect(bed.timeMicros).toBe(3_600_000_000)
  expect(op.mood).toBe(24)
 })

 it('keeps a Fiammetta restoration no-op free of additional room reads',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.initialMorale={A:24,R:24,[fia]:24};config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:true,threshold:21.6}
  const state=createRosterRuntime(config);settleRoster(state,rates)
  const source=getMowerSourceRuntime(state),bed=source.data.getDormByName('R')![1],op=source.data.operators.R!
  state.morale[fia]=24;source.data.operators[fia]!.mood=24
  state.time=1;source.data.nowMicros=3_600_000_000;bed.timeMicros=5*3_600_000_000;op.timeStampMicros=0
  const fiaTimestamp=source.data.operators[fia]!.timeStampMicros
  source.queue.tasks=[new MowerTask({time:1,type:T.FIAMMETTA,plan:{dormitory_1:[fia,'K2','K3','K4','R']}})]
  settleRoster(state,rates)
  expect(bed.timeMicros).toBe(5*3_600_000_000)
  expect(op.timeStampMicros).toBe(0)
  expect(source.data.operators[fia]!.timeStampMicros).toBe(fiaTimestamp)
 })

 it.each([{alpha:false,named:false},{alpha:true,named:false},{alpha:false,named:true},{alpha:true,named:true}])('completes a full-target Fiammetta intention without failures or repeated tasks ($alpha, named=$named)',({alpha,named})=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=alpha
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.initialMorale={A:24,R:24,[fia]:24};config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  state.morale[fia]=24
  for(const [slot,name] of Object.entries(state.occupants)){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0}
  const task=new MowerTask({type:T.FIAMMETTA,...(named?{plan:{dormitory_1:['A',fia]},metadata:'A'}:{})})
  source.queue.tasks=[task]
  const before={...state.occupants}
  settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toHaveLength(0)
  expect(state.events.filter(e=>e.type==='fiammetta')).toHaveLength(0)
  expect(state.occupants).toEqual(before)
  const traces=source.trace.filter(t=>t.type==='FIAMMETTA').length
  for(let attempt=0;attempt<8;attempt++)settleRoster(state,rates)
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traces)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toHaveLength(0)
  expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
  // 后续真实工作降低目标心情；关闭防呆仍允许高于阈值的有效充能。
  source.data.operators.A!.depletionRate=1
  advanceRoster(state,.25,rates)
  source.queue.tasks.push(new MowerTask({time:state.time}))
  settleRoster(state,rates)
  expect(state.events.some(e=>e.type==='fiammetta'&&e.operators[1]==='A')).toBe(true)
  expect(state.events.find(e=>e.type==='fiammetta')!.moraleBefore![1]).toBeGreaterThan(21.6)
  expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
 })

 it.each([false,true])('charges a target at a personal recovery cap below 24 with alpha=%s',alpha=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=alpha
  config.positions[0]!.upperLimit=12;config.beds=[]
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  state.morale.A=12;state.morale[fia]=24
  Object.assign(source.data.operators.A!,{mood:12,timeStampMicros:0,currentRoom:'room_1_1',currentIndex:0})
  source.queue.tasks=[new MowerTask({type:T.FIAMMETTA,metadata:'A',plan:{dormitory_1:['A',fia]}})]
  settleRoster(state,rates)
  expect(state.events.some(event=>event.type==='fiammetta'&&event.operators[1]==='A')).toBe(true)
  expect(state.events.find(event=>event.type==='fiammetta')!.moraleBefore![1]).toBe(12)
 })

 it('rechecks a queued charge target through its room observation and cancels without restoration',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  state.morale[fia]=24;state.morale.A=24
  const op=source.data.operators.A!;Object.assign(op,{mood:10,timeStampMicros:0,currentRoom:'room_1_1',currentIndex:0})
  const task=new MowerTask({type:T.FIAMMETTA,metadata:'A',plan:{dormitory_1:['A',fia]}})
  source.queue.tasks=[task]
  const occupants={...state.occupants}
  settleRoster(state,rates)
  expect(op.mood).toBe(24)
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toHaveLength(0)
  expect(state.occupants).toEqual(occupants)
  expect(state.events.some(e=>e.type==='fiammetta')).toBe(false)
  expect(state.diagnostics.some(d=>d.code==='mower-task-exception')).toBe(false)
 })

 it('finishes the precise old full-to-full failure without leaving an incomplete task',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  state.morale.A=24;state.morale[fia]=24
  const task=new MowerTask({type:T.FIAMMETTA,metadata:'A',plan:{dormitory_1:['A',fia]}})
  task.arrangementStarted=true
  const failure={reason:'菲亚梅塔与实际充能目标均已满心情，保留充能任务，等待相关实测或安排更新',rooms:['dormitory_1'],snapshot:{intent:'old',observations:{}}}
  task.executionFailure=failure
  const unrelated=new MowerTask({time:42,type:T.FIAMMETTA,metadata:'other',plan:{room_2_1:['Current']}})
  source.queue.tasks=[task,unrelated]
  retainMowerFailedTask(state,source.data,unrelated,'保留其他未完成安排',[])
  const unrelatedFailure=unrelated.executionFailure,unrelatedPlan=structuredClone(unrelated.plan),unrelatedTime=unrelated.timeMicros
  settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks).toContain(unrelated)
  expect(unrelated.executionFailure).toBe(unrelatedFailure)
  expect(unrelated.plan).toEqual(unrelatedPlan)
  expect(unrelated.timeMicros).toBe(unrelatedTime)
  expect(state.events.some(e=>e.type==='fiammetta')).toBe(false)
  expect(state.diagnostics.some(d=>d.code==='mower-task-exception')).toBe(false)
 })

 it('restores an already started two-person dorm arrangement even when both operators are full',()=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  state.morale.A=24;state.morale[fia]=24
  delete state.occupants.room_1_1_0;delete state.occupants.dormitory_1_0
  state.bedOccupants.dormitory_1_0='A';state.bedOccupants.dormitory_1_1=fia
  Object.assign(source.data.operators.A!,{mood:24,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:0})
  Object.assign(source.data.operators[fia]!,{mood:24,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:1})
  const task=new MowerTask({type:T.FIAMMETTA,plan:{room_1_1:['A'],dormitory_1:[fia,'K2']}});task.arrangementStarted=true
  source.queue.tasks=[task]
  settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(task)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(state.occupants.dormitory_1_0).toBe(fia)
  expect(Object.values(state.bedOccupants)).not.toContain('A')
  expect(state.events.some(e=>e.type==='fiammetta')).toBe(false)
  expect(state.diagnostics.some(d=>d.code==='mower-task-exception')).toBe(false)
 })


it('starts an exhausted shift before observed morale reaches zero',()=>{
 const config=fixture();config.mowerAlpha=true;config.initialMorale.A=.18;config.mowerSourceRules!.exhaustRequire=['A']
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 for(const [slot,name] of Object.entries(state.occupants)){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]??24;op.timeStampMicros=0}
 source.queue.tasks=[new MowerTask({type:T.EXHAUST_OFF,metadata:'A'})]
 for(let i=0;i<20&&!source.data.operators.A!.isResting();i++){
  settleRoster(state,rates)
  if(!source.data.operators.A!.isResting())advanceRoster(state,nextRosterActionHours(state,rates),rates)
 }
 expect(source.data.operators.A!.isResting()).toBe(true)
 expect(state.morale.A).toBeGreaterThan(0)
 expect(state.occupants.room_1_1_0).toBe('R')
})

function calculatedMoodFixture(enabled=true,observedResident=true){
 const config=fixture();config.mowerAlpha=true;config.mowerPolicy!.predictiveMoodControl=enabled
 config.idleOperators=['S'];config.initialMorale={...config.initialMorale,S:5}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 mowerUpdateDetail(data,'A',10,'room_1_1',0,true)
 mowerUpdateDetail(data,'R',10,'dormitory_1',4,observedResident)
 mowerUpdateDetail(data,'S',5,'',-1,true)
 data.dorms[0]!.name='R'
 state.bedOccupants.dormitory_1_4='R';state.morale.A=10;state.morale.R=24;state.time=1
 return {state,data}
}

describe('calculated scheduling mood remains separate from observations',()=>{
 it('keeps the cached fallback when both model source and caller clock are absent',()=>{
  const {data}=calculatedMoodFixture(false),op=data.operators.R!
  expect(op.calculatedMoodSnapshot).toBeUndefined()
  expect(op.currentMood(undefined as unknown as number)).toBe(10)
 })
 it.each([false,true])('uses the saved mood mode in the actual source-to-bed-planning call, enabled=%s',enabled=>{
  const {state,data}=calculatedMoodFixture(enabled),resident=data.operators.R!,before={mood:resident.mood,time:resident.timeStampMicros,prediction:resident.moodIsPrediction}
  getMowerSourceRuntime(state)
  expect(mowerSchedulingMoodObservation(data,'R')).toEqual(enabled?[24,toMowerMicros(1)]:[10,0])
  const fill=planMowerAlphaDormFill(data,new MowerTaskQueue())
  expect(fill?.plan.dormitory_1?.[4]).toBe(enabled?'S':undefined)
  expect({mood:resident.mood,time:resident.timeStampMicros,prediction:resident.moodIsPrediction}).toEqual(before)
 })
 it.each(['missing','future','invalid','prediction','invalid model'] as const)('does not supply a model baseline from a %s observation',kind=>{
  const {state,data}=calculatedMoodFixture(true,false),op=data.operators.R!
  if(kind==='future'){data.nowMicros=toMowerMicros(2);mowerUpdateDetail(data,'R',10,'dormitory_1',4,true)}
  if(kind==='invalid')mowerUpdateDetail(data,'R',-1,'dormitory_1',4,true)
  if(kind==='prediction'){op.mood=24;op.timeStampMicros=0;op.moodIsPrediction=true}
  if(kind==='invalid model'){mowerUpdateDetail(data,'R',10,'dormitory_1',4,true);state.morale.R=NaN}
  getMowerSourceRuntime(state)
  expect(mowerSchedulingMoodObservation(data,'R')).toBeUndefined()
  expect(op.currentMood(data.nowMicros)).toBe(-1)
  expect(planMowerAlphaDormFill(data,new MowerTaskQueue())).toBeUndefined()
 })
 it('retains its actual model baseline through ordinary countdown predictions and changed bed metadata',()=>{
  const {state,data}=calculatedMoodFixture(),op=data.operators.R!
  op.mood=24;op.moodIsPrediction=true;op.dormRecoveryObservation=['dormitory_1',4,0,toMowerMicros(1)]
  getMowerSourceRuntime(state)
  expect(mowerSchedulingMoodObservation(data,'R')).toEqual([24,toMowerMicros(1)])
  expect(planMowerAlphaDormFill(data,new MowerTaskQueue())?.plan.dormitory_1?.[4]).toBe('S')
  expect(op.moodIsPrediction).toBe(true)
  op.dormRecoveryObservation=['dormitory_1',3,0,toMowerMicros(1)]
  getMowerSourceRuntime(state)
  expect(mowerSchedulingMoodObservation(data,'R')).toEqual([24,toMowerMicros(1)])
 })
 it('isolates instantaneous projections and never carries a current model value into a future clock',()=>{
  const {state,data}=calculatedMoodFixture();getMowerSourceRuntime(state)
  const projected=projectMowerArrangements(data,[])
  expect(mowerSchedulingMoodObservation(projected,'R')).toEqual([24,toMowerMicros(1)])
  projected.calculatedMoodSnapshot={timeMicros:projected.nowMicros,values:{...projected.calculatedMoodSnapshot!.values,R:7}}
  expect(mowerSchedulingMoodObservation(data,'R')).toEqual([24,toMowerMicros(1)])
  projected.nowMicros+=toMowerMicros(1)
  expect(mowerSchedulingMoodObservation(projected,'R')).toBeUndefined()
  expect(data.nowMicros).toBe(toMowerMicros(1))
 })
 it.each([false,true])('uses the same model source for actual backup mood conditions, enabled=%s',enabled=>{
  const config=fixture(),actor='char_237_gravel';config.mowerAlpha=true;config.mowerPolicy!.predictiveMoodControl=enabled
  config.positions[0]!.primary=actor;config.mowerSourcePlan!.room_1_1![0]!.agent=actor;config.initialMorale={[actor]:19,R:24}
  const state=createRosterRuntime(config),data=getMowerSourceRuntime(state).data
  mowerUpdateDetail(data,actor,19,'room_1_1',0,true)
  state.time=1;state.morale[actor]=10;getMowerSourceRuntime(state)
  expect(evaluateBackupExpression("op_data.operators['砾'].current_mood() < 11",state)).toBe(enabled)
  expect(evaluateBackupExpression("op_data.operators['砾'].mood == 19",state)).toBe(true)
  expect(data.operators[actor]!.timeStampMicros).toBe(0)
 })
 it('refreshes the same known baseline across model clock changes without borrowing future snapshot values',()=>{
  const {state,data}=calculatedMoodFixture();getMowerSourceRuntime(state)
  const op=data.operators.R!
  expect(op.currentMood(data.nowMicros)).toBe(24)
  expect(Object.isFrozen(op.calculatedMoodSnapshot!.values)).toBe(true)
  state.time=2;state.morale.R=20;getMowerSourceRuntime(state)
  expect(op.currentMood(data.nowMicros)).toBe(20)
  expect(op.currentMood(data.nowMicros+toMowerMicros(1))).toBe(10)
  op.currentRoom='train';op.currentIndex=0
  expect(op.currentMood(data.nowMicros)).toBe(10)
  expect(op.mood).toBe(10);expect(op.timeStampMicros).toBe(0)
 })
 it('drops the model source when an effective configuration rebuild disables the saved mood mode',()=>{
  const {state,data}=calculatedMoodFixture();getMowerSourceRuntime(state)
  expect(data.operators.R!.currentMood(data.nowMicros)).toBe(24)
  state.config={...state.config,mowerPolicy:{...state.config.mowerPolicy!,predictiveMoodControl:false}}
  const next=makeMowerSchedulingData(state,{data})
  expect(next.calculatedMoodSnapshot).toBeUndefined()
  expect(next.operators.R!.currentMood(next.nowMicros)).toBe(10)
  expect(data.operators.R!.currentMood(data.nowMicros)).toBe(24)
 })
 it.each([false,true])('uses current calculated completion in ordinary correction, enabled=%s',enabled=>{
  const {state,data}=calculatedMoodFixture(enabled)
  mowerUpdateDetail(data,'R',20,'room_1_1',0,true)
  mowerUpdateDetail(data,'A',10,'dormitory_1',4,true)
  state.occupants.room_1_1_0='R';state.bedOccupants.dormitory_1_4='A';state.morale.A=24;state.morale.R=20
  const observed={mood:data.operators.A!.mood,time:data.operators.A!.timeStampMicros}
  getMowerSourceRuntime(state)
  const correction=planMowerCorrection(data,new MowerTaskQueue())
  expect(correction?.plan.room_1_1?.[0]).toBe(enabled?'A':undefined)
  expect({mood:data.operators.A!.mood,time:data.operators.A!.timeStampMicros}).toEqual(observed)
 })
})


describe('calculated mood observations survive scheduling cache invalidation',()=>{
 it('readmits a partially recovered full-rest primary after actual departure invalidates its raw timestamp',()=>{
  const {state,data}=calculatedMoodFixture()
  data.operators.A!.restInFull=true;data.operators.A!.exhaustRequire=true
  mowerUpdateDetail(data,'R',24,'room_1_1',0,true)
  mowerUpdateDetail(data,'A',23.475943578706268,'dormitory_1',4,true)
  state.occupants.room_1_1_0='R';state.bedOccupants.dormitory_1_4='A';state.morale.A=23.475943578706268;state.morale.R=24
  data.dorms[0]!.name='A';getMowerSourceRuntime(state)
  const source=getMowerSourceRuntime(state),departure=new MowerTask({time:state.time,type:T.RE_ORDER,plan:{dormitory_1:['Current','Current','Current','Current','S']}})
  departure.backupShiftActive=true;source.queue.tasks=[departure]
  for(let n=0;n<6&&source.queue.tasks.includes(departure);n++){settleRoster(state,rates);advanceRoster(state,.5/3600,rates)}
  const op=data.operators.A!
  expect(op.currentRoom).toBe('');expect(op.timeStampMicros).toBeUndefined()
  getMowerSourceRuntime(state)
  expect(mowerSchedulingMoodObservation(data,'A')?.[0]).toBeLessThan(24)
  expect(mowerOffDutyFullRecoveryMembers(data).has('A')).toBe(true)
  expect(Object.entries(mowerCorrectionPlan(data)).filter(([room])=>room.startsWith('dorm')).flatMap(([,row])=>row)).toContain('A')
 })
 it('retains an actual observation after its exhaust timestamp is cleared and a configuration projection is rebuilt',()=>{
  const {state,data}=calculatedMoodFixture()
  getMowerSourceRuntime(state);data.operators.A!.timeStampMicros=undefined
  state.config={...state.config};state.morale.A=7;state.time=2
  const next=getMowerSourceRuntime(state).data
  expect(next.operators.A!.timeStampMicros).toBeUndefined()
  expect(mowerSchedulingMoodObservation(next,'A')).toEqual([7,toMowerMicros(2)])
  const projected=projectMowerArrangements(next,[])
  const observed=next.calculatedMoodObservations.R
  mowerUpdateDetail(projected,'R',24,'dormitory_1',4,true)
  expect(projected.calculatedMoodObservations.R).toBe(toMowerMicros(2))
  expect(next.calculatedMoodObservations.R).toBe(observed)
  expect(next.operators.R!.timeStampMicros).toBe(0)
 })
})

it('keeps actual model observations across disabling and reopening while unread operators remain unknown',()=>{
 const {state,data}=calculatedMoodFixture(),observed=data.calculatedMoodObservations.A
 getMowerSourceRuntime(state)
 state.config={...state.config,mowerPolicy:{...state.config.mowerPolicy!,predictiveMoodControl:false}}
 const disabled=getMowerSourceRuntime(state).data
 expect(disabled.calculatedMoodSnapshot).toBeUndefined()
 expect(disabled.calculatedMoodObservations.A).toBe(observed)
 delete disabled.calculatedMoodObservations.S
 mowerUpdateDetail(disabled,'S',5,'',-1,true)
 state.time=2;state.morale.A=7
 state.config={...state.config,mowerPolicy:{...state.config.mowerPolicy!,predictiveMoodControl:true}}
 const reopened=getMowerSourceRuntime(state).data
 expect(mowerSchedulingMoodObservation(reopened,'A')).toEqual([7,toMowerMicros(2)])
 expect(mowerSchedulingMoodObservation(reopened,'S')).toBeUndefined()
 expect(reopened.operators.S!.mood).toBe(5)
})

it('keeps the measured model baseline when actual refresh-drained movement invalidates the exhausted-shift cache',()=>{
 const {state,data}=calculatedMoodFixture(),source=getMowerSourceRuntime(state)
 state.config.mowerSourceRules!.refreshDrained=['S'];data.operators.A!.exhaustRequire=true
 const task=new MowerTask({time:state.time,type:T.RE_ORDER,plan:{dormitory_1:['Current','Current','Current','Current','S']}})
 task.backupShiftActive=true;source.queue.tasks=[task]
 for(let n=0;n<6&&source.queue.tasks.includes(task);n++){settleRoster(state,rates);advanceRoster(state,.5/3600,rates)}
 expect(data.operators.A!.currentRoom).toBe('room_1_1')
 expect(data.operators.A!.timeStampMicros).toBeUndefined()
 getMowerSourceRuntime(state)
 expect(mowerSchedulingMoodObservation(data,'A')).toEqual([state.morale.A,data.nowMicros])
 expect(data.operators.A!.mood).toBe(10)
})

it('uses an independently observed full dorm filler after its raw observation cache is invalidated',()=>{
 const {state,data}=calculatedMoodFixture(),op=data.operators.R!
 getMowerSourceRuntime(state);op.timeStampMicros=undefined
 getMowerSourceRuntime(state)
 expect(hasRestingMood(op,data.nowMicros)).toBe(true)
 expect(planMowerAlphaDormFill(data,new MowerTaskQueue())?.plan.dormitory_1?.[4]).toBe('S')
 expect(op.timeStampMicros).toBeUndefined();expect(op.mood).toBe(10)
})
it('orders actual replacement candidates by known calculated mood after raw observation invalidation',()=>{
 const {state,data}=calculatedMoodFixture(),owner=data.operators.A!,full=data.operators.R!
 owner.replacement=['R','S'];state.morale.R=0
 getMowerSourceRuntime(state);full.timeStampMicros=undefined
 getMowerSourceRuntime(state)
 expect(mowerReplacementCandidates(owner,data.operators,data.policy,data.nowMicros)).toEqual(['S','R'])
 full.currentRoom='train'
 expect(hasRestingMood(full,data.nowMicros)).toBe(false)
 expect(restingMood(full,data.nowMicros)).toBe(24)
})
it('keeps unread calculated dorm mood unknown through the shared resting helpers',()=>{
 const {state,data}=calculatedMoodFixture(true,false),op=data.operators.R!
 getMowerSourceRuntime(state)
 expect(hasRestingMood(op,data.nowMicros)).toBe(false)
 expect(restingMood(op,data.nowMicros)).toBe(-1)
 expect(planMowerAlphaDormFill(data,new MowerTaskQueue())).toBeUndefined()
})


describe('confirmed charging group return in source dispatch',()=>{
 it.each([true,false].flatMap(existing=>['none','target','member'].map(full=>({existing,full}))))('charges before recovery-gated return, existing batch=$existing, full=$full',({existing,full})=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=true
  config.positions=config.positions.filter(p=>p.id!=='dormitory_1_3')
  config.positions[0]!.group='G';config.positions[1]!.primary=fia
  config.positions.push({id:'room_1_2_0',roomId:'room_1_2',primary:'B',candidates:['S'],group:'G',lowerLimit:0,upperLimit:24,shiftOffThreshold:15})
  config.beds.push({id:'dormitory_1_3',roomId:'dormitory_1',vip:false})
  config.mowerSourcePlan!.room_1_1![0]!.group='G'
  config.mowerSourcePlan!.room_1_2=[{agent:'B',group:'G',replacement:['S']}]
  config.mowerSourcePlan!.dormitory_1![0]!.agent=fia;config.mowerSourcePlan!.dormitory_1![3]!.agent='Free'
  config.mowerPolicy={...config.mowerPolicy!,opeRestingPriority:['A'],groupRestInFullOnMoodGap:false}
  config.fiammetta={operatorId:fia,orderedTargets:['B'],fool:false,threshold:21.6}
  config.initialMorale={A:12,B:12,R:24,S:24,[fia]:24}
  config.mowerSourceRules!.restInFull=full==='none'?[]:[full==='target'?'B':'A']
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false;source.firstInit=false;source.initialStaffingPending=false
  state.morale[fia]=24;Object.assign(source.data.operators[fia]!,{mood:24,timeStampMicros:0})
  Object.assign(state.occupants,{room_1_1_0:'R',room_1_2_0:'S',dormitory_1_3:'A',dormitory_1_4:'B'})
  for(const [name,room,index] of [['A','dormitory_1',3],['B','dormitory_1',4],['R','room_1_1',0],['S','room_1_2',0]] as const)Object.assign(source.data.operators[name]!,{currentRoom:room,currentIndex:index,mood:state.morale[name],timeStampMicros:0})
  source.data.operators.A!.restingPriority='high';source.data.operators.B!.restingPriority='low';source.data.groupShiftState.G=true
  for(const bed of source.data.dorms){bed.name=bed.position[1]===3?'A':'B';bed.timeMicros=toMowerMicros(4)}
  source.queue.tasks=[new MowerTask({type:T.FIAMMETTA}),...(existing?[new MowerTask({time:4,type:T.SHIFT_ON,plan:{room_1_1:['A'],room_1_2:['B']}})]:[])]
  settleRoster(state,rates)
  for(let i=0;i<8;i++){advanceRoster(state,1/3600,rates);settleRoster(state,rates)}
  expect(state.events.some(e=>e.type==='fiammetta'&&e.operators[1]==='B'),JSON.stringify({morale:state.morale,trace:source.trace,queue:source.queue.tasks.map(t=>[t.type.key,t.time,t.metadata,t.executionFailure]),diagnostics:state.diagnostics})).toBe(true)
  const returned=()=>source.trace.some(t=>t.type==='SHIFT_ON'&&t.plan.room_1_1?.includes('A')&&t.plan.room_1_2?.includes('B'))
  if(full==='member'){
   expect(returned()).toBe(false)
   const pending=source.queue.tasks.find(t=>t.type===T.SHIFT_ON&&t.fiaReturnTarget==='B')!
   expect(pending).toBeDefined();expect(pending.timeMicros).toBeGreaterThan(source.data.nowMicros)
   expect(source.queue.tasks.some(t=>t.type===T.FIAMMETTA&&t.fiaReturnTarget)).toBe(false)
  }else{
   expect(returned()).toBe(true)
   expect(source.trace.find(t=>t.type==='SHIFT_ON'&&t.plan.room_1_1?.includes('A')&&t.plan.room_1_2?.includes('B'))!.timeMicros).toBeLessThan(toMowerMicros(1/60))
  }
  expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
 })
})


describe('forced on-duty backup dispatch',()=>{
 it.each([false,true])('returns zero-mood full-recovery primaries and releases ordinary rotation after exit, predictive=%s',predictive=>{
  const config=fixture();config.mowerAlpha=true
  config.mowerPolicy={...config.mowerPolicy!,predictiveMoodControl:predictive,groupRestInFullOnMoodGap:true}
  config.positions[0]!.group='g';config.mowerSourcePlan!.room_1_1![0]!.group='g'
  config.mowerSourceRules!.restInFull=['A'];config.mowerSourceRules!.exhaustRequire=['A']
  config.initialMorale={A:0,R:24}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
  source.initial=false;source.firstInit=false
  const groupTasks=[[{group:'g',action:'on' as const,mode:'forced' as const}]]
  state.mowerShiftModel={count:1,groupTasks,evaluate:d=>d.planConditions,swap:d=>d,transition:()=>({}),activate:()=>{}}
  data.planConditions=[true];data.backupGroupTasks=groupTasks;data.groupShiftState.g=true
  state.occupants.room_1_1_0='R';state.bedOccupants.dormitory_1_4='A'
  Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:4,mood:0,timeStampMicros:0})
  Object.assign(data.operators.R!,{currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0})
  data.dorms[0]!.name='A';data.dorms[0]!.timeMicros=toMowerMicros(6)
  const forecast={...rates,forecastRates:(runtime:RuntimeState)=>({work:Object.fromEntries(Object.keys(runtime.morale).map(n=>[n,1])),recovery:Object.fromEntries(Object.keys(runtime.morale).map(n=>[n,4]))})}
  for(let n=0;n<10&&state.occupants.room_1_1_0!=='A';n++)settleRoster(state,forecast)
  expect(state.occupants.room_1_1_0).toBe('A')
  for(let n=0;n<6;n++){source.queue.tasks.push(new MowerTask());settleRoster(state,forecast)}
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.queue.tasks.some(task=>task.type===T.EXHAUST_OFF)).toBe(false)
  expect(source.data.operators.A!.workaholic).toBe(false)
  source.data.planConditions=[false]
  source.queue.tasks.push(new MowerTask());settleRoster(state,forecast)
  expect(state.occupants.room_1_1_0).toBe('R')
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.diagnostics.filter(d=>d.code==='mower-plan-solver-exception')).toEqual([])
 })
})


it('retains a stale forced-group departure across unchanged dispatch while unrelated work runs, then resumes on exit',()=>{
 const config=fixture();config.mowerAlpha=true
 config.positions[0]!.group='g';config.mowerSourcePlan!.room_1_1![0]!.group='g'
 config.initialMorale={A:0,R:24}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 const groupTasks=[[{group:'g',action:'on' as const,mode:'forced' as const}]]
 state.mowerShiftModel={count:1,groupTasks,evaluate:d=>d.planConditions,swap:d=>d,transition:()=>({}),activate:()=>{}}
 data.planConditions=[true];data.backupGroupTasks=groupTasks;data.groupShiftState.g=false
 Object.assign(data.operators.A!,{currentRoom:'room_1_1',currentIndex:0,mood:0,timeStampMicros:0})
 const task=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['K1','K2','K3','K4','A']}}),at=task.timeMicros
 source.queue.tasks=[task]
 settleRoster(state,rates)
 expect(task.executionFailure).toBeDefined()
 const original=structuredClone(task.plan),unrelated=new MowerTask()
 source.queue.tasks.push(unrelated)
 for(let n=0;n<6;n++)settleRoster(state,rates)
 expect(source.queue.tasks).toContain(task);expect(source.queue.tasks).not.toContain(unrelated)
 expect(task.plan).toEqual(original);expect(task.timeMicros).toBe(at)
 expect(state.occupants.room_1_1_0).toBe('A')
 source.data.planConditions=[false]
 settleRoster(state,rates)
 expect(state.occupants.room_1_1_0).toBe('R')
 expect(Object.values(state.bedOccupants)).toContain('A')
 expect(source.queue.tasks).not.toContain(task)
})
