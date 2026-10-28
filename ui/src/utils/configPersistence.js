import { computed, nextTick } from 'vue'
import { i18n } from '@/i18n'

const pauseOwners = new WeakMap()

// Config flush also commits a debounced weekly-plan edit. Plan waiting only
// drains requests already queued; neither operation submits an unchanged draft.
export async function drainConfigurationSaves(config, plan, additionalPlans = []) {
  await nextTick()
  await config.flush_config_saves()
  await plan.wait_for_plan_save()
  for (const additional of additionalPlans) await additional.wait_for_plan_save()
  // Drain any configuration request queued while the plan save was completing.
  await nextTick()
  await config.flush_config_saves()
}

export function createSaveCoordinator(config, plan, additionalPlans = []) {
  // The recovery UI must survive a component unmount after a failed operation.
  // Visibility follows the stores; permission to resume remains operation-local.
  const stores = [...new Set([config, plan, ...additionalPlans])]
  const paused = computed(() => stores.some((store) => store.autosave_paused))
  let ownsPause = false

  function pause({ pendingOperation = false } = {}) {
    if (ownsPause) return
    if (!pendingOperation && paused.value) {
      throw new Error(i18n.global.t('settings.process.operationInProgress'))
    }
    for (const store of stores) {
      let owners = pauseOwners.get(store)
      if (!owners) pauseOwners.set(store, (owners = new Set()))
      owners.add(resume)
      store.autosave_paused = true
    }
    ownsPause = true
  }

  function resume() {
    // Only release the pause owned by this operation.
    if (!ownsPause) return
    for (const store of stores) {
      const owners = pauseOwners.get(store)
      owners.delete(resume)
      store.autosave_paused = owners.size > 0
    }
    ownsPause = false
  }

  async function pauseAndDrain() {
    await nextTick()
    pause()
    try {
      await drainConfigurationSaves(config, plan, additionalPlans)
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
    drain: () => drainConfigurationSaves(config, plan, additionalPlans)
  }
}
