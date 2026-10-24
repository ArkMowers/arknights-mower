// PROTOTYPE 变体 D 的几何：∞ 形路线（伯努利双纽线）。左环是基建，右环是闲时出环，
// 两环在交汇点 O 相接。所有位置按弧长计算，站点在环上均匀分布。
export const W = 1200
export const H = 600
export const O = { x: 470, y: 300 }
const A = { left: 380, right: 600 }

function lem(t, a) {
  const sin = Math.sin(t)
  const cos = Math.cos(t)
  const d = 1 + sin * sin
  return [(a * cos) / d, (a * sin * cos) / d]
}

// 右环从 O 向右上出发，经最右端后从右下回到 O；左环从 O 向左上出发，从左下回到 O
export function sampleLobe(side, n = 720) {
  const t0 = side === 'left' ? Math.PI / 2 : -Math.PI / 2
  const pts = []
  const len = []
  let L = 0
  for (let i = 0; i <= n; i++) {
    const [x, y] = lem(t0 + (Math.PI * i) / n, A[side])
    const p = [O.x + x, O.y + y]
    if (i) L += Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
    pts.push(p)
    len.push(L)
  }
  return { side, pts, len, L }
}

export function center(side) {
  return [O.x + (side === 'left' ? -0.56 : 0.56) * A[side], O.y]
}

export function pointAt(lobe, s) {
  const { pts, len } = lobe
  const at = Math.max(0, Math.min(lobe.L, s))
  let lo = 0
  let hi = len.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (len[mid] < at) lo = mid
    else hi = mid
  }
  const f = (at - len[lo]) / (len[hi] - len[lo] || 1)
  return [pts[lo][0] + (pts[hi][0] - pts[lo][0]) * f, pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f]
}

// 朝环外侧的单位法线，用来摆站名
export function normalAt(lobe, s) {
  const a = pointAt(lobe, s - 3)
  const b = pointAt(lobe, s + 3)
  const p = pointAt(lobe, s)
  let nx = -(b[1] - a[1])
  let ny = b[0] - a[0]
  const d = Math.hypot(nx, ny) || 1
  nx /= d
  ny /= d
  const [cx, cy] = center(lobe.side)
  if (nx * (p[0] - cx) + ny * (p[1] - cy) < 0) {
    nx = -nx
    ny = -ny
  }
  return [nx, ny]
}

export function pathBetween(lobe, s0, s1) {
  const out = [pointAt(lobe, s0)]
  lobe.len.forEach((s, i) => {
    if (s > s0 && s < s1) out.push(lobe.pts[i])
  })
  out.push(pointAt(lobe, s1))
  return 'M ' + out.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ')
}

export function placeAlong(lobe, items, margin) {
  const span = lobe.L - 2 * margin
  return items.map((item, i) => {
    const s = margin + ((i + 0.5) * span) / Math.max(items.length, 1)
    return { item, s, p: pointAt(lobe, s), n: normalAt(lobe, s) }
  })
}
