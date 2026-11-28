import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useLazyForm } from './lazyForm'

describe('on-demand form', () => {
  it('releases a failed load and retries on the next open without remounting a loaded form', async () => {
    const scope = effectScope()
    const form = { name: 'Form' }
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ default: form })
    try {
      const dialog = scope.run(() => useLazyForm(load))
      expect(load).not.toHaveBeenCalled()
      await Promise.all([dialog.open(), dialog.open()])
      expect(load).toHaveBeenCalledOnce()
      expect(dialog.component.value).toBeNull()
      expect(dialog.show.value).toBe(false)
      expect(dialog.failed.value).toBe(true)

      await Promise.all([dialog.open(), dialog.open()])
      expect(load).toHaveBeenCalledTimes(2)
      expect(dialog.component.value).toBe(form)
      expect(dialog.show.value).toBe(true)
      expect(dialog.failed.value).toBe(false)

      dialog.show.value = false
      await dialog.open()
      expect(load).toHaveBeenCalledTimes(2)
      expect(dialog.component.value).toBe(form)
      expect(dialog.show.value).toBe(true)
    } finally {
      scope.stop()
    }
  })

  it.each([false, true])(
    'ignores a load that settles after disposal (failure=%s)',
    async (failed) => {
      const scope = effectScope()
      const { resolve, reject, promise } = Promise.withResolvers()
      const dialog = scope.run(() => useLazyForm(() => promise))
      const opening = dialog.open()
      scope.stop()

      if (failed) reject(new Error('offline'))
      else resolve({ default: { name: 'Form' } })
      await opening

      expect(dialog.component.value).toBeNull()
      expect(dialog.show.value).toBe(false)
      expect(dialog.failed.value).toBe(false)
    }
  )
})
