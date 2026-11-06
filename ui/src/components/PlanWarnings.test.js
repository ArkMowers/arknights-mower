import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useMowerStore } from '@/stores/mower'
import PlanWarnings from './PlanWarnings.vue'

const warning = vi.hoisted(() => vi.fn())
vi.mock('naive-ui', () => ({ useMessage: () => ({ warning }) }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
let scope, store
afterEach(() => {
  scope?.stop()
  store?.$dispose()
  vi.clearAllMocks()
})
it('displays transient startup warnings until closed and clears the delivery buffer', async () => {
  setActivePinia(createPinia())
  store = useMowerStore()
  scope = effectScope()
  scope.run(() => PlanWarnings.setup({}, { expose: () => {} }))
  store.plan_warnings = ['训练位技能不足，可能会导致 Mower 无法正常运行']
  await nextTick()
  expect(warning).toHaveBeenCalledExactlyOnceWith('训练位技能不足，可能会导致 Mower 无法正常运行', {
    duration: 0,
    closable: true
  })
  expect(store.plan_warnings).toEqual([])
  expect(store.log_lines).toEqual([])
})
