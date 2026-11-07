/**
 * 静态资源路径解析工具
 *
 * 兼容多部署平台：
 * 1. GitHub Pages (默认子路径形如 /R.I.I.C-Calculator/)
 * 2. Vercel / 自定义根域名 / 本地开发 / 桌面端 WebView2 (根路径 /)
 * 3. 外部静态资源 CDN (可通过环境变量 VITE_ASSET_BASE_URL 指向如 Vercel 线上地址)
 */

export function resolveAssetUrl(path: string): string {
  if (!path) return ''

  // 若已经是完整 URL（http/https/data:），直接返回
  if (/^(?:[a-z]+:)?\/\//i.test(path) || path.startsWith('data:')) {
    return path
  }

  // 去除开头的斜杠
  const cleanPath = path.startsWith('/') ? path.slice(1) : path

  // 1. 如果配置了外部静态资源基地址（如 Vercel 部署域名），优先使用
  const customAssetBase = import.meta.env?.VITE_ASSET_BASE_URL
  if (customAssetBase) {
    return `${customAssetBase.replace(/\/+$/, '')}/${cleanPath}`
  }

  // 2. 否则使用 Vite 注入的 BASE_URL（GitHub Pages 为 /R.I.I.C-Calculator/，Vercel/本地为 /）
  const base = import.meta.env?.BASE_URL || '/'
  const normalizedBase = base.endsWith('/') ? base : `${base}/`
  return `${normalizedBase}${cleanPath}`
}
