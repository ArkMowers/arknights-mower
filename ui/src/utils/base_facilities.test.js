import { describe, expect, it } from 'vitest'
import { formatFacilityLabel } from './base_facilities'

describe('facility labels', () => {
  it.each([
    ['room_1_1', 'B101'],
    ['room_1_2', 'B102'],
    ['room_1_3', 'B103'],
    ['room_2_1', 'B201'],
    ['room_2_2', 'B202'],
    ['room_2_3', 'B203'],
    ['room_3_1', 'B301'],
    ['room_3_2', 'B302'],
    ['room_3_3', 'B303']
  ])('formats %s without inventing its configured type', (room, expected) => {
    expect(formatFacilityLabel(room)).toBe(expected)
  })

  it.each([
    ['贸易站', '贸易站 B101'],
    ['制造站', '制造站 B101'],
    ['发电站', '发电站 B101']
  ])('uses the configured %s type', (name, expected) => {
    const plan = Object.freeze({ room_1_1: Object.freeze({ name }) })
    expect(formatFacilityLabel('room_1_1', plan)).toBe(expected)
  })

  it('reads changed facility types on each call without changing the plan', () => {
    const plan = { room_1_1: { name: '贸易站', plans: [{ agent: '阿米娅' }] } }
    expect(formatFacilityLabel('room_1_1', plan)).toBe('贸易站 B101')
    expect(plan).toEqual({ room_1_1: { name: '贸易站', plans: [{ agent: '阿米娅' }] } })
    plan.room_1_1.name = '制造站'
    expect(formatFacilityLabel('room_1_1', plan)).toBe('制造站 B101')
    expect(plan).toEqual({ room_1_1: { name: '制造站', plans: [{ agent: '阿米娅' }] } })
    const otherPlan = Object.freeze({ room_1_1: Object.freeze({ name: '发电站' }) })
    expect(formatFacilityLabel('room_1_1', otherPlan)).toBe('发电站 B101')
    expect(formatFacilityLabel('room_1_1', plan)).toBe('制造站 B101')
  })

  it.each([undefined, null, {}, { room_1_1: {} }, { room_1_1: { name: '未知设施' } }])(
    'keeps only the room code when its type is unavailable in %s',
    (plan) => {
      expect(formatFacilityLabel('room_1_1', plan)).toBe('B101')
    }
  )

  it.each([
    ['central', '控制中枢'],
    ['meeting', '会客室'],
    ['factory', '加工站'],
    ['contact', '办公室'],
    ['train', '训练室'],
    ['recycle', '回收站'],
    ['dormitory_1', '宿舍1'],
    ['dormitory_2', '宿舍2'],
    ['dormitory_3', '宿舍3'],
    ['dormitory_4', '宿舍4'],
    ['gaming_1', '活动室1'],
    ['gaming_2', '活动室2'],
    ['gaming_3', '活动室3']
  ])('formats %s without guessing a physical floor', (room, expected) => {
    expect(formatFacilityLabel(room)).toBe(expected)
  })

  it.each([
    ['dormitory_1_low', '宿舍1（低优先级）'],
    ['dormitory_2_low', '宿舍2（低优先级）'],
    ['dormitory_3_low', '宿舍3（低优先级）'],
    ['dormitory_4_low', '宿舍4（低优先级）']
  ])('recognizes the explicit low-priority suffix in %s', (room, expected) => {
    expect(formatFacilityLabel(room)).toBe(expected)
  })

  it.each([
    'room_0_1',
    'room_4_1',
    'room_1_4',
    'room_01_1',
    'room_1_1_extra',
    'dormitory_0',
    'dormitory_5',
    'dormitory_1_0',
    'dormitory_1_1',
    'dormitory_1_low_0',
    'dormitory_1_low_extra',
    'dorm_1',
    'gaming_0',
    'gaming_4',
    'gaming_1_low',
    'central_1',
    'unknown_room',
    'toString',
    '__proto__',
    ''
  ])('preserves unsupported room or suffix %s', (room) => {
    expect(formatFacilityLabel(room)).toBe(room)
  })
})
