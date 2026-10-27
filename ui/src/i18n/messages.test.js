import { describe, expect, it } from 'vitest'
import { baseCompile } from '@intlify/message-compiler'
import { createMowerI18n, SUPPORTED_LOCALES } from './index'

function leaves(value, prefix = '') {
  return Object.entries(value).flatMap(([key, entry]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof entry === 'string' ? [[path, entry]] : leaves(entry || {}, path)
  })
}

const parameters = (message) =>
  [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((match) => match[1]))].sort()

describe('bundled interface languages', () => {
  const instance = createMowerI18n()
  const source = new Map(leaves(instance.global.getLocaleMessage('zh-CN')))
  it.each(SUPPORTED_LOCALES)(
    '%s has every message, preserves parameters and compiles',
    (locale) => {
      const messages = new Map(leaves(instance.global.getLocaleMessage(locale)))
      expect([...messages.keys()].sort()).toEqual([...source.keys()].sort())
      for (const [key, message] of messages) {
        expect(parameters(message), `${locale}: ${key}`).toEqual(parameters(source.get(key)))
        const errors = []
        baseCompile(message, { onError: (error) => errors.push(error.message) })
        expect(errors, `${locale}: ${key}`).toEqual([])
      }
    }
  )
})
