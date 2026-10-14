import type { ManufacturingFormulaId } from './manufacturingTimeline'

export interface MowerProductSwitchSettings {
  enable: boolean
  max_drones_per_switch: number
  grandet_mode: boolean
  use_drones_when_leaving_orirock: boolean
  direct_when_drones_insufficient: boolean
  drone_loss_seconds: number
  waiting_seconds: number
}
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
export function readMowerProductSwitchSettings(value: unknown): MowerProductSwitchSettings {
  const settings = record(value) ? value : {}
  const boolean = (key: string, fallback: boolean) => typeof settings[key] === 'boolean' ? settings[key] : fallback
  const integer = (key: string, fallback: number, max: number) => {
    const candidate = settings[key]
    if (candidate === undefined) return fallback
    if (typeof candidate !== 'number' || !Number.isInteger(candidate) || candidate < 0 || candidate > max) throw new Error(`Invalid product_switching.${key}`)
    return candidate
  }
  return { enable: boolean('enable', false), max_drones_per_switch: integer('max_drones_per_switch', 0, 200), grandet_mode: boolean('grandet_mode', true), use_drones_when_leaving_orirock: boolean('use_drones_when_leaving_orirock', true), direct_when_drones_insufficient: boolean('direct_when_drones_insufficient', false), drone_loss_seconds: integer('drone_loss_seconds', 30, 180), waiting_seconds: integer('waiting_seconds', 2, 60) }
}

export const MOWER_MANUFACTURING_FORMULAS: Readonly<Record<string, ManufacturingFormulaId | undefined>> = {
  gold: 'gold', exp3: 'exp-medium', orirock: 'fragment-orirock', orirock_device: 'fragment-device',
}
export function manufacturingProductId(formula: ManufacturingFormulaId): string {
  return { gold: 'gold', 'exp-medium': 'exp3', 'fragment-orirock': 'orirock', 'fragment-device': 'orirock_device' }[formula]
}

/** Alpha manufacture_product.drone_plan: whole drones, bounded final-drone loss.
 * Input is the current unit's remaining base seconds, before production speed.
 */
export function planMowerProductSwitchDrones(remainingSeconds: number, settings: MowerProductSwitchSettings, current: string, target: string): { drones: number; naturalOnly: boolean } {
  const naturalOnly = settings.grandet_mode && !settings.use_drones_when_leaving_orirock && current.startsWith('orirock') && !target.startsWith('orirock')
  if (naturalOnly || remainingSeconds <= 0) return { drones: 0, naturalOnly }
  const seconds = Math.max(0, remainingSeconds), remainder = seconds % 180
  let drones = Math.floor(seconds / 180)
  const loss = settings.grandet_mode ? settings.drone_loss_seconds : 180
  if (remainder > 1e-6 && 180 - remainder <= loss + 1e-6) drones++
  if (settings.max_drones_per_switch) drones = Math.min(drones, settings.max_drones_per_switch)
  return { drones, naturalOnly }
}
