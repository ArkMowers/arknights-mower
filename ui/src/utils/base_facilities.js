export const facility_types = [
  { label: '贸易站', value: 'trade' },
  { label: '制造站', value: 'manufacture' },
  { label: '发电站', value: 'power' }
]

export const plan_facility_type_options = facility_types.map(({ label }) => ({
  label,
  value: label
}))

export const trigger_facility_type_options = facility_types

const fixed_facility_labels = {
  central: '控制中枢',
  meeting: '会客室',
  factory: '加工站',
  contact: '办公室',
  train: '训练室',
  recycle: '回收站'
}

export function formatFacilityLabel(roomId, plan = {}) {
  if (typeof roomId !== 'string') return roomId
  const output = /^room_([1-3])_([1-3])$/.exec(roomId)
  if (output) {
    const code = `B${output[1]}0${output[2]}`
    const name = plan?.[roomId]?.name
    return facility_types.some(({ label }) => label === name) ? `${name} ${code}` : code
  }
  if (Object.hasOwn(fixed_facility_labels, roomId)) return fixed_facility_labels[roomId]
  const dormitory = /^dormitory_([1-4])(_low)?$/.exec(roomId)
  if (dormitory) return `宿舍${dormitory[1]}${dormitory[2] ? '（低优先级）' : ''}`
  const gaming = /^gaming_([1-3])$/.exec(roomId)
  if (gaming) return `活动室${gaming[1]}`
  return roomId
}
