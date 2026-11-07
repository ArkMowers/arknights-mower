import {
  MOWER_ROOM_IDS,
  type MowerFacility,
  type MowerRoomId,
  type RosterWorkspace,
} from '../domain/roster'

function createDefaultSlots(count: number) {
  return Array.from({ length: count }, () => ({
    occupant: { kind: 'empty' as const },
    groupId: null,
    replacements: [],
  }))
}

function createDefaultFacility(roomId: MowerRoomId): MowerFacility {
  if (roomId.startsWith('room_')) {
    // 243 default layout:
    // Row 1: room_1_1 (manufacture), room_1_2 (manufacture), room_1_3 (power)
    // Row 2: room_2_1 (manufacture), room_2_2 (manufacture), room_2_3 (power)
    // Row 3: room_3_1 (trading), room_3_2 (trading), room_3_3 (power)
    if (roomId === 'room_1_3' || roomId === 'room_2_3' || roomId === 'room_3_3') {
      return { roomId, type: 'power', level: 3, slots: createDefaultSlots(1) }
    }
    if (roomId === 'room_3_1' || roomId === 'room_3_2') {
      return { roomId, type: 'trading', level: 3, product: 'money', slots: createDefaultSlots(3) }
    }
    const product = roomId === 'room_2_1' || roomId === 'room_2_2' ? 'exp' : 'gold'
    return { roomId, type: 'manufacture', level: 3, product, slots: createDefaultSlots(3) }
  }
  if (roomId === 'central') {
    return { roomId, type: 'central', level: 5, slots: createDefaultSlots(5) }
  }
  if (roomId.startsWith('dormitory_')) {
    return { roomId, type: 'dormitory', level: 5, slots: createDefaultSlots(5) }
  }
  if (roomId === 'meeting') {
    return { roomId, type: 'meeting', level: 3, slots: createDefaultSlots(2) }
  }
  if (roomId === 'factory') {
    return { roomId, type: 'factory', level: 3, slots: createDefaultSlots(1) }
  }
  if (roomId === 'contact') {
    return { roomId, type: 'contact', level: 3, slots: createDefaultSlots(1) }
  }
  if (roomId === 'train') {
    return { roomId, type: 'train', level: 3, slots: createDefaultSlots(2) }
  }
  if (roomId === 'recycle') {
    return { roomId, type: 'recycle', level: 0, slots: [] }
  }
  return { roomId, type: 'gaming', level: 1, slots: createDefaultSlots(1) }
}

export function createDefaultWorkspace(): RosterWorkspace {
  const facilities = {} as Record<MowerRoomId, MowerFacility>
  for (const roomId of MOWER_ROOM_IDS) {
    facilities[roomId] = createDefaultFacility(roomId)
  }

  return {
    schemaVersion: 8,
    name: '默认排班',
    mainPlan: {
      id: 'plan1',
      name: '主力排班',
      facilities,
      conf: {
        ling_xi: 1,
        exhaust_require: [],
        rest_in_full: [],
        resting_priority: [],
        workaholic: [],
        refresh_trading: [],
        refresh_drained: [],
        ope_resting_priority: [],
      },
    },
    compatibility: {
      defaultPlanKey: 'plan1',
      backupPlans: [],
      otherPlans: {},
      unrecognizedFields: {},
    },
  }
}
