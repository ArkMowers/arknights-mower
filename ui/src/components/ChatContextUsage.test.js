import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import ChatContextUsage from './ChatContextUsage.vue'

const state = vi.hoisted(() => ({ config: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(usage = null) {
  state.config = reactive({
    ai_type: 'custom-online',
    ai_context_tokens: 256000,
    ai_deepseek_context_tokens: 1000000
  })
  const props = reactive({ usage, busy: false })
  const scope = effectScope()
  const component = scope.run(() => ChatContextUsage.setup(props, { expose: vi.fn() }))
  return { props, component, scope }
}

describe('context usage indicator', () => {
  it('labels 214k of 475k as 45% with 55% remaining and distinguishes estimates', () => {
    const { props, component, scope } = setup({
      used_tokens: 214000,
      max_tokens: 475000,
      estimated: true,
      compactions: 0
    })
    expect(component.usedPercent.value).toBe(45)
    expect(component.remainingPercent.value).toBe(55)
    expect(component.label.value).toContain('估算已用 214,000 token，共 475,000 token')
    expect(component.formatTokens(214000)).toBe('214k')
    props.usage = { used_tokens: 10000, max_tokens: 1000000, estimated: false, compactions: 1 }
    expect(component.usedPercent.value).toBe(1)
    expect(component.label.value).not.toContain('估算')
    expect(component.formatTokens(1000000)).toBe('1M')
    scope.stop()
  })
  it('shows the selected capacity before a request without inventing usage', () => {
    const { component, scope } = setup()
    expect(component.capacity.value).toBe(256000)
    expect(component.usedPercent.value).toBeNull()
    expect(component.label.value).toContain('发送后显示用量')
    state.config.ai_type = 'deepseek'
    expect(component.capacity.value).toBe(1000000)
    scope.stop()
  })
  it('clamps the ring and remaining value when a provider reports over capacity', () => {
    const { props, component, scope } = setup({
      used_tokens: 1200000,
      max_tokens: 1000000,
      compacting: true
    })
    props.busy = true
    expect(component.usedPercent.value).toBe(120)
    expect(component.remainingPercent.value).toBe(0)
    expect(component.ringOffset.value).toBe(0)
    expect(component.compacting.value).toBe(true)
    props.busy = false
    expect(component.compacting.value).toBe(false)
    props.usage = { used_tokens: -1, max_tokens: 1000000 }
    expect(component.usedPercent.value).toBeNull()
    scope.stop()
  })
})
