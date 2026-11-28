// 曲率连续圆角的半径：支持 corner-shape 的内核把半径放大（倍数见 mower.css 的
// --mower-corner-scale），其他内核保持原值。形状由 mower.css 的全局规则统一切换。
export function corner(px) {
  return `calc(${px}px * var(--mower-corner-scale, 1))`
}
