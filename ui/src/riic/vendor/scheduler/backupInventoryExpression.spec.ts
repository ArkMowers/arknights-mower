import {describe,it,expect} from 'vitest'
import {compileBackupExpression} from './backupExpression'
import {createRosterRuntime} from './rosterRuntime'

const compile=(source:unknown)=>compileBackupExpression(source,new Set())
const fixture=()=>createRosterRuntime({positions:[],beds:[]})

describe('safe inventory backup queries',()=>{
 it.each(['赤金','源石碎片','固源岩','装置','龙门币','全部经验（计算）'])('reads supported inventory %s',name=>{
  const state=fixture();state.mowerInventoryCounts={[name]:123}
  const expression=compile(`op_data.inventory_count('${name}') >= 123`)
  expect(expression.usesInventory).toBe(true);expect(expression.usesFacilityProduct).toBe(false)
  expect(expression.evaluate(state)).toBe(true)
 })
 it('distinguishes absent state from an initialized empty inventory',()=>{
  const expression=compile(`op_data.inventory_count('赤金')`),state=fixture()
  expect(()=>expression.evaluate(state)).toThrow('缺少库存状态')
  state.mowerInventoryCounts={};expect(expression.evaluate(state)).toBe(0)
 })
 it('reads live replacement tables and supplied experience values without inventing income',()=>{
  const expression=compile(`op_data.inventory_count('全部经验（计算）')`),state=fixture()
  state.mowerInventoryCounts={'全部经验（计算）':1200}
  expect(expression.evaluate(state)).toBe(1200)
  state.time=24;expect(expression.evaluate(state)).toBe(1200)
  state.mowerInventoryCounts={'全部经验（计算）':2200}
  expect(expression.evaluate(state)).toBe(2200)
 })
 it('supports serialized trees and chained thresholds without registering operators',()=>{
  const participants=new Set<string>(),expression=compileBackupExpression({left:"op_data.inventory_count('赤金')",operator:'>=',right:500},participants),state=fixture()
  state.mowerInventoryCounts={'赤金':500};expect(expression.evaluate(state)).toBe(true)
  expect(compile("0 <= op_data.inventory_count('赤金') < 501").evaluate(state)).toBe(true)
  expect(participants.size).toBe(0)
 })
 it.each(['基础作战记录','unknown','gold','__proto__','constructor'])('rejects non-native inventory item %s',name=>{
  expect(()=>compile(`op_data.inventory_count('${name}')`)).toThrow('不支持的副表仓库资源')
 })
 it.each([-1,NaN,Infinity])('rejects invalid host inventory amount %s',value=>{
  const state=fixture();state.mowerInventoryCounts={'赤金':value}
  expect(()=>compile(`op_data.inventory_count('赤金')`).evaluate(state)).toThrow('库存数量')
 })
 it('does not read inherited inventory properties',()=>{
  const state=fixture();state.mowerInventoryCounts=Object.create({'赤金':100}) as Record<string,number>
  expect(compile(`op_data.inventory_count('赤金')`).evaluate(state)).toBe(0)
 })
})

describe('safe effective facility-product backup queries',()=>{
 it.each(['gold','exp3','orirock','orirock_device','lmd','orundum'])('compares the native constant %s without executing a name',product=>{
  const state=fixture();state.mowerFacilityProducts={room_1_1:product}
  const expression=compile(`op_data.facility_product(room_1_1) == ${product}`)
  expect(expression.evaluate(state)).toBe(true)
  expect(expression.usesFacilityProduct).toBe(true);expect(expression.usesInventory).toBe(false)
 })
 it('reads changed facility products on each evaluation and preserves explicit unknown',()=>{
  const state=fixture(),expression=compile(`op_data.facility_product('room_1_1')`)
  expect(()=>expression.evaluate(state)).toThrow('缺少设施产物状态')
  state.mowerFacilityProducts={room_1_1:'gold'};expect(expression.evaluate(state)).toBe('gold')
  state.mowerFacilityProducts={room_1_1:'orirock_device'};expect(expression.evaluate(state)).toBe('orirock_device')
  state.mowerFacilityProducts={room_1_1:null};expect(expression.evaluate(state)).toBeNull()
  state.mowerFacilityProducts={};expect(expression.evaluate(state)).toBeNull()
 })
 it.each(['central','meeting','factory','contact','train','recycle','dormitory_4','gaming_3'])('accepts native base position %s',room=>{
  const state=fixture();state.mowerFacilityProducts={}
  expect(compile(`op_data.facility_product('${room}') is None`).evaluate(state)).toBe(true)
  expect(compile(`op_data.facility_product(${room}) is None`).evaluate(state)).toBe(true)
 })
 it.each(['room_0_1','room_4_1','dormitory_5','gaming_4','__proto__'])('rejects unknown room %s',room=>{
  expect(()=>compile(`op_data.facility_product('${room}')`)).toThrow('不支持的设施位置')
 })
 it('detects both dependencies even when evaluation short-circuits an absent state',()=>{
  const expression=compile(`True or (op_data.inventory_count('赤金') > 0 and op_data.facility_product('room_1_1') == 'gold')`)
  expect(expression.usesInventory).toBe(true);expect(expression.usesFacilityProduct).toBe(true)
  expect(expression.evaluate(fixture())).toBe(true)
  expect(compile('True')).toMatchObject({usesInventory:false,usesFacilityProduct:false})
 })
 it.each([
  `op_data.inventory_count()`, `op_data.inventory_count(1)`, `op_data.inventory_count('赤金', '装置')`,
  `op_data.inventory_count(op_data.party_time)`, `op_data.inventory_count('赤金').constructor`,
  `op_data.inventory_count('赤金')()`, `op_data.facility_product('room_1_1').__class__`,
  `op_data.facility_product('room_1_1') == arbitrary_name`,
 ])('rejects unsupported syntax %s',source=>expect(()=>compile(source)).toThrow('副表：'))
})


