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
const maxBufferedBytes = 8 * 1024 * 1024

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
  checkCapacity(kind, queue.length, items.length)
  queue.push(...items)
}

function checkCapacity(kind, used, needed) {
  if (used >= 32) throw new Error(`${queueNames[kind]}队列已满，最多 32 项`)
  if (used + needed > 32) {
    throw new Error(`${queueNames[kind]}队列最多 32 项，本次需加入 ${needed} 项，剩余容量不足`)
  }
}

async function downloadMember(axios, id, kind, mixed) {
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
  const slots = destination === 'copilot' && script?.difficulty === 3 ? 2 : 1
  return { blob, destination, slots }
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
      if (!target.set) checkCapacity(kind, configs[kind].value.scripts.length, 1)
      const ids = target.set
        ? (await axios.get(`${base}/network/maa-copilot-set/${target.id}`)).data.ids
        : [target.id]
      if (!Array.isArray(ids) || !ids.length) throw new Error('作业集为空或缺少成员列表')
      const members = []
      const errors = []
      const cached = new Map()
      let bufferedBytes = 0
      const formatFailure = (index, error) => {
        const reason = error.response?.data?.message || error.message || '作业导入失败'
        const number = typeof ids[index] === 'string' ? `（${ids[index]}）` : ''
        return `第 ${index + 1} 份${number}：${reason}`
      }
      for (const [index, id] of ids.entries()) {
        try {
          let member = cached.get(id)
          if (!member) {
            member = await downloadMember(axios, id, kind, mixed)
            if (bufferedBytes + member.blob.size <= maxBufferedBytes) {
              bufferedBytes += member.blob.size
            } else {
              // Keep metadata for every candidate; fetch overflow files only if they fit.
              member.blob = null
            }
            cached.set(id, member)
          }
          members.push({ index, member })
        } catch (error) {
          errors[index] = formatFailure(index, error)
        }
      }

      const destinations = mixed ? ['copilot', 'sss'] : [kind]
      const admitted = Object.fromEntries(destinations.map((key) => [key, []]))
      const initialSlots = Object.fromEntries(
        destinations.map((key) => [key, 32 - configs[key].value.scripts.length])
      )
      function fits(entry, slots) {
        try {
          checkCapacity(entry.member.destination, 32 - slots, entry.member.slots)
          return true
        } catch (error) {
          entry.waiting = true
          errors[entry.index] ??= formatFailure(entry.index, error)
          return false
        }
      }
      function remaining(destination, limit) {
        const liveSlots = 32 - configs[destination].value.scripts.length
        let used = 0
        // Live edits can take slots; keep accepted uploads in admission order.
        admitted[destination] = admitted[destination].filter((entry) => {
          if (!fits(entry, liveSlots - used)) return false
          used += entry.member.slots
          return true
        })
        return Math.min(limit, liveSlots) - used
      }
      async function admit(entry, limit) {
        const { member, index } = entry
        const { destination } = member
        const hasRoom = () => fits(entry, remaining(destination, limit))
        if (!hasRoom()) return
        try {
          if (!member.script) {
            let blob = member.blob
            if (!blob) {
              const fresh = await downloadMember(axios, ids[index], kind, mixed)
              if (fresh.destination !== destination || fresh.slots !== member.slots) {
                throw new Error('下载期间作业的类型或难度已变化，请重新导入')
              }
              blob = fresh.blob
              if (!hasRoom()) return
            }
            const form = new FormData()
            form.append('copilot', blob)
            const { data } = await axios.post(copilotLibraryUrl(destination), form)
            member.blob = null
            member.script = data
            member.slots = destination === 'copilot' && data.difficulty === 3 ? 2 : 1
            if (destination === kind && !library.value.some((item) => item.id === data.id)) {
              library.value.push(data)
            }
            if (!hasRoom()) return
          }
          admitted[destination].push(entry)
          entry.waiting = false
          delete errors[index]
        } catch (error) {
          entry.waiting = false
          errors[index] = formatFailure(index, error)
        }
      }
      // Complete the initial allocation first. Only unclaimed slots may fund another member.
      for (const entry of members) await admit(entry, initialSlots[entry.member.destination])
      for (;;) {
        const free = Object.fromEntries(destinations.map((key) => [key, remaining(key, 32)]))
        const eligible = members.filter(
          ({ waiting, member }) => waiting && member.slots <= free[member.destination]
        )
        if (!eligible.length) break
        const lengths = destinations.map((key) => configs[key].value.scripts.length)
        for (const entry of eligible) {
          await admit(entry, 32)
          // A new edit can make an earlier skipped member eligible before the next upload.
          if (destinations.some((key, i) => configs[key].value.scripts.length !== lengths[i])) break
        }
      }
      const counts = new Map()
      for (const destination of destinations) {
        remaining(destination, 32)
        const entries = admitted[destination].sort((a, b) => a.index - b.index)
        if (!entries.length) continue
        const added = []
        for (const { member } of entries) appendToQueue(added, destination, member.script)
        configs[destination].value.scripts.push(...added)
        if (destination === kind) selected.value = entries.at(-1).member.script.id
        counts.set(destination, entries.length)
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
