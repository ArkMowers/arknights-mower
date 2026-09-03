export function getDroppedFile(event) {
  const files = event?.dataTransfer?.files
  if (!files?.length) return null
  if (typeof files.item === 'function') {
    return files.item(0)
  }
  return files[0] || null
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
