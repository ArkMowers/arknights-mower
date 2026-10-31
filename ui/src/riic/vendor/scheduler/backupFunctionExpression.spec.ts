import { describe, expect, it } from 'vitest'
import { compileBackupExpression } from './backupExpression'
import { createRosterRuntime } from './rosterRuntime'

const compile = (source: unknown) => compileBackupExpression(source, new Set())
const state = () => createRosterRuntime({ positions: [], beds: [] })

describe('backup condition functions', () => {
  it.each([
    ['max', ['3', '9', '4'], 9],
    ['min', ['3', '9', '4'], 3],
    ['sum', ['3', '9', '4'], 16],
    ['any', ['False', 'True', 'False'], true],
    ['all', ['True', 'False', 'True'], false],
    ['abs', ['-8'], 8],
    ['max', ['7'], 7],
    ['min', ['7'], 7],
    ['sum', ['7'], 7],
    ['any', ['False'], false],
    ['all', ['True'], true]
  ])('evaluates saved %s arguments', (name, args, expected) => {
    expect(compile({ function: name, args }).evaluate(state())).toBe(expected)
  })

  it('evaluates nested expressions using live query observations', () => {
    const expression = compile({ left: { function: 'max', args: [
      "op_data.inventory_count('赤金')",
      { function: 'sum', args: [{ left: '3', operator: '+', right: '4' }, '8'] }
    ] }, operator: '>', right: '20' })
    const runtime = state()
    runtime.mowerInventoryCounts = { 赤金: 10 }
    expect(expression.usesInventory).toBe(true)
    expect(expression.evaluate(runtime)).toBe(false)
    runtime.mowerInventoryCounts = { 赤金: 30 }
    expect(expression.evaluate(runtime)).toBe(true)
  })

  it.each([
    'max(3, min(9, 4), 8) == 8',
    'max([7]) == 7',
    'min([7]) == 7',
    'sum([3, 9, 4]) == 16',
    'any([False, 3 > 2])',
    'all([True, abs(-8) == 8])'
  ])('accepts equivalent custom text %s', (source) => {
    expect(compile(source).evaluate(state())).toBe(true)
  })

  it.each([
    { function: 'max', args: [] },
    { function: 'abs', args: ['1', '2'] },
    { function: 'sum', args: [] },
    { function: 'eval', args: ['1'] },
    'max(1)', 'sum(1, 2)', 'abs(1, 2)', 'all([True)', 'min(1, 2', 'eval(1)'
  ])('rejects unsupported or incomplete calls %j', (source) => {
    expect(() => compile(source)).toThrow()
  })
})

describe('function arithmetic follows native power restrictions and precedence',()=>{
 it.each([
  ['sum([1, 2]) * 2',6],['sum([1, 2]) ** 2',9],['-2 ** 2',-4],['(-2) ** 2',4],
  ['2 * 3 ** 2 + 1',19],['2 ** (3)',8],['2 ** +3',8],['abs(-3) ** 2',9],
 ])('evaluates %s', (source,expected)=>expect(compile(source).evaluate(state())).toBe(expected))
 it.each(['2 ** -2','2 ** 65','2 ** 1.5','2 ** 3 ** 2','2 ** sum([1,2])'])('rejects a non-native exponent in %s',source=>expect(()=>compile(source)).toThrow())
 it('preserves saved function nodes as arithmetic operands',()=>{
  const source={left:{function:'sum',args:['1','2']},operator:'**',right:'2'}
  expect(compile(source).evaluate(state())).toBe(9)
 })
 it.each(['any([True, 1 / 0])','all([False, 1 / 0])'])('evaluates all list items before %s',source=>expect(()=>compile(source).evaluate(state())).toThrow())
})
