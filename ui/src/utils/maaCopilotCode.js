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

function queueEntries(kind, { id, difficulty }) {
  if (kind === 'sss') return [{ id, type: 1, ec: 1, times: 1 }]
  if (kind === 'paradox') return [{ id }]
  const modes = difficulty === 3 ? [false, true] : [difficulty === 2]
  return modes.map((is_raid) => ({ id, nav_name_override: '', is_raid }))
}

export function appendCopilotScript(configs, kind, script) {
  configs[kind].value.scripts.push(...queueEntries(kind, script))
}

async function importMember(axios, id, kind, mixed) {
  if (typeof id !== 'string' || !/^\d+$/.test(id)) throw new Error('作业编号无效')
  const { data } = await axios.get(`${base}/network/maa-copilot/${id}`)
  const content = data.data?.content
  if (typeof content !== 'string') throw new Error('下载的作业内容缺失')
  const blob = new Blob([content], { type: 'application/json' })
  if (blob.size > 1024 * 1024) throw new Error('作业文件不能超过 1 MB')
  let script
  try {
    script = JSON.parse(content.replace(/^\uFEFF/, ''))
  } catch {
    throw new Error('作业文件不是有效 JSON')
  }
  const destination = mixed ? (script?.type === 'SSS' ? 'sss' : 'copilot') : kind
  const form = new FormData()
  form.append('copilot', blob)
  const { data: stored } = await axios.post(copilotLibraryUrl(destination), form)
  return { destination, script: stored }
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
    () => new Set(configs[kind].value.scripts.map(({ id }) => id)),
    (ids, previous) => {
      if (
        [...ids].some(
          (id) => !previous.has(id) && !library.value.some((script) => script.id === id)
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
      const imports = new Map()
      const cached = new Map()
      const errors = []
      for (const [index, id] of ids.entries()) {
        try {
          let member = cached.get(id)
          if (!member) {
            member = await importMember(axios, id, kind, mixed)
            cached.set(id, member)
            if (
              member.destination === kind &&
              !library.value.some((item) => item.id === member.script.id)
            ) {
              library.value.push(member.script)
            }
          }
          const { destination, script } = member
          if (!imports.has(destination)) imports.set(destination, [])
          imports.get(destination).push(script)
        } catch (error) {
          const reason = error.response?.data?.message || error.message || '作业导入失败'
          const number = typeof id === 'string' ? `（${id}）` : ''
          errors.push(`第 ${index + 1} 份${number}：${reason}`)
        }
      }

      for (const [destination, scripts] of imports) {
        const queue = configs[destination].value
        queue.scripts = queue.scripts.concat(
          scripts.flatMap((script) => queueEntries(destination, script))
        )
        if (destination === kind) selected.value = scripts.at(-1).id
      }
      failures.value = errors
      if (imports.size) {
        code.value = ''
        const added = [...imports]
          .map(([key, scripts]) => `${queueNames[key]} ${scripts.length} 份`)
          .join('、')
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
