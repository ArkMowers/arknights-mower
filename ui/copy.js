import fs from 'fs'
import path from 'path'

const sourceFile = 'Mower入门指北.html'
const destDir = 'dist/docs'

fs.mkdirSync(destDir, { recursive: true })
fs.copyFileSync(sourceFile, path.join(destDir, path.basename(sourceFile)))

console.log(`Copied ${sourceFile} to ${destDir}`)
