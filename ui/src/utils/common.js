export { swap } from './swap'

import { match } from 'pinyin-pro'

export function pinyin_match(text, pinyin, options = {}) {
  const exact = match(text, pinyin, options)
  if (exact || (!/v/i.test(pinyin) && !options.v)) return exact
  const query = options.insensitive === false ? pinyin : pinyin.toLowerCase()
  return match(text, query, { v: true, ...options })
}
