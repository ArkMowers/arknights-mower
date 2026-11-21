export const MOWER_DEFAULT_DORM_ORDER = ['dormitory_1', 'dormitory_2', 'dormitory_3', 'dormitory_4']

/** Alpha retains explicit low beds and migrates legacy numbered bed keys. */
export function effectiveMowerDormOrder(values: readonly string[]): string[] {
  const order: string[] = []
  for (const value of values) {
    const room = /^dormitory_[1-4]_\d+$/.test(value) ? value.replace(/_\d+$/, '') : value
    if (/^dormitory_[1-4](?:_low)?$/.test(room) && !order.includes(room)) order.push(room)
  }
  return [...order, ...MOWER_DEFAULT_DORM_ORDER.filter(room => !order.includes(room))]
}
