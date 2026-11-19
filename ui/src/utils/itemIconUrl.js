import { publicAsset } from '@/utils/publicAsset'

/** 图标地址：后端按 depot/ 前缀从资源包提供，缺失时页面走 fallback。 */
export function itemIconUrl(icon) {
  if (!icon) return ''
  return publicAsset(`/depot/${encodeURIComponent(icon)}.webp`)
}
