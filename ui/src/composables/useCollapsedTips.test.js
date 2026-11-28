import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { useCollapsedTips } from './useCollapsedTips'

vi.stubGlobal('document', new EventTarget())

afterEach(() => {
  vi.restoreAllMocks()
})

function start(collapsed) {
  const scope = effectScope()
  const tips = scope.run(() => useCollapsedTips(collapsed))
  return { ...tips, stop: () => scope.stop() }
}

// Focus target; `keyboard` decides whether it matches :focus-visible.
function target(keyboard) {
  return { matches: (selector) => selector === ':focus-visible' && keyboard }
}

function pressEscape() {
  document.dispatchEvent(Object.assign(new Event('keydown'), { key: 'Escape' }))
}

describe('useCollapsedTips', () => {
  it('shows hover tooltips only while collapsed', async () => {
    const collapsed = ref(false)
    const tips = start(collapsed)
    tips.setTip('log', true)
    expect(tips.tipKey.value).toBeNull()
    collapsed.value = true
    await nextTick()
    tips.setTip('log', true)
    expect(tips.tipKey.value).toBe('log')
    tips.setTip('plan', false)
    expect(tips.tipKey.value).toBe('log')
    tips.setTip('log', false)
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('shows the tooltip on keyboard focus but not on pointer focus', () => {
    const tips = start(ref(true))
    tips.focusTip('log', target(false))
    expect(tips.tipKey.value).toBeNull()
    tips.blurTip('log')
    tips.focusTip('plan', target(true))
    expect(tips.tipKey.value).toBe('plan')
    tips.blurTip('plan')
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('restores the keyboard-focused row after collapse and hides it on expand', async () => {
    const collapsed = ref(false)
    const tips = start(collapsed)
    tips.focusTip('toggle', target(true))
    expect(tips.tipKey.value).toBeNull()
    collapsed.value = true
    await nextTick()
    expect(tips.tipKey.value).toBe('toggle')
    collapsed.value = false
    await nextTick()
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('restores nothing after collapse when focus came from the pointer', async () => {
    const collapsed = ref(false)
    const tips = start(collapsed)
    tips.focusTip('toggle', target(false))
    collapsed.value = true
    await nextTick()
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('forgets a row once it loses focus', async () => {
    const collapsed = ref(false)
    const tips = start(collapsed)
    tips.focusTip('log', target(true))
    tips.blurTip('log')
    collapsed.value = true
    await nextTick()
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('dismisses the tooltip on Escape from anywhere and then stops listening', async () => {
    const remove = vi.spyOn(document, 'removeEventListener')
    const tips = start(ref(true))
    tips.setTip('log', true)
    await nextTick()
    pressEscape()
    expect(tips.tipKey.value).toBeNull()
    await nextTick()
    expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function))
    tips.setTip('plan', true)
    await nextTick()
    expect(tips.tipKey.value).toBe('plan')
    pressEscape()
    expect(tips.tipKey.value).toBeNull()
    tips.stop()
  })

  it('removes the Escape listener when its scope stops', async () => {
    const add = vi.spyOn(document, 'addEventListener')
    const remove = vi.spyOn(document, 'removeEventListener')
    const tips = start(ref(true))
    tips.setTip('log', true)
    await nextTick()
    expect(add).toHaveBeenCalledTimes(1)
    const [, listener] = add.mock.calls[0]
    tips.stop()
    expect(remove).toHaveBeenCalledWith('keydown', listener)
  })
})
