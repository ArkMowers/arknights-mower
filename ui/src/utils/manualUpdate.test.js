import { describe, expect, it } from 'vitest'

import { getDroppedFile, postManualUpdate } from './manualUpdate.js'

describe('manual update helpers', () => {
  it('reads the first file from a standard drop event', () => {
    const file = { name: 'resource.zip' }
    expect(getDroppedFile({ dataTransfer: { files: [file] } })).toBe(file)
    expect(getDroppedFile({ dataTransfer: { files: [] } })).toBeNull()
    expect(getDroppedFile(undefined)).toBeNull()
  })

  it('posts the selected file as update form data and reports progress', async () => {
    const file = new Blob(['resource'], { type: 'application/zip' })
    const progress = []
    const client = {
      async post(url, body, config) {
        expect(url).toBe('/hot-update/manual')
        expect(body.get('update')).toBeInstanceOf(Blob)
        config.onUploadProgress({ loaded: 1, total: 4 })
        return { data: { ok: true, kind: 'resource' } }
      }
    }

    await expect(
      postManualUpdate(client, '/hot-update/manual', file, (event) => progress.push(event))
    ).resolves.toEqual({ ok: true, kind: 'resource' })
    expect(progress).toEqual([{ percent: 25 }])
  })
})
