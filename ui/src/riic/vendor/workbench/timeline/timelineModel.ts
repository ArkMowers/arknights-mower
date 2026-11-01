import { getOperatorName, getRoomDisplayName, getOperatorAvatarUrl } from '../operatorHelpers'
import type { ScheduleSimulationReport } from '../../simulator/scheduleSimulation'
import type { RuntimeEvent } from '../../scheduler/rosterRuntime'

export interface TimelineInterval {
  id: string
  start: number
  end: number
  duration: number
  operatorId: string
  operatorName: string
  avatarUrl: string
  roomId: string
  roomName: string
  roomType: string
  slotIndex: number
  slotKey: string
  isDormitory: boolean
  isVipBed?: boolean
  startMorale?: number
  endMorale?: number
  efficiencyPercent?: number
  status: 'working' | 'resting' | 'idle' | 'exhausted'
}

export interface SlotTrack {
  slotKey: string
  slotIndex: number
  role: 'work' | 'dorm-keeper' | 'free-rest' | 'fiammetta'
  intervals: TimelineInterval[]
}

export interface FacilityTrack {
  roomId: string
  roomName: string
  roomType: string
  level: number
  averageEfficiency: number
  slots: SlotTrack[]
}

export interface OperatorTrack {
  operatorId: string
  operatorName: string
  avatarUrl: string
  workHours: number
  restHours: number
  idleHours: number
  exhaustedHours: number
  workFraction: number
  intervals: TimelineInterval[]
}

export interface TimelineMarkerEvent {
  time: number
  type: string
  label: string
  description: string
  operatorIds: string[]
  icon: string
  color: string
}

export interface TimelineDataset {
  totalHours: number
  warmupHours: number
  observedHours: number
  facilityTracks: FacilityTrack[]
  operatorTracks: OperatorTrack[]
  events: TimelineMarkerEvent[]
}

function resolveRoomType(roomId: string, rawType?: string): string {
  if (rawType) return rawType
  if (roomId === 'central') return 'central'
  if (roomId.startsWith('dormitory_') || roomId.startsWith('dorm_')) return 'dormitory'
  if (roomId === 'meeting') return 'meeting'
  if (roomId === 'factory') return 'workshop'
  if (roomId === 'contact') return 'office'
  if (roomId === 'train') return 'training'
  if (roomId === 'recycle') return 'recycle'
  return 'manufacture'
}

/**
 * Builds a structured, merged timeline dataset from a simulation report.
 * Merges contiguous raw segments with identical occupancy into coherent intervals.
 */
