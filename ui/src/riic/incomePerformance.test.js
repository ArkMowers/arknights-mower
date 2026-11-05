import { afterEach, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import { appendFileSync } from 'node:fs'
import { performance } from 'node:perf_hooks'
import process from 'node:process'
import plan from './fixtures/income-21trade-3proviso.json'
import { defaultIncomeSettings, incomeRequest } from './income'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import * as productionModule from './vendor/simulator/productionTimeline'
import { runCalculationBridge } from './vendor/workbench/calculationBridge'

const originalCopy = MowerOperatorState.prototype.copyForProjection
let controllerSpy
function restoreBaseline() {
  MowerOperatorState.prototype.copyForProjection = originalCopy
  controllerSpy?.mockClear()
  controllerSpy?.mockRestore()
  controllerSpy = undefined
  vi.restoreAllMocks()
}
afterEach(restoreBaseline)
const plain = (value) =>
  Object.fromEntries(Object.entries(value).filter(([, value]) => typeof value !== 'function'))

it('copies every projection constructor input and retains independent position setters and nested data', () => {
  const source = new MowerOperatorState({
    name: 'A',
    nativeName: 'A',
    room: 'room_1_1',
    index: 1,
    group: 'g',
    replacement: ['B'],
    groupBindings: [{ group: 'g', replacement: ['B'] }],
    operatorType: 'high',
    restingPriority: 'standby',
    alpha: true,
    currentRoom: 'dormitory_1',
    currentIndex: 2,
    mood: 13,
    calculatedMoodSnapshot: { timeMicros: 5, values: { A: 12 } },
    timeStampMicros: 4,
    depletionRate: 1.2,
    exhaustTimeMicros: 19,
    temporaryDormFill: true,
    dormMoodFallback: 'dormitory_1',
    restMoodReleaseLimit: 18,
    moodIsPrediction: true,
    customMoodLimit: true,
    dormMoodPeers: { B: 3 },
    dormRecoveryObservation: ['dormitory_1', 2, 4, 8],
    dormPositionVersion: 9,
    dormRecoveryRoom: 'dormitory_1',
    dormRecoveryIndex: 2,
    dormRecoveryFixed: [['B', 0, 2]],
    singleRecoveryManager: true,
    restingFromTrain: true,
    idleRestCheck: [19, 13, 4],
    lowerLimit: 2,
    upperLimit: 19,
    workaholic: true,
    exhaustRequire: true,
    restInFull: true,
    restMoodLimit: true,
    workshop: true
  })
  const legacy = new MowerOperatorState({
    ...source,
    projectedMoodResting: source.projectedMoodResting ?? source.isResting(),
    replacement: [...source.replacement]
  })
  const copied = source.copyForProjection()
  expect(plain(copied)).toEqual(plain(legacy))
  copied.currentRoom = 'room_2_1'
  legacy.currentRoom = 'room_2_1'
  expect(plain(copied)).toEqual(plain(legacy))
  expect(source.currentRoom).toBe('dormitory_1')
  copied.setProjectedPosition('room_3_1', 1)
  expect(copied.currentRoom).toBe('room_3_1')
  expect(source.currentIndex).toBe(2)
  copied.replacement.push('C')
  copied.groupBindings[0].replacement.push('C')
  copied.dormRecoveryFixed.push(['C', 1, 3])
  copied.dormMoodPeers.C = 7
  expect(source.replacement).toEqual(['B'])
  expect(source.groupBindings[0].replacement).toEqual(['B'])
  expect(source.dormRecoveryFixed).toEqual([['B', 0, 2]])
  expect(source.dormMoodPeers).toEqual({ B: 3 })
})

const benchmark = process.env.MOWER_INCOME_BENCHMARK === '1'
it(
  'preserves income, inventories and the complete supplied-plan scheduling trace',
  () => {
    const modes = benchmark
      ? ['baseline', 'optimized', 'optimized', 'baseline']
      : ['baseline', 'optimized']
    const hashes = []
    for (const mode of modes) {
      restoreBaseline()
      if (mode === 'baseline') {
        MowerOperatorState.prototype.copyForProjection = function () {
          return new MowerOperatorState({
            ...this,
            projectedMoodResting: this.projectedMoodResting ?? this.isResting(),
            replacement: [...this.replacement]
          })
        }
        const create = productionModule.createProductionTimeline
        controllerSpy = vi
          .spyOn(productionModule, 'createProductionTimeline')
          .mockImplementation((...args) => {
            const controller = create(...args)
            let revision = 0
            return { ...controller, productVersion: () => ++revision }
          })
      }
      const settings = {
        ...defaultIncomeSettings(),
        operatorMode: 'maximum',
        inventorySource: 'manual',
        finiteInventory: false,
        weightMode: 'custom',
        warmupDays: 0,
        sampleDays: 1,
        droneRoom: 'room_3_3'
      }
      const request = incomeRequest(plan, settings)
      const start = performance.now()
      // The bridge exposes an exact short horizon without changing editable day limits.
      request.options.simulationOptions.sampleHours = benchmark ? 24 : 6
      const result = runCalculationBridge(request.workspace, request.options)
      const elapsed = performance.now() - start
      expect(result.success, result.error).toBe(true)
      const hash = createHash('sha256').update(JSON.stringify(result)).digest('hex')
      hashes.push(hash)
      if (process.env.MOWER_INCOME_BENCHMARK_LOG)
        appendFileSync(
          process.env.MOWER_INCOME_BENCHMARK_LOG,
          JSON.stringify({ mode, hours: benchmark ? 24 : 6, milliseconds: elapsed, hash }) + '\n'
        )
    }
    restoreBaseline()
    expect(new Set(hashes).size).toBe(1)
  },
  benchmark ? 180000 : 60000
)

it('shares position accessors while keeping positions and the extracted projection setter independent', () => {
  const a = new MowerOperatorState({ name: 'A', currentRoom: 'room_1_1', currentIndex: 0 })
  const b = new MowerOperatorState({ name: 'B', currentRoom: 'room_2_1', currentIndex: 1 })
  for (const key of ['currentRoom', 'currentIndex']) {
    expect(Object.keys(a)).toContain(key)
    expect(Object.getOwnPropertyDescriptor(a, key).get).toBe(
      Object.getOwnPropertyDescriptor(b, key).get
    )
    expect(Object.getOwnPropertyDescriptor(a, key).set).toBe(
      Object.getOwnPropertyDescriptor(b, key).set
    )
  }
  const project = a.setProjectedPosition
  project('dormitory_1', 2)
  expect(a.currentRoom).toBe('dormitory_1')
  expect(a.currentIndex).toBe(2)
  expect(b.currentRoom).toBe('room_2_1')
  expect(b.currentIndex).toBe(1)
})

const timingBenchmark = process.env.MOWER_INCOME_TIMING_BENCHMARK === '1'
it.skipIf(!timingBenchmark)(
  'compares native and theoretical timing with the same supplied plan and horizon',
  () => {
    for (const mode of ['native', 'theoretical', 'theoretical', 'native']) {
      const request = incomeRequest(plan, {
        ...defaultIncomeSettings(),
        operatorMode: 'maximum',
        inventorySource: 'manual',
        finiteInventory: false,
        weightMode: 'custom',
        warmupDays: 0,
        sampleDays: 1,
        droneRoom: 'room_3_3'
      })
      request.options.simulationOptions.production.theoreticalMode = mode === 'theoretical'
      const start = performance.now()
      const result = runCalculationBridge(request.workspace, request.options)
      const milliseconds = performance.now() - start
      expect(result.success, result.error).toBe(true)
      const report = result.simulationReport
      expect(report.observedHours).toBeCloseTo(24, 8)
      expect(report.production.assumptions.timingModel).toBe(
        mode === 'theoretical' ? 'theoretical-events-v1' : 'native-io-v1'
      )
      if (process.env.MOWER_INCOME_BENCHMARK_LOG)
        appendFileSync(
          process.env.MOWER_INCOME_BENCHMARK_LOG,
          JSON.stringify({ mode, hours: 24, milliseconds, summary: result.report.summary }) + '\n'
        )
    }
  },
  180000
)
