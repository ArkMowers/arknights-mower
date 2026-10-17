import { describe, expect, it } from 'vitest'
import { buildTimelineData } from './timelineModel'
import type { ScheduleSimulationReport } from '../../simulator/scheduleSimulation'

describe('timelineModel', () => {
  it('handles empty report gracefully', () => {
    const report: ScheduleSimulationReport = {
      schemaVersion: 1,
      engine: 'mower-morale-v1',
      success: true,
      elapsedHours: 24,
      observedHours: 24,
      assumptions: {
        sampleHours: 24,
        warmupHours: 0,
        maxStepHours: 0.25,
        warmupModel: 'continuous',
        restingThreshold: 0.65,
        operationDurationHours: 0,
        dormAtmosphere: '',
        singleRecoveryTarget: '',
      },
      inputs: {
        schedule: {
          schemaVersion: 1,
          rooms: [
            {
              roomId: 'room_1_1',
              type: 'manufacture',
              level: 3,
              capacity: 3,
              slots: [
                {
                  roomId: 'room_1_1',
                  slotIndex: 0,
                  occupant: { kind: 'operator', operatorId: 'char_102_texas' },
                  primaryOperatorId: 'char_102_texas',
                  orderedCandidates: ['char_198_blackd'],
                  groupId: null,
                  role: 'work',
                },
              ],
            },
          ],
          operators: {},
          restPools: [],
          policies: {} as any,
          fiammettaPolicies: [],
          runOrderPolicies: [],
          diagnostics: [],
          assumptions: {} as any,
          sourceWorkspace: {} as any,
        } as any,
        options: {},
      },
      operators: [],
      rooms: [{ roomId: 'room_1_1', roomType: 'manufacture', averageEfficiencyPercent: 130, efficiencyPercentHours: 3120, occupiedHours: 24, teams: [] }],
      events: [],
      segments: [],
      diagnostics: [],
    }

    const data = buildTimelineData(report)
    expect(data.totalHours).toBe(24)
    expect(data.facilityTracks).toHaveLength(1)
    expect(data.facilityTracks[0]?.roomId).toBe('room_1_1')
    expect(data.facilityTracks[0]?.slots).toHaveLength(1)
    expect(data.facilityTracks[0]?.slots[0]?.intervals).toHaveLength(0)
  })

  it('merges contiguous raw segments with identical occupancy into coherent intervals', () => {
    const report: ScheduleSimulationReport = {
      schemaVersion: 1,
      engine: 'mower-morale-v1',
      success: true,
      elapsedHours: 24,
      observedHours: 24,
      assumptions: {
        sampleHours: 24,
        warmupHours: 0,
        maxStepHours: 0.25,
        warmupModel: 'continuous',
        restingThreshold: 0.65,
        operationDurationHours: 0,
        dormAtmosphere: '',
        singleRecoveryTarget: '',
      },
      inputs: {
        schedule: {
          schemaVersion: 1,
          rooms: [
            {
              roomId: 'room_1_1',
              type: 'manufacture',
              level: 3,
              capacity: 1,
              slots: [
                {
                  roomId: 'room_1_1',
                  slotIndex: 0,
                  occupant: { kind: 'operator', operatorId: 'char_102_texas' },
                  primaryOperatorId: 'char_102_texas',
                  orderedCandidates: ['char_198_blackd'],
                  groupId: null,
                  role: 'work',
                },
              ],
            },
            {
              roomId: 'dormitory_1',
              type: 'dormitory',
              level: 5,
              capacity: 1,
              slots: [
                {
                  roomId: 'dormitory_1',
                  slotIndex: 0,
                  occupant: { kind: 'free' },
                  primaryOperatorId: null,
                  orderedCandidates: [],
                  groupId: null,
                  role: 'free-rest',
                },
              ],
            },
          ],
          operators: {},
          restPools: [],
          policies: {} as any,
          fiammettaPolicies: [],
          runOrderPolicies: [],
          diagnostics: [],
          assumptions: {} as any,
          sourceWorkspace: {} as any,
        } as any,
        options: {},
      },
      operators: [
        { operatorId: 'char_102_texas', operatorName: '德克萨斯', mainWorkHours: 12, substituteWorkHours: 0, workHours: 12, exhaustedHours: 0, restHours: 12, idleHours: 0, workFraction: 0.5, workRestRatio: 1, initialMorale: 24, finalMorale: 24 },
        { operatorId: 'char_198_blackd', operatorName: '黑角', mainWorkHours: 0, substituteWorkHours: 12, workHours: 12, exhaustedHours: 0, restHours: 0, idleHours: 12, workFraction: 0.5, workRestRatio: null, initialMorale: 24, finalMorale: 12 },
      ],
      rooms: [
        { roomId: 'room_1_1', roomType: 'manufacture', averageEfficiencyPercent: 120, efficiencyPercentHours: 2880, occupiedHours: 24, teams: [] },
      ],
      events: [
        { time: 12, type: 'shift-off', operators: ['char_102_texas'] },
        { time: 12, type: 'shift-on', operators: ['char_198_blackd'] },
      ],
      segments: [
        // 0..6: Texas in room_1_1
        { start: 0, end: 6, occupants: { room_1_1_0: 'char_102_texas' }, bedOccupants: {}, morale: { char_102_texas: 18, char_198_blackd: 24 }, efficiencyPercent: { room_1_1: 120 } },
        // 6..12: Texas continues in room_1_1
        { start: 6, end: 12, occupants: { room_1_1_0: 'char_102_texas' }, bedOccupants: {}, morale: { char_102_texas: 12, char_198_blackd: 24 }, efficiencyPercent: { room_1_1: 120 } },
        // 12..24: Black Horn takes over room_1_1, Texas goes to dorm
        { start: 12, end: 18, occupants: { room_1_1_0: 'char_198_blackd' }, bedOccupants: { dormitory_1_0: 'char_102_texas' }, morale: { char_102_texas: 18, char_198_blackd: 18 }, efficiencyPercent: { room_1_1: 120 } },
        { start: 18, end: 24, occupants: { room_1_1_0: 'char_198_blackd' }, bedOccupants: { dormitory_1_0: 'char_102_texas' }, morale: { char_102_texas: 24, char_198_blackd: 12 }, efficiencyPercent: { room_1_1: 120 } },
      ],
      diagnostics: [],
    }

    const data = buildTimelineData(report)

    // Facility View checks:
    const roomTrack = data.facilityTracks.find(f => f.roomId === 'room_1_1')
    expect(roomTrack).toBeDefined()
    expect(roomTrack?.slots[0]?.intervals).toHaveLength(2)

    const firstInterval = roomTrack!.slots[0]!.intervals[0]!
    expect(firstInterval.operatorId).toBe('char_102_texas')
    expect(firstInterval.start).toBe(0)
    expect(firstInterval.end).toBe(12)
    expect(firstInterval.duration).toBe(12)
    expect(firstInterval.status).toBe('working')

    const secondInterval = roomTrack!.slots[0]!.intervals[1]!
    expect(secondInterval.operatorId).toBe('char_198_blackd')
    expect(secondInterval.start).toBe(12)
    expect(secondInterval.end).toBe(24)
    expect(secondInterval.duration).toBe(12)

    // Dorm track checks:
    const dormTrack = data.facilityTracks.find(f => f.roomId === 'dormitory_1')
    expect(dormTrack).toBeDefined()
    const dormSlot = dormTrack!.slots[0]!
    expect(dormSlot.intervals).toHaveLength(2) // 0-12 empty/idle, 12-24 Texas resting
    const restingInterval = dormSlot.intervals.find(i => i.operatorId === 'char_102_texas')
    expect(restingInterval).toBeDefined()
    expect(restingInterval?.status).toBe('resting')
    expect(restingInterval?.start).toBe(12)
    expect(restingInterval?.end).toBe(24)

    // Operator View checks:
    const texasTrack = data.operatorTracks.find(o => o.operatorId === 'char_102_texas')
    expect(texasTrack).toBeDefined()
    expect(texasTrack?.intervals).toHaveLength(2)
    expect(texasTrack?.intervals[0]?.status).toBe('working')
    expect(texasTrack?.intervals[0]?.start).toBe(0)
    expect(texasTrack?.intervals[0]?.end).toBe(12)
    expect(texasTrack?.intervals[1]?.status).toBe('resting')
    expect(texasTrack?.intervals[1]?.start).toBe(12)
    expect(texasTrack?.intervals[1]?.end).toBe(24)

    // Events check:
    expect(data.events).toHaveLength(2)
    expect(data.events.some(e => e.type === 'shift-off')).toBe(true)
    expect(data.events.some(e => e.type === 'shift-on')).toBe(true)

    const rapid = {
      ...report,
      segments: Array.from({ length: 4 }, (_, index) => ({
        start: index * .001,
        end: (index + 1) * .001,
        occupants: { room_1_1_0: index % 2 ? 'char_198_blackd' : 'char_102_texas' },
        bedOccupants: {},
        morale: { char_102_texas: 24, char_198_blackd: 24 },
        efficiencyPercent: { room_1_1: 120 },
      })),
    }
    const rapidSlot = buildTimelineData(rapid).facilityTracks.find(f => f.roomId === 'room_1_1')!.slots[0]!
    expect(rapidSlot.intervals).toHaveLength(4)
    expect(new Set(rapidSlot.intervals.map(interval => interval.id)).size).toBe(4)
  })

  it('correctly offsets intervals by warmupHours', () => {
    const report: ScheduleSimulationReport = {
      schemaVersion: 1,
      engine: 'mower-morale-v1',
      success: true,
      elapsedHours: 96,
      observedHours: 24,
      assumptions: {
        sampleHours: 24,
        warmupHours: 72,
        maxStepHours: 0.25,
        warmupModel: 'continuous',
        restingThreshold: 0.65,
        operationDurationHours: 0,
        dormAtmosphere: '',
        singleRecoveryTarget: '',
      },
      inputs: {
        schedule: {
          schemaVersion: 1,
          rooms: [
            {
              roomId: 'room_1_1',
              type: 'manufacture',
              level: 3,
              capacity: 1,
              slots: [
                {
                  roomId: 'room_1_1',
                  slotIndex: 0,
                  occupant: { kind: 'operator', operatorId: 'char_102_texas' },
                  primaryOperatorId: 'char_102_texas',
                  orderedCandidates: [],
                  groupId: null,
                  role: 'work',
                },
              ],
            },
          ],
          operators: {},
          restPools: [],
          policies: {} as any,
          fiammettaPolicies: [],
          runOrderPolicies: [],
          diagnostics: [],
          assumptions: {} as any,
          sourceWorkspace: {} as any,
        } as any,
        options: {},
      },
      operators: [],
      rooms: [],
      events: [{ time: 80, type: 'fiammetta', operators: ['char_102_texas'] }],
      segments: [
        { start: 72, end: 96, occupants: { room_1_1_0: 'char_102_texas' }, bedOccupants: {}, morale: { char_102_texas: 20 }, efficiencyPercent: { room_1_1: 150 } },
      ],
      diagnostics: [],
    }

    const data = buildTimelineData(report)
    expect(data.warmupHours).toBe(72)
    expect(data.observedHours).toBe(24)

    const interval = data.facilityTracks[0]?.slots[0]?.intervals[0]
    expect(interval?.start).toBe(0) // 72 - 72 = 0
    expect(interval?.end).toBe(24) // 96 - 72 = 24

    const fiammettaEvent = data.events[0]
    expect(fiammettaEvent?.time).toBe(8) // 80 - 72 = 8
    expect(fiammettaEvent?.type).toBe('fiammetta')
  })
})