export function buildTimelineData(report: ScheduleSimulationReport): TimelineDataset {
  const warmupHours = report.assumptions?.warmupHours ?? 0
  const observedHours = report.observedHours || (report.assumptions?.sampleHours ?? 24)
  const totalHours = observedHours

  const segments = report.segments ?? []
  const schedule = report.inputs?.schedule

  // 1. Gather all rooms and their slot configurations
  const roomTracksMap = new Map<string, FacilityTrack>()

  if (schedule?.rooms) {
    for (const room of schedule.rooms) {
      if (room.type === 'gaming' || !room.roomId) continue
      const rType = resolveRoomType(room.roomId, room.type)
      const roomStats = report.rooms?.find(r => r.roomId === room.roomId)

      const facilityTrack: FacilityTrack = {
        roomId: room.roomId,
        roomName: getRoomDisplayName(room.roomId, rType),
        roomType: rType,
        level: room.level || 1,
        averageEfficiency: roomStats?.averageEfficiencyPercent ?? 100,
        slots: room.slots.map(slot => ({
          slotKey: `${room.roomId}_${slot.slotIndex}`,
          slotIndex: slot.slotIndex,
          role: slot.role,
          intervals: [],
        })),
      }
      roomTracksMap.set(room.roomId, facilityTrack)
    }
  }

  // If schedule wasn't attached, derive rooms from report.rooms or segments
  if (roomTracksMap.size === 0 && report.rooms) {
    for (const r of report.rooms) {
      const rType = resolveRoomType(r.roomId, r.roomType)
      roomTracksMap.set(r.roomId, {
        roomId: r.roomId,
        roomName: getRoomDisplayName(r.roomId, rType),
        roomType: rType,
        level: 3,
        averageEfficiency: r.averageEfficiencyPercent,
        slots: [],
      })
    }
  }

  // 2. Map segments into slot intervals (Facility View)
  if (segments.length > 0) {
    // Process each facility track and its slots
    for (const facility of roomTracksMap.values()) {
      const isDorm = facility.roomType === 'dormitory'

      // If slots were not pre-populated, infer from segment keys
      if (facility.slots.length === 0) {
        const slotKeyPrefix = `${facility.roomId}_`
        const slotKeys = new Set<string>()
        for (const seg of segments) {
          const dict = isDorm ? { ...seg.occupants, ...seg.bedOccupants } : seg.occupants
          for (const k of Object.keys(dict)) {
            if (k.startsWith(slotKeyPrefix)) slotKeys.add(k)
          }
        }
        const sortedKeys = Array.from(slotKeys).sort()
        facility.slots = sortedKeys.map((k, idx) => ({
          slotKey: k,
          slotIndex: idx,
          role: isDorm ? 'free-rest' : 'work',
          intervals: [],
        }))
      }

      for (const slot of facility.slots) {
        let currentInterval: TimelineInterval | null = null

        for (const seg of segments) {
          // Normalize time relative to observation start
          const segStart = Math.max(0, seg.start - warmupHours)
          const segEnd = Math.max(0, seg.end - warmupHours)
          if (segEnd <= segStart) continue

          // Occupant in this slot
          const opId = (seg.occupants[slot.slotKey] || (isDorm ? seg.bedOccupants[slot.slotKey] : '')) || ''
          const opName = opId ? getOperatorName(opId) : ''
          const currentMorale = opId ? seg.morale?.[opId] : undefined
          const eff = seg.efficiencyPercent?.[facility.roomId]

          let status: TimelineInterval['status'] = 'idle'
          if (opId) {
            if (isDorm) {
              status = 'resting'
            } else if (currentMorale !== undefined && currentMorale <= 0) {
              status = 'exhausted'
            } else {
              status = 'working'
            }
          }

          if (
            currentInterval &&
            currentInterval.operatorId === opId &&
            currentInterval.status === status
          ) {
            // Extend existing interval
            currentInterval.end = segEnd
            currentInterval.duration = segEnd - currentInterval.start
            if (currentMorale !== undefined) {
              currentInterval.endMorale = currentMorale
            }
          } else {
            // Finish previous
            if (currentInterval) {
              slot.intervals.push(currentInterval)
            }
            // Start new interval
            currentInterval = {
              id: `${slot.slotKey}_${segStart}`,
              start: segStart,
              end: segEnd,
              duration: segEnd - segStart,
              operatorId: opId,
              operatorName: opName,
              avatarUrl: opId ? getOperatorAvatarUrl(opId) : '',
              roomId: facility.roomId,
              roomName: facility.roomName,
              roomType: facility.roomType,
              slotIndex: slot.slotIndex,
              slotKey: slot.slotKey,
              isDormitory: isDorm,
              startMorale: currentMorale,
              endMorale: currentMorale,
              efficiencyPercent: eff,
              status,
            }
          }
        }

        if (currentInterval) {
          slot.intervals.push(currentInterval)
        }
      }
    }
  }

  // 3. Build Operator View Tracks
  const operatorTracksMap = new Map<string, OperatorTrack>()

  // Register known operators from report
  if (report.operators) {
    for (const op of report.operators) {
      const charId = op.operatorId
      const name = op.operatorName || getOperatorName(charId)
      operatorTracksMap.set(charId, {
        operatorId: charId,
        operatorName: name,
        avatarUrl: getOperatorAvatarUrl(charId),
        workHours: op.workHours,
        restHours: op.restHours,
        idleHours: op.idleHours,
        exhaustedHours: op.exhaustedHours,
        workFraction: op.workFraction,
        intervals: [],
      })
    }
  }

  // Build continuous operator intervals across time
  if (segments.length > 0) {
    const allOperatorIds = new Set<string>()
    for (const opId of operatorTracksMap.keys()) allOperatorIds.add(opId)
    // Index physical locations once per segment instead of rescanning every
    // occupied slot for every operator. Shared slot details keep this compact.
    type Location = { slotKey: string; roomId: string; isDorm: boolean; roomType: string; roomName: string }
    const slotDetails = new Map<string, Location>()
    const segmentLocations = segments.map(seg => {
      const locations = new Map<string, Location>()
      for (const [occupants, isDorm] of [[seg.occupants, false], [seg.bedOccupants, true]] as const) {
        for (const [key, id] of Object.entries(occupants)) {
          if (!id) continue
          allOperatorIds.add(id)
          // Preserve the original first-match order, including work before beds.
          if (locations.has(id)) continue
          const cacheKey = `${isDorm}:${key}`
          let location = slotDetails.get(cacheKey)
          if (!location) {
            const roomId = key.replace(/_\d+$/, '')
            const roomType = resolveRoomType(roomId, roomTracksMap.get(roomId)?.roomType)
            location = { slotKey: key, roomId, isDorm, roomType, roomName: getRoomDisplayName(roomId, roomType) }
            slotDetails.set(cacheKey, location)
          }
          locations.set(id, location)
        }
      }
      return locations
    })

    for (const opId of allOperatorIds) {
      let track = operatorTracksMap.get(opId)
      if (!track) {
        track = {
          operatorId: opId,
          operatorName: getOperatorName(opId),
          avatarUrl: getOperatorAvatarUrl(opId),
          workHours: 0,
          restHours: 0,
          idleHours: 0,
          exhaustedHours: 0,
          workFraction: 0,
          intervals: [],
        }
        operatorTracksMap.set(opId, track)
      }

      let currentInterval: TimelineInterval | null = null

      for (const [segmentIndex, seg] of segments.entries()) {
        const segStart = Math.max(0, seg.start - warmupHours)
        const segEnd = Math.max(0, seg.end - warmupHours)
        if (segEnd <= segStart) continue

        // Determine where op is located in this segment
        const location = segmentLocations[segmentIndex]!.get(opId)
        const locatedRoomId = location?.roomId ?? ''
        const locatedSlotKey = location?.slotKey ?? ''
        const isDorm = location?.isDorm ?? false

        const currentMorale = seg.morale?.[opId]
        const rType = location?.roomType ?? ''
        const rName = location?.roomName ?? '闲置待机'

        let status: TimelineInterval['status'] = 'idle'
        if (locatedSlotKey) {
          if (isDorm || rType === 'dormitory') {
            status = 'resting'
          } else if (currentMorale !== undefined && currentMorale <= 0) {
            status = 'exhausted'
          } else {
            status = 'working'
          }
        }

        const eff = locatedRoomId ? seg.efficiencyPercent?.[locatedRoomId] : undefined

        if (
          currentInterval &&
          currentInterval.status === status &&
          currentInterval.roomId === locatedRoomId
        ) {
          currentInterval.end = segEnd
          currentInterval.duration = segEnd - currentInterval.start
          if (currentMorale !== undefined) {
            currentInterval.endMorale = currentMorale
          }
        } else {
          if (currentInterval) {
            track.intervals.push(currentInterval)
          }
          currentInterval = {
            id: `op_${opId}_${segStart}`,
            start: segStart,
            end: segEnd,
            duration: segEnd - segStart,
            operatorId: opId,
            operatorName: track.operatorName,
            avatarUrl: track.avatarUrl,
            roomId: locatedRoomId,
            roomName: rName,
            roomType: rType,
            slotIndex: 0,
            slotKey: locatedSlotKey,
            isDormitory: isDorm,
            startMorale: currentMorale,
            endMorale: currentMorale,
            efficiencyPercent: eff,
            status,
          }
        }
      }

      if (currentInterval) {
        track.intervals.push(currentInterval)
      }
    }
  }

  // 4. Format Discrete Marker Events
  const events: TimelineMarkerEvent[] = []
  const rawEvents = (report.events ?? []) as RuntimeEvent[]

  for (const e of rawEvents) {
    const timeRel = Math.max(0, e.time - warmupHours)
    if (timeRel < 0 || timeRel > totalHours) continue

    const opNames = (e.operators || []).map((id: string) => getOperatorName(id))

    if (e.type === 'fiammetta') {
      events.push({
        time: timeRel,
        type: 'fiammetta',
        label: '菲亚梅塔心情互换',
        description: `菲亚梅塔将自身充沛心情转移至 ${opNames.join('、') || '指定干员'}`,
        operatorIds: e.operators || [],
        icon: '🕊️',
        color: '#f59e0b',
      })
    } else if (e.type === 'backup-plan') {
      events.push({
        time: timeRel,
        type: 'backup-plan',
        label: `副表${e.active ? '启用' : '退出'}: ${e.backupName || ''}`,
        description: `副表【${e.backupName || ''}】在 ${e.timing || ''} 阶段切换为${e.active ? '激活' : '停用'}`,
        operatorIds: e.operators || [],
        icon: '🔄',
        color: '#8b5cf6',
      })
    } else if (e.type === 'backup-task') {
      events.push({
        time: timeRel,
        type: 'backup-task',
        label: `副表任务: ${e.backupName || ''}`,
        description: `副表【${e.backupName || ''}】在 ${e.timing || ''} 阶段执行任务：${opNames.join('、') || '指定干员'}`,
        operatorIds: e.operators || [],
        icon: '⚡',
        color: '#a855f7',
      })
    } else if (e.type === 'shift-on') {
      events.push({
        time: timeRel,
        type: 'shift-on',
        label: '进驻上岗',
        description: `${opNames.join('、')} 进驻设施`,
        operatorIds: e.operators || [],
        icon: '🟢',
        color: '#10b981',
      })
    } else if (e.type === 'shift-off') {
      events.push({
        time: timeRel,
        type: 'shift-off',
        label: '下班休息',
        description: `${opNames.join('、')} 心情耗尽/换班下岗`,
        operatorIds: e.operators || [],
        icon: '🟡',
        color: '#f59e0b',
      })
    }
  }

  // Sort tracks deterministically
  const facilityOrder = ['manufacture', 'trading', 'power', 'central', 'dormitory', 'meeting', 'office', 'training', 'workshop', 'recycle']
  const sortedFacilities = Array.from(roomTracksMap.values()).sort((a, b) => {
    const ai = facilityOrder.indexOf(a.roomType)
    const bi = facilityOrder.indexOf(b.roomType)
    if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
    return a.roomId.localeCompare(b.roomId)
  })

  const sortedOperators = Array.from(operatorTracksMap.values()).sort((a, b) => {
    // Sort by work fraction descending
    if (b.workFraction !== a.workFraction) return b.workFraction - a.workFraction
    return a.operatorName.localeCompare(b.operatorName, 'zh-CN')
  })

  return {
    totalHours,
    warmupHours,
    observedHours,
    facilityTracks: sortedFacilities,
    operatorTracks: sortedOperators,
    events,
  }
}
