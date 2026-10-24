/** Shared by the income simulator and the embedded runtime evaluator. */
export const MORALE_SKILL_THRESHOLDS = [4, 8, 12, 16, 18, 20] as const
export const MORALE_RATE_EPSILON = 1e-8

export function retainedRecoveryTarget(
  candidates: readonly string[],
  previous: {room: string; target: string; providerPosition: string; targetPosition: string} | undefined,
  room: string,
  provider: string,
  position: (id: string) => string,
  mood: (id: string) => number,
) {
  if (previous?.room === room && candidates.includes(previous.target)
    && previous.providerPosition === position(provider)
    && previous.targetPosition === position(previous.target)) return previous.target
  return [...candidates].sort((a, b) => mood(a) - mood(b))[0]
}
