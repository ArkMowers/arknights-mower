// Stable, saturated stroke colours paired with light translucent legend badges.
// Badge text uses the active theme's main text colour, not white on unknown fills.
const PALETTE = [
  '#287FC0',
  '#DC5075',
  '#CB8423',
  '#329376',
  '#8556C0',
  '#C45A36',
  '#417BB9',
  '#BC648F',
  '#679144',
  '#7369CC',
  '#BD7042',
  '#398DAB',
  '#A95761',
  '#658944',
  '#7D6FBA',
  '#B67D20'
]

export function moodStroke(index) {
  return PALETTE[((index % PALETTE.length) + PALETTE.length) % PALETTE.length]
}

export function moodBadgeBackground(hex) {
  const value = /^#[a-fA-F0-9]{6}$/.test(hex) ? hex : '#287FC0'
  const parts = [1, 3, 5].map((start) => parseInt(value.slice(start, start + 2), 16))
  return `rgba(${parts.join(', ')}, 0.14)`
}
