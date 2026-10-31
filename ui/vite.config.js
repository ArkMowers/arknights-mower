import { fileURLToPath, URL } from 'node:url'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import process from 'node:process'
import { resolve } from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Inspect from 'vite-plugin-inspect'
import vueJsx from '@vitejs/plugin-vue-jsx'

import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import { incrementalPublicAssets } from './scripts/publicAssets.js'
import { mockPreview } from './preview/vite-plugin.js'

// unplugin-vue-components 用单引号拼接自动导入路径且不转义，检出目录含单引号时
// 生成的 import 语句会因引号提前闭合而无法解析。这里把组件路径换成 `@/` 别名，
// 输出与绝对路径构建一致，也避免依赖目录名。
const srcRoot = fileURLToPath(new URL('./src', import.meta.url)).replace(/\\/g, '/')
const require = createRequire(import.meta.url)

function mowerChangelog() {
  const moduleId = 'virtual:mower-changelog'
  const resolvedModuleId = `\0${moduleId}`
  const changelogPath = fileURLToPath(new URL('../CHANGELOG.md', import.meta.url))
  return {
    name: 'mower-changelog',
    resolveId(id) {
      if (id === moduleId) return resolvedModuleId
    },
    async load(id) {
      if (id !== resolvedModuleId) return
      this.addWatchFile(changelogPath)
      return `export default ${JSON.stringify(await readFile(changelogPath, 'utf8'))}`
    }
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => ({
  define:
    mode === 'mock-preview'
      ? { 'import.meta.env.VITE_HTTP_URL': JSON.stringify('http://mower-preview.invalid') }
      : undefined,
  server: {
    port: Number(process.env.MOWER_DEV_PORT || 5173),
    strictPort: true,
    hmr: mode === 'mock-preview' ? false : undefined
  },
  plugins: [
    incrementalPublicAssets(),
    mowerChangelog(),
    mode === 'mock-preview' ? mockPreview() : null,
    Inspect(),
    vue(),
    vueJsx(),
    AutoImport({
      imports: [
        'vue',
        {
          'naive-ui': ['useDialog', 'useMessage', 'useNotification', 'useLoadingBar']
        }
      ]
    }),
    Components({
      dts: command === 'serve' ? 'components.d.ts' : false,
      resolvers: [NaiveUiResolver()],
      importPathTransform: (path) => {
        const normalized = path.replace(/\\/g, '/')
        return normalized.startsWith(srcRoot) ? `@${normalized.slice(srcRoot.length)}` : normalized
      }
    })
  ],
  resolve: {
    alias: [
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      // vuedraggable 4.1.0 的默认入口是 UMD；使用随包发布的 ESM 源码，减少兼容代码。
      // 升级该依赖时需重新核对源码入口及两处排序组件的拖动行为。
      {
        find: /^vuedraggable$/,
        replacement: require.resolve('vuedraggable/src/vuedraggable.js')
      }
    ]
  },
  build: {
    outDir: mode === 'mock-preview' ? 'dist-preview' : undefined,
    rollupOptions: {
      input:
        mode === 'mock-preview'
          ? { main: resolve(import.meta.dirname, 'preview/index.html') }
          : {
              main: resolve(import.meta.dirname, 'index.html'),
              manager: resolve(import.meta.dirname, 'manager/index.html')
            }
    }
  }
}))
