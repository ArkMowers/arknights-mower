import { fileURLToPath } from 'node:url'
import { defineConfig, globalIgnores, includeIgnoreFile } from 'eslint/config'
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default defineConfig(
  includeIgnoreFile(fileURLToPath(new URL('./.gitignore', import.meta.url))),
  globalIgnores(['**/.*']),
  {
    files: ['**/*.{vue,js,jsx,cjs,mjs}'],
    extends: [js.configs.recommended, vue.configs['flat/essential'], skipFormatting],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@vicons/*/*', '!@vicons/*/es'],
              message:
                'Import icons from @vicons/<pkg>/es/<Icon>: files outside es/ are CommonJS and the Vite 8 dev server renders them blank.'
            }
          ]
        }
      ]
    }
  },
  {
    files: [
      'src/**/*.{vue,js,jsx,cjs,mjs}',
      'manager/**/*.{vue,js,jsx,cjs,mjs}',
      'test/**/*.js',
      'preview/main.js',
      'preview/mock.js'
    ],
    languageOptions: { globals: globals.browser }
  },
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: { ts: tsParser } } },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'error'
    }
  },
  {
    files: [
      'copy.js',
      'vite.config.js',
      'eslint.config.js',
      'changelog-module.test.js',
      'preview/vite-plugin.js',
      'preview/*.test.js'
    ],
    languageOptions: { globals: globals.nodeBuiltin }
  }
)
