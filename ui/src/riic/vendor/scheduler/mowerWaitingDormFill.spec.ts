import {describe,expect,it} from 'vitest'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig,type RuntimeRates} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(vacant:boolean){
 const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,
  positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']}],
  beds:[{id:'dormitory_1_0',roomId:'dormitory_1',vip:true}],
  initialMorale:{A:24,R:0,S:24},idleOperators:['S'],
  mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},
  mowerPolicy:{restingThreshold:0,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[{agent:'Free',group:'',replacement:[]}]},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0,priorityReplacement:['R']},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 if(!vacant)state.bedOccupants.dormitory_1_0='S'
 for(const op of Object.values(source.data.operators)){op.currentRoom='';op.currentIndex=-1;op.mood=state.morale[op.name]??24;op.timeStampMicros=0}
 for(const [slot,name] of Object.entries({...state.occupants,...state.bedOccupants})){
  if(!name)continue
  const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1))
 }
 source.data.dorms[0]!.name=vacant?'':'S'
 const waiting=new MowerTask({type:T.SHIFT_OFF,time:-1,plan:{dormitory_1:['R']}})
 waiting.executionRetained=true
 source.waitingRecovery=[{task:waiting,reason:'backup-veto',conditionIndexes:[],observedNames:[],observation:'[[],{},[],[]]',deadlines:{},names:[],rooms:[]}]
 source.queue.tasks=[new MowerTask()]
 const rates:RuntimeRates={workRate:()=>1,recoveryRate:()=>4}
 return {state,source,waiting,rates}
}

describe('ordinary dorm fill with parked reservations',()=>{
 it.each(['occupied-destination','vacant-destination','occupied-source'] as const)('does not regenerate a reserved fill through repeated dispatch for %s',reservation=>{
  const vacant=reservation==='vacant-destination'
  const {state,source,waiting,rates}=fixture(vacant),time=waiting.timeMicros,plan=waiting.plan
  if(reservation==='occupied-source'){
   delete plan.dormitory_1;plan.room_1_1=['S'];waiting.type=T.SHIFT_ON;waiting.executionRetained=false
  }
  for(let repeat=0;repeat<6;repeat++){
   let next=0
   for(let step=0;step<4;step++){
    settleRoster(state,rates)
    expect(source.queue.tasks.some(task=>Object.keys(task.dormFillPlan).length)).toBe(false)
    next=nextRosterActionHours(state,rates)
    if(next>1/60)break
    advanceRoster(state,next,rates)
   }
   expect(next).toBeGreaterThan(1/60)
   advanceRoster(state,Math.min(next,1/60),rates)
  }
  expect(source.waitingRecovery?.map(wait=>wait.task)).toEqual([waiting])
  expect(waiting.timeMicros).toBe(time);expect(waiting.plan).toBe(plan)
  expect(source.trace.some(task=>task.type==='FILL_DORM'||Object.keys(task.plan).some(room=>room.startsWith('dorm')))).toBe(false)

  const pages=['INFRA_DETAILS','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','CLUE_GIVE_AWAY','INFRA_DETAILS'],requests:string[]=[]
  rates.mowerClueIO=(request,current)=>({delayMicros:0,observe:()=>{
   requests.push(request.kind)
   return {kind:request.kind,observedAtMicros:toMowerMicros(current.time),value:request.kind==='scene'?pages.shift()??'INFRA_DETAILS':null}
  }})
  const independent=new MowerTask({time:state.time,type:T.CLUE})
  source.queue.tasks.push(independent)
  settleRoster(state,rates)
  expect(requests).toContain('read-time');expect(requests).not.toContain('save-exception')
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.waitingRecovery?.map(wait=>wait.task)).toEqual([waiting]);expect(waiting.timeMicros).toBe(time)

  // A revised remaining arrangement releases the old bed and candidate reservation.
  waiting.plan={room_1_1:['A']}
  source.queue.tasks.push(new MowerTask({time:state.time}))
  for(let step=0;step<10&&state.bedOccupants.dormitory_1_0!=='R';step++){
   settleRoster(state,rates)
   if(state.bedOccupants.dormitory_1_0!=='R')advanceRoster(state,nextRosterActionHours(state,rates),rates)
  }
  expect(state.bedOccupants.dormitory_1_0).toBe('R')
  expect(source.waitingRecovery?.map(wait=>wait.task)).toEqual([waiting]);expect(waiting.timeMicros).toBe(time)
 })
})
