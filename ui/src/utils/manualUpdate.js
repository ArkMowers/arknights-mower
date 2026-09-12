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

export function isUpdateFileDrag(event) {
  const transfer = event?.dataTransfer
  if (!Array.from(transfer?.types || []).includes('Files')) return false
  // Do not consume image/text uploads or internal sorting. Names are never used
  // for routing; the browser only exposes MIME types before a file is dropped.
  const files = transfer.files?.length
    ? Array.from(transfer.files)
    : Array.from(transfer.items || []).filter((item) => item.kind === 'file')
  return (
    files.length > 0 &&
    files.every(
      (file) =>
        !file.type ||
        [
          'application/zip',
          'application/x-zip-compressed',
          'application/gzip',
          'application/x-gzip',
          'application/x-tar',
          'application/x-apple-diskimage',
          'application/octet-stream'
        ].includes(file.type)
    )
  )
}

export async function updatePackageKind(file) {
  const header = new Uint8Array(await file.slice(0, 4).arrayBuffer())
  // Gzip and UDIF are software candidates; the server validates their actual
  // payload, version and integrity before asking for installation confirmation.
  if (header[0] === 0x1f && header[1] === 0x8b) return 'software'
  if (file.size >= 512) {
    const footer = new Uint8Array(await file.slice(-512, -508).arrayBuffer())
    if (footer[0] === 0x6b && footer[1] === 0x6f && footer[2] === 0x6c && footer[3] === 0x79)
      return 'software'
  }
  if (header[0] !== 0x50 || header[1] !== 0x4b) return null
  // Read the ZIP directory locally without decompressing/uploading the package.
  const { BlobReader, ZipReader } = await import('@zip.js/zip.js')
  const reader = new ZipReader(new BlobReader(file), { useWebWorkers: false })
  let software = false
  let resource = false
  let count = 0
  try {
    for await (const entry of reader.getEntriesGenerator()) {
      if (++count > 100000) throw new Error('更新包文件数量过多')
      if (entry.directory) continue
      const path = entry.filename
      software ||= ['maa-python.json', 'mower-android.json'].includes(path)
      software ||= /(^|\/)(_internal|Contents\/Resources)\/arknights_mower\/__init__\.py$/.test(
        path
      )
      resource ||= [
        'arknights_mower/data/version.json',
        'nav_steps.json',
        'stage_data.json'
      ].includes(path)
    }
  } catch {
    throw new Error('无法读取更新包目录，请选择完整的 Mower 安装包')
  } finally {
    await reader.close()
  }
  if (software && resource) throw new Error('包内同时包含软件和资源更新结构，请分别上传')
  return software ? 'software' : resource ? 'resource' : null
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
