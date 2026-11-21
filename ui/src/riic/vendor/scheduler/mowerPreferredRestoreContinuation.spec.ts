import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={room_1_1:[{agent:'A',group:'a',replacement:['X']}],room_1_2:[{agent:'B',group:'b',replacement:['Y','Z']}],dormitory_1:['K1','K2','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))}
 const config:RuntimeConfig={mowerAlpha:true,mowerTaskScheduling:{adjustForRunOrders:false},positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),beds:[2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===2})),mowerSourcePlan:rows,mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:['A','B'],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.6,rescueThreshold:.5,powerPlantCount:2,opeRestingPriority:[]},initialMorale:{A:5,B:5,X:24,Y:2,Z:24},idleOperators:[]}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 state.occupants={room_1_1_0:'X',room_1_2_0:'Z',dormitory_1_0:'K1',dormitory_1_1:'K2'}
 state.bedOccupants={dormitory_1_2:'A',dormitory_1_3:'B',dormitory_1_4:'Y'}
 for(const op of Object.values(data.operators)){
  const position=Object.entries({...state.occupants,...state.bedOccupants}).find(([,name])=>name===op.name)?.[0],split=position?.lastIndexOf('_')??-1
  Object.assign(op,{currentRoom:position?.slice(0,split)??'',currentIndex:position?Number(position.slice(split+1)):-1,mood:state.morale[op.name]??24,timeStampMicros:0,depletionRate:position?.startsWith('dorm')?0:1})
 }
 data.dorms=[new MowerDormState(['dormitory_1',2],'A',toMowerMicros(5)),new MowerDormState(['dormitory_1',3],'B',toMowerMicros(5)),new MowerDormState(['dormitory_1',4],'Y',toMowerMicros(5))]
 data.groupShiftState={a:true,b:true}
 const task=new MowerTask({time:-1,type:T.SELF_CORRECTION,plan:{room_1_2:['Y']}})
 task.preferredReplacementRestore=true;source.queue.tasks=[task]
 return {state,source,task}
}

describe('preferred-cover restoration continuation',()=>{
 it.each(['arrangementStarted','executionRetained','backupShiftActive','productShiftLocked'] as const)('preserves original remaining work protected by %s',protection=>{
  const {state,source,task}=fixture(),time=task.timeMicros,rates={workRate:()=>1,recoveryRate:()=>4}
  task[protection]=true
  if(protection==='executionRetained'){
   settleRoster(state,rates)
   expect(task.plan.room_1_2).toEqual(['Y'])
   expect(source.queue.tasks.includes(task)||state.occupants.room_1_2_0==='Y').toBe(true)
   expect(task.timeMicros).toBe(time)
   return
  }
  for(let step=0;step<40&&state.occupants.room_1_2_0!=='Y';step++){
   settleRoster(state,rates)
   if(state.occupants.room_1_2_0!=='Y')advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('Y')
  expect(task.timeMicros).toBe(time)
  expect(state.time).toBeLessThan(1/60)
 })
 it('still cancels an unstarted optional restoration when the preferred cover no longer qualifies',()=>{
  const {state,source,task}=fixture()
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.queue.tasks).not.toContain(task)
  expect(state.occupants.room_1_2_0).toBe('Z')
 })
})
