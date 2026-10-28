import { afterEach, expect, it } from 'vitest'
import { computed } from 'vue'
import { i18n } from '@/i18n'
import { resourceUpdateMessage } from './resourceUpdatePresentation'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

it('updates a resource job caption with the interface language while preserving the complete backend record', () => {
  const job = {
    id: 'original-job',
    status: 'success',
    phase: 'done',
    progress: 100,
    message: '资源包已安装，各实例在任务间歇加载，无需重启 Mower'
  }
  const before = structuredClone(job)
  const caption = computed(() => resourceUpdateMessage(job.message))
  i18n.global.locale.value = 'en-US'
  expect(caption.value).toBe(
    'Resources installed. Each instance loads them between tasks; no Mower restart is needed.'
  )
  i18n.global.locale.value = 'ja-JP'
  expect(caption.value).toContain('Mower の再起動は不要')
  i18n.global.locale.value = 'zh-TW'
  expect(caption.value).toContain('無須重新啟動 Mower')
  expect(job).toEqual(before)
  expect(resourceUpdateMessage('未知诊断：D:/用户目录/package.zip')).toBe(
    '未知诊断：D:/用户目录/package.zip'
  )
})
