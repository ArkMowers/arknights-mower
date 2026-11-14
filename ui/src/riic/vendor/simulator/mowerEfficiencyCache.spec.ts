import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import { resolveOperatorCharId as id } from '../domain/operatorIdentifiers'
import {simulateSchedule} from './scheduleSimulation'

function crossing(control: '令' | '夕') {
 const ws=createDefaultWorkspace()
 ws.mainPlan.facilities.central.slots=[{occupant:{kind:'operator',operatorId:control},groupId:null,replacements:[]}]
 ws.mainPlan.facilities.room_2_1.slots=[{occupant:{kind:'operator',operatorId:'迷迭香'},groupId:null,replacements:[]}]
 ws.mainPlan.facilities.room_2_1.type='manufacture';ws.mainPlan.facilities.room_2_1.product='gold';ws.mainPlan.facilities.room_3_1.slots=[{occupant:{kind:'operator',operatorId:'黑键'},groupId:null,replacements:[]}];ws.mainPlan.conf.workaholic=[control,'迷迭香','黑键']
 return compileRosterSchedule(ws,{operatorMorale:{[id(control)]:13}})
}
describe('production efficiency caches follow actual mood skill boundaries',()=>{
 it.each(['令','夕'] as const)('%s refreshes perception after crossing 12 without a roster movement',(name)=>{
  const s=crossing(name),r=simulateSchedule(s,{sampleHours:2,maxStepHours:.25,warmupModel:'hourly',recordSegments:true,consumptionOverrides:{[id(name)]:1,[id('迷迭香')]:0}})
  expect(r.success).toBe(true)
  expect(r.events.filter(e=>e.type==='shift-off'||e.type==='shift-on')).toHaveLength(0)
  const before=r.segments.find(x=>x.start===0)!.efficiencyPercent.room_2_1!
  const after=r.segments.find(x=>x.start>=1.25)!.efficiencyPercent.room_2_1!
  expect(after-before).toBe(name==='令'?10:-10)
  expect(r.segments.find(x=>x.start>=1.25)!.efficiencyPercent.room_3_1!-r.segments[0]!.efficiencyPercent.room_3_1!).toBe(name==='令'?5:-5)
  expect(r.rooms.find(x=>x.roomId==='room_2_1')!.averageEfficiencyPercent).toBeCloseTo((before+after)/2,8)
 })
 it('Totter refreshes its local productivity after losing four mood points',()=>{
  const ws=createDefaultWorkspace();ws.mainPlan.facilities.room_2_1.slots=[{occupant:{kind:'operator',operatorId:'铅踝'},groupId:null,replacements:[]}];ws.mainPlan.facilities.room_2_1.type='manufacture';ws.mainPlan.facilities.room_2_1.product='gold';ws.mainPlan.conf.workaholic=['铅踝']
  const r=simulateSchedule(compileRosterSchedule(ws,{operatorMorale:{[id('铅踝')]:21}}),{sampleHours:2,maxStepHours:.25,warmupModel:'hourly',recordSegments:true,consumptionOverrides:{[id('铅踝')]:1}})
  expect(r.success).toBe(true);expect(r.events.filter(e=>e.type==='shift-off'||e.type==='shift-on')).toHaveLength(0)
  const before=r.segments.find(x=>x.start===0)!.efficiencyPercent.room_2_1!,after=r.segments.find(x=>x.start>=1.25)!.efficiencyPercent.room_2_1!
  expect(after-before).toBe(-5);expect(r.rooms.find(x=>x.roomId==='room_2_1')!.averageEfficiencyPercent).toBeCloseTo((before+after)/2,8)
 })
 it('hourly warmup uses the operator session hour rather than the wall clock hour',()=>{
  const ws=createDefaultWorkspace();ws.mainPlan.facilities.room_2_1.slots=[{occupant:{kind:'operator',operatorId:'阿罗玛'},groupId:null,replacements:[]}];ws.mainPlan.facilities.room_2_1.product='gold';ws.mainPlan.conf.workaholic=['阿罗玛']
  const r=simulateSchedule(compileRosterSchedule(ws),{sampleHours:1,maxStepHours:.25,warmupModel:'hourly',recordSegments:true,initialWorkHours:{[id('阿罗玛')]:.5},consumptionOverrides:{[id('阿罗玛')]:0}})
  expect(r.success).toBe(true);expect(r.events).toEqual([])
  expect(r.segments.filter(x=>x.start<.5).every(x=>x.efficiencyPercent.room_2_1===126)).toBe(true)
  expect(r.segments.filter(x=>x.start>=.5).every(x=>x.efficiencyPercent.room_2_1===128)).toBe(true)
  expect(r.rooms.find(x=>x.roomId==='room_2_1')!.averageEfficiencyPercent).toBeCloseTo(127,8)
 })

 it('Fiammetta resets hourly warmup at a fractional session start',()=>{
  const ws=createDefaultWorkspace();ws.mainPlan.facilities.room_2_1.slots=[{occupant:{kind:'operator',operatorId:'阿罗玛'},groupId:null,replacements:[]}];ws.mainPlan.facilities.room_2_1.product='gold';ws.mainPlan.conf.workaholic=['阿罗玛']
  ws.mainPlan.facilities.dormitory_1.slots=[{occupant:{kind:'operator',operatorId:'菲亚梅塔'},groupId:null,replacements:['阿罗玛']}]
  const r=simulateSchedule(compileRosterSchedule(ws,{operatorMorale:{[id('菲亚梅塔')]:23,[id('阿罗玛')]:20}}),{sampleHours:6.5,maxStepHours:.25,warmupModel:'hourly',recordSegments:true,consumptionOverrides:{[id('阿罗玛')]:1}})
  expect(r.success).toBe(true)
  const exchange=r.events.find(e=>e.type==='fiammetta')!.time
  expect(exchange).toBeCloseTo(4,8)
  expect(r.operators.find(operator=>operator.operatorId===id('菲亚梅塔'))!.initialMorale).toBe(16)
  expect(r.events.some(event=>event.type==='fiammetta'&&event.time<4)).toBe(false)
  const absence=r.segments.filter(x=>x.occupants.room_2_1_0!==id('阿罗玛'))
  expect(absence).not.toHaveLength(0)
  const returned=absence[absence.length-1]!.end
  expect((returned-exchange)*3600).toBeCloseTo(.5,4)
  const warmed=r.segments.find(x=>Math.abs(x.start-returned-1)<1e-8)
  expect(warmed?.efficiencyPercent.room_2_1).toBe(128)
  expect(r.segments.filter(x=>x.start>=returned&&x.start<returned+1-1e-8).every(x=>x.efficiencyPercent.room_2_1===126)).toBe(true)
  // The first four session hours average 129%; the post-charge session restarts at 126%.
  const expected=(129*exchange+100*(returned-exchange)+126+128+130*(6.5-returned-2))/6.5
  expect(r.rooms.find(x=>x.roomId==='room_2_1')!.averageEfficiencyPercent).toBeCloseTo(expected,8)
 })

})
