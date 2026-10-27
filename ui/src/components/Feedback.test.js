import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import axios from 'axios'
import { i18n } from '@/i18n'
import Feedback from './Feedback.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => ref(true)
}))
vi.mock('axios', () => ({ default: { post: vi.fn() } }))
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('keeps feature enum and drafted user text in the feedback payload after labels change language', async () => {
  const scope = effectScope()
  try {
    const page = scope.run(() => Feedback.setup({}, { expose: vi.fn() }))
    page.feedbackData.value.type = '功能建议'
    page.feedbackData.value.description = '请保留用户自己的反馈内容和路径 D:/示例'
    const original = structuredClone(
      page.feedbackData.value.__v_raw || { ...page.feedbackData.value }
    )
    const chinese = page.feedbackTypeOptions[1].label
    i18n.global.locale.value = 'en-US'
    expect(page.feedbackTypeOptions[1].label).not.toBe(chinese)
    expect(page.feedbackTypeOptions[1].value).toBe('功能建议')
    expect(page.feedbackData.value).toEqual(original)
    expect(axios.post).not.toHaveBeenCalled()
    vi.stubGlobal('alert', vi.fn())
    vi.spyOn(console, 'log').mockImplementation(() => {})
    axios.post.mockResolvedValue({ data: '后端响应原文' })
    page.formRef.value = { validate: (callback) => callback(null) }
    await page.submitFeedback()
    expect(axios.post).toHaveBeenCalledExactlyOnceWith('/submit_feedback', original)
    expect(alert).toHaveBeenCalledWith('后端响应原文')
  } finally {
    scope.stop()
  }
})
