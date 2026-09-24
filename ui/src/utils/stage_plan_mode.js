// A three-state view of the existing two-field backend config. No new persisted keys.
export const STAGE_PLAN_MODES = Object.freeze({
  OFF: 'off',
  MAA: 'maa',
  MOWER: 'mower'
})

function normalizeRunner(runner) {
  return runner === STAGE_PLAN_MODES.MOWER ? STAGE_PLAN_MODES.MOWER : STAGE_PLAN_MODES.MAA
}

export function getStagePlanMode(enabled, runner) {
  return enabled ? normalizeRunner(runner) : STAGE_PLAN_MODES.OFF
}

export function selectStagePlanMode(mode, previousRunner = STAGE_PLAN_MODES.MAA) {
  const runner = normalizeRunner(previousRunner)
  if (mode === STAGE_PLAN_MODES.OFF) {
    // Preserve the last selected executor while paused; the scheduler uses enabled=false.
    return { stage_plan_enable: false, stage_plan_runner: runner }
  }
  if (mode === STAGE_PLAN_MODES.MAA || mode === STAGE_PLAN_MODES.MOWER) {
    return { stage_plan_enable: true, stage_plan_runner: mode }
  }
  throw new RangeError('Unknown stage plan execution mode')
}
