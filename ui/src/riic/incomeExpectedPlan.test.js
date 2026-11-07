import { appendFileSync } from 'node:fs'
import process from 'node:process'
import { expect, it } from 'vitest'
import plan from './fixtures/income-21trade-3proviso.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'

const longRun = process.env.MOWER_INCOME_LONG_TEST === '1'
const warmupDays = longRun ? 3 : 0
const sampleDays = longRun ? 28 : 1

// Complete Scheduling Plan decoded from the supplied income JPG, including its eight backups.
it.each([true, false])(
  'calculates the supplied plan with expectation mode %s',
  (expectationMode) => {
    const original = structuredClone(plan)
    let lastProgress = -1
    const result = calculateIncome(
      plan,
      {
        ...defaultIncomeSettings(),
        expectationMode,
        warmupDays,
        sampleDays,
        ...(expectationMode ? {} : { seed: 42 }),
        operatorMode: 'maximum',
        inventorySource: 'manual',
        finiteInventory: false,
        weightMode: 'custom',
        droneRoom: 'room_3_3'
      },
      (progress) => {
        const percent = Math.floor(progress.fraction * 100)
        if (process.env.MOWER_INCOME_TEST_LOG && percent > lastProgress) {
          lastProgress = percent
          appendFileSync(
            process.env.MOWER_INCOME_TEST_LOG,
            JSON.stringify({
              expectationMode,
              percent,
              label: progress.label,
              activity: progress.activity?.status
            }) + '\n'
          )
        }
      }
    )
    if (result.success && process.env.MOWER_INCOME_TEST_LOG)
      appendFileSync(
        process.env.MOWER_INCOME_TEST_LOG,
        JSON.stringify({
          result: {
            expectationMode,
            warmupDays,
            sampleDays,
            score: result.summary.totalScore82,
            exp: result.summary.exp,
            goldEquivalent: result.summary.goldValue + result.summary.virtualGoldValue,
            orderLmd: result.summary.orderLmd,
            orders: result.orderDistribution,
            drones: result.stability?.drones,
            maxWorkFractionDifference: result.stability.maxWorkFractionDifference,
            expectedProduction: result.simulationReport.production.expected
          }
        }) + '\n'
      )
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(sampleDays * 24, 6)
    expect(result.simulationReport.elapsedHours).toBeCloseTo((warmupDays + sampleDays) * 24, 6)
    expect(result.simulationReport.production.assumptions.expectationMode).toBe(expectationMode)
    expect(result.summary.totalScore82).toBeGreaterThan(0)
    if (!warmupDays)
      expect(
        result.eventLog.entries.some(
          (event) => event.type === '副表切换' && event.detail === '无训练计划（启用）'
        )
      ).toBe(true)
    expect(
      result.timelineData.operatorTracks.some((track) =>
        track.intervals.some((interval) => interval.roomId === 'train')
      )
    ).toBe(true)
    const sampled = result.simulationReport.production.events.filter(
      (event) => event.type === 'order-completed' && event.time > warmupDays * 24
    )
    const upper = sampled.filter((event) => event.roomId === 'room_1_1')
    const lower = sampled.filter((event) => event.roomId === 'room_3_1')
    expect(upper.length).toBeGreaterThan(0)
    expect(lower.length).toBeGreaterThan(0)
    if (expectationMode) {
      expect(result.simulationReport.production.assumptions).not.toHaveProperty('seed')
      expect(result.orderDistribution.expected).toBe(true)
      for (const { order } of upper) {
        expect(order.baseMinutes).toBeCloseTo(170.4, 9)
        expect(order.goldCost).toBeCloseTo(4.4, 9)
        expect(order.lmdReward).toBeCloseTo(2200, 9)
      }
      for (const { order } of lower) {
        expect(order.baseMinutes).toBe(144)
        expect(order.goldCost).toBe(4)
        expect(order.lmdReward).toBe(2000)
      }
      expect(Math.abs(result.orderDistribution.rows[1].count - upper.length * 0.4)).toBeLessThan(
        0.41
      )
      expect(result.summary.exp * (result.observedHours / 24)).toBeCloseTo(
        result.simulationReport.production.expected.output.exp,
        6
      )
      expect(result.simulationReport.production.expected.droneGenerated).toBeGreaterThan(0)
      expect(result.stability.drones).toBeUndefined()
      expect(result.orderDistribution.rows[2].count).toBe(0)
    } else {
      expect(result.simulationReport.production.assumptions.seed).toBe(42)
      expect(sampled.every((event) => !event.order.expectationComponents)).toBe(true)
    }
    if (!expectationMode) {
      const drones = result.stability.drones
      expect(drones.consumed).toBeGreaterThan(0)
      expect(drones.closing).toBeCloseTo(
        drones.opening + drones.generated - drones.overflow - drones.consumed,
        6
      )
      expect(drones.consumed).toBeCloseTo(result.resources.outflows.drone, 6)
    }
    expect(result.stability.roomComparisons.length).toBeGreaterThan(0)
    expect(plan).toEqual(original)
  },
  longRun ? 1200000 : 60000
)
