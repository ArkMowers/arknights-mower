export function getDroppedFile(event) {
  const files = event?.dataTransfer?.files
  if (!files?.length) return null
  if (typeof files.item === 'function') {
    return files.item(0)
  }
  return files[0] || null
}

export function updatePackageKind(file) {
  const name = file?.name?.toLowerCase() || ''
  if (name.endsWith('.dmg') || name.endsWith('.tar.gz')) return 'software'
  if (!name.endsWith('.zip')) return null
  return name.startsWith('arknights-mower_') || name === 'mower.zip' ? 'software' : 'resource'
}

export function droppedUpdateFile(event) {
  const files = event?.dataTransfer?.files
  if (files?.length !== 1) throw new Error('请一次拖入一个更新包')
  const file = getDroppedFile(event)
  if (!updatePackageKind(file)) throw new Error('请拖入 Mower 的 ZIP、tar.gz 或 DMG 更新包')
  if (!file.size) throw new Error('更新包为空，请选择完整文件')
  if (file.size > 2 * 1024 ** 3) throw new Error('更新包超过 2 GiB 限制')
  return file
}

export function isUpdateFileDrag(event) {
  const transfer = event?.dataTransfer
  if (!Array.from(transfer?.types || []).includes('Files')) return false
  if (transfer.files?.length) return Array.from(transfer.files).every(updatePackageKind)
  // Browsers hide filenames while hovering. Empty MIME is common for DMG/tar.gz;
  // the drop handler checks filenames before consuming the actual event.
  const items = Array.from(transfer.items || []).filter((item) => item.kind === 'file')
  return (
    items.length > 0 &&
    items.every(
      (item) =>
        !item.type ||
        [
          'application/zip',
          'application/x-zip-compressed',
          'application/gzip',
          'application/x-gzip',
          'application/x-tar',
          'application/x-apple-diskimage',
          'application/octet-stream'
        ].includes(item.type)
    )
  )
}

export async function postManualUpdate(client, url, file, onProgress = () => {}) {
  const formData = new FormData()
  formData.append('update', file)
  const response = await client.post(url, formData, {
    onUploadProgress(event) {
      if (!event.total) return
      onProgress({ percent: Math.min(100, Math.round((event.loaded / event.total) * 100)) })
    }
  })
  return response.data
}
