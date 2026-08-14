import fs from 'fs'
import path from 'path'
import zlib from 'zlib'

const sourceFile = 'Mower入门指北.html'
const destDir = 'dist/docs'

fs.mkdirSync(destDir, { recursive: true })
fs.copyFileSync(sourceFile, path.join(destDir, path.basename(sourceFile)))

// 预压缩静态资源，server.py 会按 Accept-Encoding 返回 .gz
function precompress(dir) {
  let count = 0
  let totalBefore = 0
  let totalAfter = 0
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    if (fs.statSync(full).isDirectory()) {
      const r = precompress(full)
      count += r.count
      totalBefore += r.before
      totalAfter += r.after
      continue
    }
    if (!/\.(js|css|html|json|svg|map)$/.test(name)) continue
    const gz = full + '.gz'
    if (fs.existsSync(gz)) continue
    const before = fs.statSync(full).size
    const data = fs.readFileSync(full)
    const out = zlib.gzipSync(data, { level: 9 })
    fs.writeFileSync(gz, out)
    count++
    totalBefore += before
    totalAfter += out.length
  }
  return { count, before: totalBefore, after: totalAfter }
}

const r = precompress('dist')
console.log(
  `Precompressed ${r.count} files: ${(r.before / 1024).toFixed(0)}KB -> ${(r.after / 1024).toFixed(0)}KB`
)

console.log(`Copied ${sourceFile} to ${destDir}`)
