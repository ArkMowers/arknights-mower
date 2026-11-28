import {expect,it} from 'vitest'
import {createRosterRuntime,settleRoster,advanceRoster,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {mowerUpdateDetail} from './mowerObservations'
import {MowerTask} from './mowerTaskQueue'

it('dispatches a sustainable ordinary recall and executes the requesting group normal return',()=>{
 const keepers=['K1','K2']
 const config:RuntimeConfig={mowerAlpha:true,mowerDormFillers:true,positions:[
  ...['A','B','C'].map((primary,index)=>({id:`room_1_${index+1}_0`,roomId:`room_1_${index+1}`,primary,candidates:[index===2?'Y':'X'],group:index?'request':'',lowerLimit:0,upperLimit:24,shiftOffThreshold:15})),
  ...keepers.map((primary,index)=>({id:`dormitory_1_${index}`,roomId:'dormitory_1',primary,candidates:[],permanent:true,dormitory:true}))
 ],beds:[2,3,4].map(index=>({id:`dormitory_1_${index}`,roomId:'dormitory_1',vip:true})),initialMorale:{A:3,B:0,C:16,X:24,Y:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,rescueThreshold:.75,groupRestInFullOnMoodGap:false,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['X']}],room_1_2:[{agent:'B',group:'request',replacement:['X']}],room_1_3:[{agent:'C',group:'request',replacement:['Y']}],dormitory_1:[...keepers.map(agent=>({agent,group:'',replacement:[]})),...[2,3,4].map(()=>({agent:'Free',group:'',replacement:[]}))]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 state.occupants.room_1_1_0='X';state.bedOccupants.dormitory_1_2='A'
 mowerUpdateDetail(source.data,'A',3,'dormitory_1',2,true)
 mowerUpdateDetail(source.data,'X',24,'room_1_1',0,true)
 mowerUpdateDetail(source.data,'B',0,'room_1_2',0,true)
 mowerUpdateDetail(source.data,'C',16,'room_1_3',0,true)
 for(const [name,op] of Object.entries(source.data.operators)){op.mood=state.morale[name]??24;op.timeStampMicros=0;op.moodIsPrediction=false}
 source.queue.tasks=[new MowerTask()]
 const rates={workRate:()=>1,recoveryRate:()=>4,forecastMoods:(s:RuntimeState)=>({...s.morale}),forecastRates:(s:RuntimeState)=>({work:Object.fromEntries(Object.keys(s.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(s.morale).map(name=>[name,4]))})}
 settleRoster(state,rates)
 expect(state.occupants.room_1_1_0).toBe('A')
 expect(state.occupants.room_1_2_0).toBe('X')
 expect(state.occupants.room_1_3_0).toBe('Y')
 expect(Object.values(state.bedOccupants)).toContain('B')
 expect(Object.values(state.bedOccupants)).toContain('C')
 const returnTask=source.queue.tasks.find(task=>task.plan.room_1_2?.[0]==='B'&&task.plan.room_1_3?.[0]==='C')!
 expect(returnTask).toBeDefined()
 expect(returnTask.time).toBeCloseTo(2-8/60)
 advanceRoster(state,returnTask.time-state.time,rates);settleRoster(state,rates)
 expect(state.occupants.room_1_2_0).toBe('B')
 expect(state.occupants.room_1_3_0).toBe('C')
 expect(state.morale.A).toBeGreaterThan(0)
 expect(state.morale.B).toBeLessThan(24)
 expect(state.diagnostics.some(d=>d.code==='mower-plan-solver-exception')).toBe(false)
})
