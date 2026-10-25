import {describe,it,expect,vi} from 'vitest'
import {createDefaultConfig,createRoom} from '../domain/defaults'
import {OPERATORS} from '../domain/operators'
import {mowerCoordinationRates} from './mowerCoordinationRates'
import {evaluateDormitoryRecovery} from '../engine/dormitoryRecovery'
import * as recoveryEngine from '../engine/dormitoryRecovery'
import * as globalContext from '../engine/globalContext'

const id=(name:string)=>OPERATORS.find(op=>op.name===name)!.charId
function config(){
 const c=createDefaultConfig()
 c.rooms=[];c.controlOperatorIds=[];c.facilities.dormitories=[5]
 c.facilityOperatorIds.dormitories=[['杜林','闪灵','菲亚梅塔','芬'].map(id)]
 c.operatorMorale=Object.fromEntries(c.facilityOperatorIds.dormitories[0]!.map(name=>[name,10]))
 return c
}
describe('isolated coordination rate estimates',()=>{
 it('bounds recovery without single or group bonuses, retaining self penalties and Fiammetta exclusion',()=>{
  const c=config(),before=JSON.stringify(c),r=mowerCoordinationRates(c,[5000])
  expect(r.recovery[id('芬')]).toBeCloseTo(4)
  expect(r.recovery[id('杜林')]).toBeCloseTo(3.9)
  expect(r.recovery[id('菲亚梅塔')]).toBe(2)
  expect(JSON.stringify(c)).toBe(before)
  expect(evaluateDormitoryRecovery(c,0,new Map(Object.entries(c.operatorMorale)),5000,new Map([[id('闪灵'),id('芬')]])).rates.get(id('芬'))).toBeCloseTo(5)
 })
 it('recomputes working consumption from projected providers instead of a cached roster',()=>{
  const c=config(),room=createRoom('room_1_1','manufacture');room.operatorIds=[id('芬')];room.operatorCount=1;c.rooms=[room]
  c.facilityOperatorIds.dormitories=[[]];c.controlOperatorIds=[id('阿米娅')];c.operatorMorale[id('阿米娅')]=24
  expect(mowerCoordinationRates(c,[5000]).work[id('芬')]).toBeCloseTo(.95)
  c.operatorMorale[id('阿米娅')]=0
  expect(mowerCoordinationRates(c,[5000]).work[id('芬')]).toBeCloseTo(1)
 })
 it('uses room atmosphere and explicit test rates without mutating their source',()=>{
  const c=config(),overrides={work:{[id('芬')]:.75},recovery:{[id('菲亚梅塔')]:1.5}}
  expect(mowerCoordinationRates(c,[0],overrides)).toMatchObject({work:{[id('芬')]:.75},recovery:{[id('芬')]:2,[id('杜林')]:1.9,[id('菲亚梅塔')]:1.5}})
  expect(overrides.recovery[id('菲亚梅塔')]).toBe(1.5)
 })
 it('shares one unchanged global context across distinct dormitories in one forecast',()=>{
  const c=config();c.facilities.dormitories=[5,4,3,0]
  c.facilityOperatorIds.dormitories=[['流明','芬'],['纯烬艾雅法拉','香草'],['杜林','菲亚梅塔'],[]].map(names=>names.map(id))
  c.operatorMorale=Object.fromEntries(c.facilityOperatorIds.dormitories.flat().map(name=>[name,10]))
  const before=JSON.stringify(c),build=vi.spyOn(globalContext,'buildRiicGlobalContext'),evaluate=vi.spyOn(recoveryEngine,'evaluateDormitoryRecovery')
  try {
   const result=mowerCoordinationRates(c,[5000,4000,3000,0])
   expect(result.recovery[id('芬')]).toBe(4)
   expect(result.recovery[id('香草')]).toBe(3.5)
   expect(result.recovery[id('杜林')]).toBeCloseTo(2.9)
   expect(result.recovery[id('菲亚梅塔')]).toBe(2)
   expect(build).toHaveBeenCalledTimes(1)
   expect(evaluate).toHaveBeenCalledTimes(4)
   const context=build.mock.results[0]!.value,morale=build.mock.calls[0]![2]
   for(const args of evaluate.mock.calls){expect(args[0]).toBe(c);expect(args[2]).toBe(morale);expect(args[6]).toBe(context)}
   expect(JSON.stringify(c)).toBe(before)
  }finally{evaluate.mockRestore();build.mockRestore()}
 })
 it('rebuilds the context after provider mood and facility configuration change',()=>{
  const c=config(),power=createRoom('power','power');power.operatorIds=[id('Lancet-2')];power.operatorCount=1
  c.rooms=[power];c.controlOperatorIds=[id('森蚺')];c.operatorMorale[id('森蚺')]=24
  const build=vi.spyOn(globalContext,'buildRiicGlobalContext')
  try {
   expect(mowerCoordinationRates(c,[5000]).recovery[id('杜林')]).toBeCloseTo(3.9)
   const first=build.mock.results[0]!.value
   expect(first.effectivePowerStations.count).toBe(3)
   c.operatorMorale[id('森蚺')]=0;c.zeroMoraleOperatorIds=[id('森蚺')];c.facilities.dormitories=[3]
   expect(mowerCoordinationRates(c,[3000]).recovery[id('杜林')]).toBeCloseTo(2.9)
   expect(build).toHaveBeenCalledTimes(2)
   expect(build.mock.results[1]!.value).not.toBe(first)
   expect(build.mock.results[1]!.value.effectivePowerStations.count).toBe(1)
   expect(first.effectivePowerStations.count).toBe(3)
  }finally{build.mockRestore()}
 })
 it('does not build a recovery context when no dormitory has a known level',()=>{
  const c=config();c.facilities.dormitories=[0]
  const build=vi.spyOn(globalContext,'buildRiicGlobalContext')
  try{expect(mowerCoordinationRates(c,[0]).recovery).toEqual({});expect(build).not.toHaveBeenCalled()}finally{build.mockRestore()}
 })
})
