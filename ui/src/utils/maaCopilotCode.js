import { ref, watch } from 'vue'

export function parseCopilotCode(value) {
  const code = value.trim()
  const set = /^(?:prts:\/\/)?s(\d+)$/i.exec(code)
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

const libraryPaths = { copilot: 'maa-copilot', sss: 'sss-copilot', paradox: 'maa-paradox' }
const queueNames = { copilot: '自动战斗', sss: '保全派驻', paradox: '悖论模拟' }
const base = import.meta.env.VITE_HTTP_URL || ''

export function copilotLibraryUrl(kind) {
  return `${base}/${libraryPaths[kind]}`
}

export function appendCopilotScript(configs, kind, script) {
  appendToQueue(configs[kind].value.scripts, kind, script)
}

function appendToQueue(queue, kind, { id, difficulty }) {
  let items
  if (kind === 'sss') {
    items = [{ id, type: 1, ec: 1, times: 1 }]
  } else if (kind === 'paradox') {
    items = [{ id }]
  } else {
    const modes = difficulty === 3 ? [false, true] : [difficulty === 2]
    items = modes.map((is_raid) => ({ id, nav_name_override: '', is_raid }))
  }
  if (queue.length >= 32) throw new Error(`${queueNames[kind]}队列已满，最多 32 项`)
  if (queue.length + items.length > 32) {
    throw new Error(
      `${queueNames[kind]}队列最多 32 项，本次需加入 ${items.length} 项，剩余容量不足。已入库作业可从已有作业中选择`
    )
  }
  queue.push(...items)
}

async function importMember(axios, id, kind, mixed, available) {
  if (typeof id !== 'string' || !/^\d+$/.test(id)) throw new Error('作业编号无效')
  const destinations = mixed ? ['copilot', 'sss'] : [kind]
  if (destinations.every((key) => available(key) === 0)) {
    throw new Error(
      `${destinations.map((key) => queueNames[key]).join('和')}队列已满，每个队列最多 32 项`
    )
  }
  const { data } = await axios.get(`${base}/network/maa-copilot/${id}`)
  const content = data.data?.content
  if (typeof content !== 'string') throw new Error('下载的作业内容缺失')
  const blob = new Blob([content], { type: 'application/json' })
  if (blob.size > 1024 * 1024) throw new Error('作业文件不能超过 1 MB')
  let destination = kind
  let slots = 1
  if (mixed) {
    let script
    try {
      script = JSON.parse(content.replace(/^\uFEFF/, ''))
    } catch {
      throw new Error('作业文件不是有效 JSON')
    }
    destination = script?.type === 'SSS' ? 'sss' : 'copilot'
    if (destination === 'copilot' && script?.difficulty === 3) slots = 2
  }
  if (available(destination) < slots) {
    throw new Error(`${queueNames[destination]}队列已满，最多 32 项`)
  }
  const form = new FormData()
  form.append('copilot', blob)
  const { data: script } = await axios.post(copilotLibraryUrl(destination), form)
  return { destination, script }
}

export function useCopilotDownload({
  axios,
  configs,
  kind,
  loading,
  selected,
  library,
  refresh,
  message
}) {
  const code = ref('')
  const failures = ref([])
  watch(
    () => configs[kind].value.scripts.map(({ id }) => id),
    (ids, previous) => {
      if (
        ids.some(
          (id) => !previous.includes(id) && !library.value.some((script) => script.id === id)
        )
      ) {
        refresh()
      }
    }
  )
  async function download() {
    if (loading.value) return
    loading.value = true
    failures.value = []
    try {
      const target = parseCopilotCode(code.value)
      const mixed = target.set && kind !== 'paradox'
      const ids = target.set
        ? (await axios.get(`${base}/network/maa-copilot-set/${target.id}`)).data.ids
        : [target.id]
      if (!Array.isArray(ids) || !ids.length) throw new Error('作业集为空或缺少成员列表')
      const imported = []
      const errors = []
      const cached = new Map()
      const possibleSlots = { copilot: 32, sss: 32, paradox: 32 }
      const available = (destination) =>
        target.set ? possibleSlots[destination] : 32 - configs[destination].value.scripts.length
      const recordFailure = (index, id, error) => {
        const reason = error.response?.data?.message || error.message || '作业导入失败'
        const number = typeof id === 'string' ? `（${id}）` : ''
        errors[index] = `第 ${index + 1} 份${number}：${reason}`
      }
      for (const [index, id] of ids.entries()) {
        try {
          let member = cached.get(id)
          if (!member) {
            member = await importMember(axios, id, kind, mixed, available)
            cached.set(id, member)
          }
          const { destination, script } = member
          const size = destination === 'copilot' && script.difficulty === 3 ? 2 : 1
          const remaining = possibleSlots[destination]
          if (remaining < size) throw new Error(`${queueNames[destination]}队列已满，最多 32 项`)
          // A two-slot member may leave one free slot when the actual capacity is odd.
          possibleSlots[destination] = Math.max(size - 1, remaining - size)
          imported.push({ index, id, destination, script })
        } catch (error) {
          recordFailure(index, id, error)
        }
      }
      const queues = new Map()
      const counts = new Map()
      for (const { index, id, destination, script } of imported) {
        if (destination === kind) {
          if (!library.value.some((item) => item.id === script.id)) library.value.push(script)
          selected.value = script.id
        }
        if (!queues.has(destination))
          queues.set(destination, [...configs[destination].value.scripts])
        try {
          appendToQueue(queues.get(destination), destination, script)
          counts.set(destination, (counts.get(destination) || 0) + 1)
        } catch (error) {
          recordFailure(index, id, error)
        }
      }
      for (const destination of counts.keys()) {
        configs[destination].value.scripts = queues.get(destination)
      }
      failures.value = errors.filter(Boolean)
      if (counts.size) {
        code.value = ''
        const added = [...counts].map(([key, count]) => `${queueNames[key]} ${count} 份`).join('、')
        const summary = `已加入队列：${added}`
        if (failures.value.length) {
          message.warning(`${summary}。另有 ${failures.value.length} 份未加入，原因见导入结果`)
        } else {
          message.success(summary)
        }
      } else {
        message.error(failures.value[0])
      }
    } catch (error) {
      message.error(
        error.response?.data?.message || error.message || '作业下载失败，请检查网络代理'
      )
    } finally {
      loading.value = false
    }
  }
  return { code, download, failures }
}
