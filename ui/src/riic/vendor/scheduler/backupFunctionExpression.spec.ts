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
