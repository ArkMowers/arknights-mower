import { describe, expect, it } from 'vitest'

import {
  droppedUpdateFile,
  getDroppedFile,
  isUpdateFileDrag,
  postManualUpdate,
  updatePackageKind
} from './manualUpdate.js'

describe('manual update helpers', () => {
  it('routes software packages separately from resource zip files', () => {
    for (const name of [
      'arknights-mower_4.2.0_windows_x64.zip',
      'mower.zip',
      'mower.dmg',
      'mower.tar.gz'
    ]) {
      expect(updatePackageKind({ name })).toBe('software')
    }
    for (const name of ['resource.zip', 'hot_update.zip']) {
      expect(updatePackageKind({ name })).toBe('resource')
    }
    expect(updatePackageKind({ name: 'plan.json' })).toBeNull()
    expect(updatePackageKind({ name: 'screenshot.png' })).toBeNull()
  })

  it('leaves sorting, text, images and JSON drags to existing handlers', () => {
    expect(isUpdateFileDrag({ dataTransfer: { types: ['text/plain'] } })).toBe(false)
    for (const [name, type] of [
      ['plan.json', 'application/json'],
      ['image.png', 'image/png']
    ]) {
      expect(
        isUpdateFileDrag({
          dataTransfer: { types: ['Files'], files: [{ name }], items: [{ kind: 'file', type }] }
        })
      ).toBe(false)
      expect(
        isUpdateFileDrag({
          dataTransfer: { types: ['Files'], files: [], items: [{ kind: 'file', type }] }
        })
      ).toBe(false)
    }
    expect(
      isUpdateFileDrag({ dataTransfer: { types: ['Files'], files: [{ name: 'resource.zip' }] } })
    ).toBe(true)
  })

  it('rejects multi-file, empty or oversized update drops', () => {
    const file = { name: 'resource.zip', size: 100 }
    expect(droppedUpdateFile({ dataTransfer: { files: [file] } })).toBe(file)
    expect(() => droppedUpdateFile({ dataTransfer: { files: [file, file] } })).toThrow('一次')
    expect(() => droppedUpdateFile({ dataTransfer: { files: [{ ...file, size: 0 }] } })).toThrow(
      '为空'
    )
    expect(() =>
      droppedUpdateFile({ dataTransfer: { files: [{ ...file, size: 3 * 1024 ** 3 }] } })
    ).toThrow('2 GiB')
  })

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
