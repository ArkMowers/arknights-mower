import { zipPackage } from '../../test/updatePackage.js'
import { describe, expect, it } from 'vitest'

import {
  droppedUpdateFile,
  getDroppedFile,
  postManualUpdate,
  isUpdateFileDrag,
  updatePackageKind
} from './manualUpdate.js'

describe('manual update helpers', () => {
  it('rejects multi-file, empty or oversized update drops', () => {
    const file = { name: '任意改名 (1).bin', size: 100 }
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

describe('content-based update routing', () => {
  it.each([
    [['mower-android.json', 'mower/arknights_mower/data/version.json'], 'android.zip', 'software'],
    [['maa-python.json', 'maa.py'], 'adapter.zip', 'software'],
    [['mower/_internal/arknights_mower/__init__.py'], 'resources.zip', 'software'],
    [['Mower.app/Contents/Resources/arknights_mower/__init__.py'], 'renamed.zip (1)', 'software'],
    [['arknights_mower/data/version.json'], 'arknights-mower_4.9.9.zip', 'resource'],
    [['nav_steps.json', 'version.json'], 'offline.bin', 'resource'],
    [['stage_data.json'], 'offline (1).zip', 'resource'],
    [['version.json'], 'arknights-mower_4.9.9.zip', null],
    [['README.md'], 'resource.zip', null],
    [['nested/arknights_mower/data/version.json'], 'resource.zip', null]
  ])('routes %j without using name %s', async (paths, name, kind) => {
    await expect(updatePackageKind(await zipPackage(paths, name))).resolves.toBe(kind)
  })

  it('rejects ambiguous archives instead of choosing an installer', async () => {
    const file = await zipPackage([
      'mower/_internal/arknights_mower/__init__.py',
      'arknights_mower/data/version.json'
    ])
    await expect(updatePackageKind(file)).rejects.toThrow('同时包含')
  })

  it('reports damaged ZIPs and ignores non-package contents', async () => {
    await expect(updatePackageKind(new File(['PKbroken'], 'resource.zip'))).rejects.toThrow(
      '无法读取'
    )
    await expect(updatePackageKind(new File(['unrelated'], 'mower.zip'))).resolves.toBeNull()
    await expect(updatePackageKind(new File([], 'mower.zip'))).resolves.toBeNull()
  })

  it('uses gzip magic and the DMG footer regardless of their names', async () => {
    await expect(
      updatePackageKind(new File([new Uint8Array([31, 139, 8, 0])], 'renamed'))
    ).resolves.toBe('software')
    const bytes = new Uint8Array(1024)
    bytes.set(new TextEncoder().encode('koly'), 512)
    await expect(updatePackageKind(new File([bytes], 'renamed (1).bin'))).resolves.toBe('software')
    bytes[512] = 0
    await expect(updatePackageKind(new File([bytes], 'fake.dmg'))).resolves.toBeNull()
  })

  it.each(['image/png', 'application/json', 'text/plain'])('leaves %s drags untouched', (type) => {
    expect(isUpdateFileDrag({ dataTransfer: { types: ['Files'], files: [{ type }] } })).toBe(false)
  })

  it('ignores internal sorting and accepts archive MIME or unknown MIME during hover', () => {
    expect(isUpdateFileDrag({ dataTransfer: { types: ['text/plain'] } })).toBe(false)
    for (const type of ['', 'application/octet-stream', 'application/zip']) {
      expect(
        isUpdateFileDrag({
          dataTransfer: {
            types: ['Files'],
            files: [],
            items: [{ kind: 'file', type }]
          }
        })
      ).toBe(true)
      expect(
        isUpdateFileDrag({
          dataTransfer: {
            types: ['Files'],
            files: [{ name: 'renamed (1).bin', type }]
          }
        })
      ).toBe(true)
    }
  })
})
