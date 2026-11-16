export const receptionReferenceBonus = 21

export function receptionOccupancyBonus(rarity, phase) {
  return ({ 4: 2, 5: 4, 6: 5 }[rarity] || 0) + phase * 8
}

export function normalizedReceptionEfficiency(skillBonus, rarity, phase) {
  return skillBonus + receptionOccupancyBonus(rarity, phase) - receptionReferenceBonus
}
