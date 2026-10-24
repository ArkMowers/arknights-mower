export { swap } from './swap'

import { match } from 'pinyin-pro'

export function pinyin_match(text, pinyin) {
  pinyin = pinyin.replaceAll('v', 'ü')
  return match(text, pinyin)
}
