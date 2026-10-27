import { i18n } from '@/i18n'
import { maaQueueMessages } from '@/i18n/messages/maaQueue'

const messageKeys = new Map(
  Object.entries(maaQueueMessages['zh-CN'])
    .filter(([, message]) => !message.includes('{'))
    .map(([key, message]) => [message, key])
)

export function copilotMessage(message) {
  if (typeof message !== 'string') return message
  const suffix = '。队列未改变，已入库作业可从已有作业中选择'
  if (message.endsWith(suffix)) {
    return i18n.global.t('maaQueue.partialImport', {
      reason: copilotMessage(message.slice(0, -suffix.length))
    })
  }
  const capacity = /^队列最多 32 项，当前还可加入 (\d+) 项；请整理队列后重试$/.exec(message)
  if (capacity) return i18n.global.t('maaQueue.queueCapacity', { remaining: capacity[1] })
  const key = messageKeys.get(message)
  return key ? i18n.global.t(`maaQueue.${key}`) : message
}

export function parseCopilotCode(value) {
  const code = value.trim()
  const set = /^prts:\/\/s(\d+)$/i.exec(code)
  if (set) return { id: set[1], set: true }
  const number = /^(?:(?:prts|maa):\/\/)?(\d+)$/i.exec(code)
  if (number) return { id: number[1], set: false }
  try {
    const url = new URL(code)
    if (url.protocol === 'https:' && url.host === 'prts.plus' && !url.username && !url.password) {
      const operation = /^\/operation\/(\d+)\/?$/.exec(url.pathname)
      if (operation) return { id: operation[1], set: false }
    }
  } catch {
    // Plain codes are handled above; an invalid URL is not a download target.
  }
  throw new Error('请输入有效的 prts:// 作业代码、PRTS Plus 作业链接或编号')
}

export async function downloadCopilotScripts(axios, source, endpoint, remaining) {
  const target = parseCopilotCode(source)
  const base = `${import.meta.env.VITE_HTTP_URL || ''}/network`
  const ids = target.set
    ? (await axios.get(`${base}/maa-copilot-set/${target.id}`)).data.ids
    : [target.id]
  if (!Array.isArray(ids) || !ids.length || ids.some((id) => !/^\d+$/.test(id))) {
    throw new Error('作业集为空或包含无效作业编号')
  }
  if (ids.length > remaining) {
    throw new Error(`队列最多 32 项，当前还可加入 ${remaining} 项；请整理队列后重试`)
  }
  const blobs = []
  for (const id of ids) {
    const { data } = await axios.get(`${base}/maa-copilot/${id}`)
    const content = data.data?.content
    if (typeof content !== 'string') throw new Error('下载的作业内容缺失')
    const blob = new Blob([content], { type: 'application/json' })
    if (blob.size > 1024 * 1024) throw new Error('作业文件不能超过 1 MB')
    blobs.push(blob)
  }
  const scripts = []
  try {
    for (const blob of blobs) {
      const form = new FormData()
      form.append('copilot', blob)
      const { data } = await axios.post(endpoint, form)
      scripts.push(data)
    }
  } catch (error) {
    const reason = error.response?.data?.message || error.message || '作业导入失败'
    const failure = new Error(`${reason}。队列未改变，已入库作业可从已有作业中选择`)
    failure.refreshLibrary = true
    throw failure
  }
  return scripts
}
