export function swap(source, target, arr) {
  const source_plan = arr[source]
  arr[source] = arr[target]
  arr[target] = source_plan
}

import { match } from 'pinyin-pro'

export function pinyin_match(text, pinyin) {
  pinyin = pinyin.replaceAll('v', 'ü')
  return match(text, pinyin)
}