describe('effective facility-product counts',()=>{
 it.each(['gold','exp3','orirock','orirock_device','lmd','orundum'])('counts exact native product %s across different rooms',product=>{
  const state=fixture();state.mowerFacilityProducts={room_1_1:product,room_1_2:product,room_1_3:null,room_2_1:'unsupported'}
  const expression=compile(`op_data.facility_product_count('${product}')`)
  expect(expression.evaluate(state)).toBe(2)
  expect(expression).toMatchObject({usesFacilityProduct:true,usesInventory:false})
  expect(compile(`op_data.facility_product_count(${product})`).evaluate(state)).toBe(2)
 })
 it('counts product types once and distinguishes each rock recipe',()=>{
  const state=fixture();state.mowerFacilityProducts={room_1_1:'gold',room_1_2:'gold',room_1_3:'orirock',room_2_1:'orirock_device',room_2_2:'lmd',room_2_3:null,room_3_1:'unsupported'}
  const expression=compile('op_data.facility_product_type_count()')
  expect(expression.evaluate(state)).toBe(4)
  expect(expression).toMatchObject({usesFacilityProduct:true,usesInventory:false})
  state.mowerFacilityProducts={room_1_1:'gold',room_1_2:'gold'}
  expect(expression.evaluate(state)).toBe(1)
  state.mowerFacilityProducts={}
  expect(expression.evaluate(state)).toBe(0)
  expect(compile("op_data.facility_product_count('gold')").evaluate(state)).toBe(0)
 })
 it.each(["op_data.facility_product_count('gold')",'op_data.facility_product_type_count()'])('requires initialized products for %s',source=>{
  expect(()=>compile(source).evaluate(fixture())).toThrow('缺少设施产物状态')
 })
 it('reads fresh own product entries without counting prototype values',()=>{
  const state=fixture();state.mowerFacilityProducts=Object.assign(Object.create({room_1_1:'gold'}),{room_1_2:'exp3'}) as Record<string,string>
  expect(compile("op_data.facility_product_count('gold')").evaluate(state)).toBe(0)
  expect(compile('op_data.facility_product_type_count()').evaluate(state)).toBe(1)
  state.mowerFacilityProducts={room_1_1:'gold',room_1_2:'gold'}
  expect(compile("op_data.facility_product_count('gold')").evaluate(state)).toBe(2)
 })
 it('detects composite count and inventory dependencies even behind short-circuit',()=>{
  const expression=compile("op_data.facility_product_count('gold') == 2 or (op_data.inventory_count('赤金') < 1000 and op_data.facility_product_count('gold') == 3)")
  const state=fixture();state.mowerFacilityProducts={room_1_1:'gold',room_1_2:'gold'}
  expect(expression).toMatchObject({usesFacilityProduct:true,usesInventory:true})
  expect(expression.evaluate(state)).toBe(true)
  state.mowerFacilityProducts={room_1_1:'gold',room_1_2:'gold',room_1_3:'gold'};state.mowerInventoryCounts={'赤金':999}
  expect(expression.evaluate(state)).toBe(true)
  state.mowerInventoryCounts={'赤金':1000}
  expect(expression.evaluate(state)).toBe(false)
  expect(compile('True or op_data.facility_product_type_count() > 0')).toMatchObject({usesFacilityProduct:true,usesInventory:false})
 })
 it.each(['unknown','exp','fragment','money','__proto__','constructor'])('rejects unsupported count product %s',name=>{
  expect(()=>compile(`op_data.facility_product_count('${name}')`)).toThrow('不支持的产物或订单类型')
 })
 it.each([
  'op_data.facility_product_count()', 'op_data.facility_product_count(1)', "op_data.facility_product_count('gold', 'exp3')",
  'op_data.facility_product_count(op_data.party_time)', "op_data.facility_product_count('gold').constructor",
  "op_data.facility_product_count('gold')()", "op_data.facility_product_type_count('gold')",
  'op_data.facility_product_type_count(1)', 'op_data.facility_product_type_count().constructor',
 ])('rejects unsupported count syntax %s',source=>expect(()=>compile(source)).toThrow('副表：'))
})
