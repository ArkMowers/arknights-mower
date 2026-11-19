// The relay bootstrap supplies immutable URLs for the selected build.
export function publicAsset(path, localPath = path) {
  const files = globalThis.window?.__MOWER_PUBLIC_ASSETS__
  if (!files) return localPath
  const key = path.startsWith('/') ? path : '/' + path
  if (Object.hasOwn(files, key)) return files[key]
  try {
    return files[decodeURIComponent(key)] ?? localPath
  } catch {
    return localPath
  }
}
