import { nextTick, ref } from 'vue'

// Config flush also commits a debounced weekly-plan edit. Plan waiting only
// drains requests already queued; neither operation submits an unchanged draft.
export async function drainConfigurationSaves(config, plan) {
  await nextTick()
  await config.flush_config_saves()
  await plan.wait_for_plan_save()
  // A completed plan save can reset dorm_order and queue a config save.
  await nextTick()
  await config.flush_config_saves()
}

export function createSaveCoordinator(config, plan) {
  const paused = ref(false)

  function pause({ pendingOperation = false } = {}) {
    if (paused.value) return
    if (!pendingOperation && (config.autosave_paused || plan.autosave_paused)) {
      throw new Error('配置导入或进程操作正在进行，请等待完成后再试')
    }
    config.autosave_paused = true
    plan.autosave_paused = true
    paused.value = true
  }

  function resume() {
    // Only release the pause owned by this operation.
    if (!paused.value) return
    config.autosave_paused = false
    plan.autosave_paused = false
    paused.value = false
  }

  async function pauseAndDrain() {
    await nextTick()
    pause()
    try {
      await drainConfigurationSaves(config, plan)
    } catch (error) {
      resume()
      throw error
    }
  }

  return {
    paused,
    pause,
    resume,
    pauseAndDrain,
    drain: () => drainConfigurationSaves(config, plan)
  }
}
