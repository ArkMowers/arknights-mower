export function getDroppedFile(event) {
  const files = event?.dataTransfer?.files
  if (!files?.length) return null
  if (typeof files.item === 'function') {
    return files.item(0)
  }
  return files[0] || null
}

export function droppedUpdateFile(event) {
  const files = event?.dataTransfer?.files
  if (files?.length !== 1) throw new Error('请一次拖入一个更新包')
  const file = getDroppedFile(event)
  if (!file.size) throw new Error('更新包为空，请选择完整文件')
  if (file.size > 2 * 1024 ** 3) throw new Error('更新包超过 2 GiB 限制')
  return file
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
