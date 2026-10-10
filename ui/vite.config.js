import { fileURLToPath, URL } from 'node:url'
import process from 'node:process'
import { resolve } from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Inspect from 'vite-plugin-inspect'
import vueJsx from '@vitejs/plugin-vue-jsx'

import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

// unplugin-vue-components 用单引号拼接自动导入路径且不转义，检出目录含单引号时
// 生成的 import 语句会因引号提前闭合而无法解析。这里把组件路径换成 `@/` 别名，
// 输出与绝对路径构建一致，也避免依赖目录名。
const srcRoot = fileURLToPath(new URL('./src', import.meta.url)).replace(/\\/g, '/')

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  server: {
    port: Number(process.env.MOWER_DEV_PORT || 5173),
    strictPort: true
  },
  plugins: [
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
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        manager: resolve(import.meta.dirname, 'manager/index.html')
      }
    }
  }
}))
