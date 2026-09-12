import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import GlobalUpdateDrop from './GlobalUpdateDrop.vue'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import { zipPackage } from '../../test/updatePackage.js'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  client: { post: vi.fn() },
  push: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  resources: { installing: false, loadResourceVersionLocal: vi.fn() }
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: state.push }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ error: state.error, warning: state.warning }) }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resources }))
vi.mock('@/stores/config', () => ({
  useConfigStore: () => ({ load_item: vi.fn(), load_shop: vi.fn() })
}))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => ({ load_operators: vi.fn() }) }))

class DropTarget {
  constructor(local = false) {
    this.local = local
  }
  closest() {
    return this.local
  }
}
function dropEvent(file, overrides = {}) {
  return {
    target: new DropTarget(),
    defaultPrevented: false,
    dataTransfer: { types: ['Files'], files: [file] },
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    ...overrides
  }
}

describe('global update drop routing', () => {
  let scope, component
  beforeEach(() => {
    vi.clearAllMocks()
    state.mounted = []
    state.unmounted = []
    state.resources.installing = false
    vi.stubGlobal('Element', DropTarget)
    vi.stubGlobal('window', { addEventListener: vi.fn(), removeEventListener: vi.fn() })
    vi.stubGlobal('document', { addEventListener: vi.fn(), removeEventListener: vi.fn() })
    scope = effectScope()
    component = scope.run(() => GlobalUpdateDrop.setup({}, { expose: () => {} }))
    state.mounted.forEach((callback) => callback())
  })
  afterEach(() => {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    pendingSoftwarePackage.value = null
    vi.unstubAllGlobals()
  })

  it('routes a renamed software package to settings without uploading or installing', async () => {
    const file = await zipPackage(['mower/_internal/arknights_mower/__init__.py'], 'resource.zip')
    await component.drop(dropEvent(file))
    expect(pendingSoftwarePackage.value).toBe(file)
    expect(state.push).toHaveBeenCalledWith('/mowersettings')
    expect(state.client.post).not.toHaveBeenCalled()
    expect(component.show.value).toBe(false)
  })

  it('opens resource confirmation based on contents and submits only after confirmation', async () => {
    const file = await zipPackage(['arknights_mower/data/version.json'], 'arknights-mower_4.9.zip')
    await component.drop(dropEvent(file))
    expect(component.show.value).toBe(true)
    expect(component.selected.value).toBe(file)
    expect(state.push).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
    state.client.post.mockResolvedValueOnce({ data: { ok: true, kind: 'resource' } })
    await component.installResource()
    expect(state.client.post).toHaveBeenCalledOnce()
    expect(state.client.post.mock.calls[0][0]).toBe('/hot-update/manual')
    expect(state.resources.loadResourceVersionLocal).toHaveBeenCalledOnce()
  })

  it('does not consume existing local drop handlers, editable targets or non-package drags', async () => {
    const file = new File(['irrelevant'], 'file.bin')
    for (const event of [
      dropEvent(file, { defaultPrevented: true }),
      dropEvent(file, { target: new DropTarget(true) }),
      dropEvent(new File(['image'], 'image.png', { type: 'image/png' })),
      dropEvent(new File(['{}'], 'data.json', { type: 'application/json' })),
      dropEvent(file, { dataTransfer: { types: ['text/plain'], files: [] } })
    ]) {
      component.enter(event)
      component.over(event)
      await component.drop(event)
      expect(event.preventDefault).not.toHaveBeenCalled()
      expect(event.stopPropagation).not.toHaveBeenCalled()
    }
    expect(state.error).not.toHaveBeenCalled()
    expect(state.push).not.toHaveBeenCalled()
    expect(component.show.value).toBe(false)
  })

  it('rejects unknown contents instead of falling back to the resource installer', async () => {
    await component.drop(dropEvent(await zipPackage(['unrelated.txt'], 'resource.zip')))
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('未识别'))
    expect(component.show.value).toBe(false)
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(component.reading.value).toBe(false)
  })

  it('blocks concurrent drops and ignores results after unmount', async () => {
    let resolveHeader
    const file = {
      size: 20,
      type: '',
      slice: () => ({
        arrayBuffer: () =>
          new Promise((resolve) => {
            resolveHeader = resolve
          })
      })
    }
    const first = component.drop(dropEvent(file))
    expect(component.reading.value).toBe(true)
    await component.drop(dropEvent(file))
    expect(state.warning).toHaveBeenCalledOnce()
    state.unmounted.forEach((callback) => callback())
    resolveHeader(new Uint8Array([31, 139]).buffer)
    await first
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(state.push).not.toHaveBeenCalled()
    expect(component.reading.value).toBe(false)
  })

  it('registers routing in bubble phase and removes every listener', () => {
    expect(window.addEventListener).toHaveBeenCalledWith('drop', component.drop)
    state.unmounted.forEach((callback) => callback())
    for (const args of window.addEventListener.mock.calls)
      expect(window.removeEventListener).toHaveBeenCalledWith(...args)
    for (const args of document.addEventListener.mock.calls)
      expect(document.removeEventListener).toHaveBeenCalledWith(...args)
  })
})
