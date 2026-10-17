import {describe,it,expect} from 'vitest'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,makeMowerSchedulingData} from './mowerSourceRuntime'
import {mowerUpdateDetail} from './mowerObservations'
import {alphaRestingTier} from './mowerAlphaDorm'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {evaluateBackupExpression} from './backupPlans'
const rates={workRate:()=>1,recoveryRate:()=>4}
function fixture():RuntimeConfig {
 const keepers=['K1','K2','K3','K4']
 return {positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},...keepers.map((name,i)=>({id:'dormitory_1_'+i,roomId:'dormitory_1',primary:name,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:16,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(name=>({agent:name,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
}
describe('integrated Mower source scheduler',()=>{
 it('retains temporary standby promotion and identity when rebuilding scheduling data',()=>{
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
  expect(op.standbyLowPriority).toBe(true)
  expect(alphaRestingTier(rebuilt,'A')).toBe(2)
  expect(rebuilt.canStandby(op)).toBe(true)
  expect(rebuilt.isGroupShiftAnchor(op)).toBe(false)
  mowerUpdateDetail(rebuilt,'A',24,'room_1_1',0,true)
  expect(op.standbyLowPriority).toBe(false)
  expect(alphaRestingTier(rebuilt,'A')).toBe(4)
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
  expect(candidate.mood).toBe(24);candidate.depletionRate=0;candidate.timeStampMicros=source.data.nowMicros
  state.morale.A=10;source.queue.tasks=[new MowerTask({time:state.time,type:T.FIAMMETTA})]
  settleRoster(state,rates)
  expect(state.events.find(event=>event.type==='fiammetta')).toBeUndefined()
  expect(state.morale.A).toBe(10);expect(state.morale[fia]).toBe(24)
  expect(candidate.mood).toBe(24)
  expect(source.queue.tasks.find(task=>task.type===T.FIAMMETTA)!.time).toBe(11.5)
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
  state.time=1;source.data.nowMicros=3_600_000_000;bed.timeMicros=5*3_600_000_000;op.timeStampMicros=0
  const fiaTimestamp=source.data.operators[fia]!.timeStampMicros
  source.queue.tasks=[new MowerTask({time:1,type:T.FIAMMETTA,plan:{dormitory_1:[fia,'K2','K3','K4','R']}})]
  settleRoster(state,rates)
  expect(bed.timeMicros).toBe(5*3_600_000_000)
  expect(op.timeStampMicros).toBe(0)
  expect(source.data.operators[fia]!.timeStampMicros).toBe(fiaTimestamp)
 })

 it.each([{alpha:false,named:false},{alpha:true,named:false},{alpha:false,named:true},{alpha:true,named:true}])('retains a full-to-full Fiammetta charge without polling ($alpha, named=$named)',({alpha,named})=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=alpha
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.idleOperators=['X'];config.initialMorale={A:24,R:24,X:24,[fia]:24}
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  for(const [slot,name] of Object.entries(state.occupants)){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0}
  source.queue.tasks=[new MowerTask({type:T.FIAMMETTA,...(named?{plan:{room_1_1:['Current'],dormitory_1:['A',fia]},metadata:'A'}:{})})]
  const before={...state.occupants}
  settleRoster(state,rates)
  const retained=source.queue.tasks.find(task=>task.type===T.FIAMMETTA)!
  expect(retained.executionFailure).toBeDefined();expect(retained.timeMicros).toBe(0)
  expect(retained.plan.room_1_1).toBeUndefined()
  expect(state.events.filter(e=>e.type==='fiammetta')).toHaveLength(0)
  expect(state.occupants).toEqual(before)
  const traceCount=source.trace.filter(t=>t.type==='FIAMMETTA').length
  const independent=new MowerTask({time:.01});source.queue.tasks.push(independent)
  state.time=.01;settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toEqual([retained])
  // The independent arrangement moved R into a Free bed and refreshed the observed state.
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traceCount+1)
  expect(source.data.operators.R!.currentRoom).toBe('dormitory_1')
  expect(retained.executionFailure).toBeDefined()
  for(let attempt=0;attempt<3;attempt++)settleRoster(state,rates)
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traceCount+1)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toEqual([retained])
  expect(state.events.filter(e=>e.type==='fiammetta')).toHaveLength(0)
  expect(retained.timeMicros).toBe(0)
  expect(state.diagnostics.some(d=>d.message.includes('五分钟'))).toBe(false)
  const target=retained.plan.dormitory_1![0]!
  state.morale[target]=10
  const op=source.data.operators[target]!;op.mood=10;op.timeStampMicros=36_000_000;op.moodIsPrediction=false
  settleRoster(state,rates)
  expect(retained.executionFailure).toBeUndefined()
  expect(state.events.some(e=>e.type==='fiammetta'&&e.operators[1]===target)).toBe(true)
  expect(source.queue.tasks).not.toContain(retained)
  expect(state.occupants.dormitory_1_0).toBe(fia)
  expect(state.occupants.room_1_1_0).toBe('A')
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
