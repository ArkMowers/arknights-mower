import type { AppConfig, RoomType } from '../domain/types'

export interface RosterParticipant {
  operatorId: string
  roomId: string
  roomType: RoomType | 'control'
  role: 'primary' | 'backup'
  replacesOperatorId: string | null
}

interface RosterSlot {
  roomId: string
  roomType: RoomType | 'control'
  primaryOperatorId: string
  backupOperatorId: string | null
  currentOperatorId: string | null
  currentRole: 'primary' | 'backup' | null
}

export interface RosterTransition {
  operatorId: string
  roomId: string
  role: 'primary' | 'backup'
  replacementOperatorId: string | null
}

export interface ShiftRoster {
  participants: RosterParticipant[]
  primaryOperatorIds: Set<string>
  activeOperatorIds: () => Set<string>
  inactiveOperatorIds: () => Set<string>
  hasVacancies: () => boolean
  currentConfig: () => AppConfig
  depart: (
    operatorIds: Iterable<string>,
    canEnter?: (operatorId: string) => boolean,
  ) => RosterTransition[]
  fillVacancies: (canEnter: (operatorId: string) => boolean) => void
}

function primarySlots(config: AppConfig): RosterSlot[] {
  const slots: RosterSlot[] = []
  for (const operatorId of config.controlOperatorIds) {
    slots.push({
      roomId: '控制中枢',
      roomType: 'control',
      primaryOperatorId: operatorId,
      backupOperatorId: null,
      currentOperatorId: operatorId,
      currentRole: 'primary',
    })
  }
  for (const room of config.rooms) {
    for (const operatorId of room.operatorIds) {
      slots.push({
        roomId: room.id,
        roomType: room.type,
        primaryOperatorId: operatorId,
        backupOperatorId: null,
        currentOperatorId: operatorId,
        currentRole: 'primary',
      })
    }
  }
  return slots
}

/**
 * The scheduling seam for a one-step primary-to-backup handover.
 * Invalid or conflicting backups are ignored here and reported by layout validation.
 */
export function createShiftRoster(config: AppConfig): ShiftRoster {
  const slots = primarySlots(config)
  const primaryOperatorIds = new Set(slots.map((slot) => slot.primaryOperatorId))
  const claimedBackups = new Set<string>()

  for (const slot of slots) {
    const candidate = config.operatorBackups[slot.primaryOperatorId]
    if (!candidate || primaryOperatorIds.has(candidate) || claimedBackups.has(candidate)) continue
    slot.backupOperatorId = candidate
    claimedBackups.add(candidate)
  }

  const participants: RosterParticipant[] = slots.flatMap((slot) => {
    const primary: RosterParticipant = {
      operatorId: slot.primaryOperatorId,
      roomId: slot.roomId,
      roomType: slot.roomType,
      role: 'primary',
      replacesOperatorId: null,
    }
    if (!slot.backupOperatorId) return [primary]
    return [
      primary,
      {
        operatorId: slot.backupOperatorId,
        roomId: slot.roomId,
        roomType: slot.roomType,
        role: 'backup',
        replacesOperatorId: slot.primaryOperatorId,
      },
    ]
  })

  return {
    participants,
    primaryOperatorIds,
    activeOperatorIds: () => new Set(
      slots.map((slot) => slot.currentOperatorId).filter((id): id is string => Boolean(id)),
    ),
    inactiveOperatorIds: () => {
      const active = new Set(
        slots.map((slot) => slot.currentOperatorId).filter((id): id is string => Boolean(id)),
      )
      const rotatable = new Set(
        slots
          .filter((slot) => slot.backupOperatorId)
          .flatMap((slot) => [slot.primaryOperatorId, slot.backupOperatorId!]),
      )
      return new Set(
        participants
          .map((item) => item.operatorId)
          .filter((id) => rotatable.has(id) && !active.has(id)),
      )
    },
    hasVacancies: () => slots.some((slot) => !slot.currentOperatorId),
    currentConfig: () => ({
      ...config,
      controlOperatorIds: slots
        .filter((slot) => slot.roomType === 'control')
        .map((slot) => slot.currentOperatorId)
        .filter((id): id is string => Boolean(id)),
      rooms: config.rooms.map((room) => ({
        ...room,
        operatorIds: slots
          .filter((slot) => slot.roomId === room.id)
          .map((slot) => slot.currentOperatorId)
          .filter((id): id is string => Boolean(id)),
      })),
    }),
    depart(operatorIds, canEnter = () => true) {
      const leaving = new Set(operatorIds)
      const transitions: RosterTransition[] = []
      for (const slot of slots) {
        if (!slot.currentOperatorId || !leaving.has(slot.currentOperatorId) || !slot.currentRole) continue
        const role = slot.currentRole
        const operatorId = slot.currentOperatorId
        const candidate = role === 'primary' ? slot.backupOperatorId : slot.primaryOperatorId
        const replacementOperatorId = candidate && canEnter(candidate) ? candidate : null
        slot.currentOperatorId = replacementOperatorId
        slot.currentRole = replacementOperatorId
          ? replacementOperatorId === slot.primaryOperatorId ? 'primary' : 'backup'
          : null
        transitions.push({ operatorId, roomId: slot.roomId, role, replacementOperatorId })
      }
      return transitions
    },
    fillVacancies(canEnter) {
      for (const slot of slots) {
        if (slot.currentOperatorId || !slot.backupOperatorId) continue
        const candidate = [slot.primaryOperatorId, slot.backupOperatorId]
          .find((id): id is string => Boolean(id) && canEnter(id))
        if (!candidate) continue
        slot.currentOperatorId = candidate
        slot.currentRole = candidate === slot.primaryOperatorId ? 'primary' : 'backup'
      }
    },
  }
}
