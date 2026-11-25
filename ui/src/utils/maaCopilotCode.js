import { computed, nextTick, ref, toRaw, watch } from 'vue'

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

// A mixed set can write to both the ordinary and SSS libraries before publishing either queue.
const mixedLibrary = { imports: ref(0), deletions: new Set() }
const paradoxLibrary = { imports: ref(0), deletions: new Set() }

export function useCopilotLibrary({ axios, configs, kind, message, store }) {
  const library = ref([])
  const selected = ref(null)
  const backupWarning = ref('')
  const activity = kind === 'paradox' ? paradoxLibrary : mixedLibrary
  const endpoint = copilotLibraryUrl(kind)
  const loading = ref(false)
  const canDelete = computed(
    () =>
      !activity.imports.value &&
      !!selected.value &&
      !configs[kind].value.scripts.some((item) => item.id === selected.value)
  )
  let latestRefresh = 0
  async function refresh() {
    const request = ++latestRefresh
    try {
      const { data } = await axios.get(endpoint)
      if (request !== latestRefresh) return
      library.value = data.scripts
      backupWarning.value = data.backup_warning || ''
    } catch (error) {
      if (request === latestRefresh) message.error(error.response?.data?.message || '读取作业失败')
    }
  }
  async function beginImport() {
    activity.imports.value++
    if (activity.deletions.size) await Promise.allSettled(activity.deletions)
  }
  async function delete_script() {
    if (!canDelete.value) return
    const id = selected.value
    try {
      await store.flush_config_saves()
      if (!canDelete.value || selected.value !== id) return
      const deletion = axios.delete(`${endpoint}/${id}`)
      activity.deletions.add(deletion)
      try {
        await deletion
      } finally {
        activity.deletions.delete(deletion)
      }
      if (selected.value === id) selected.value = null
      await refresh()
    } catch (error) {
      message.error(error.response?.data?.message || '删除作业失败')
    }
  }
  async function publishImports(imports, errors) {
    if (imports.size && store.autosave_paused) throw new Error('配置保存已暂停，请稍后重试')
    const newRows = new Map()
    for (const [destination, members] of imports) {
      const rows = members.flatMap(({ script }) => queueEntries(destination, script))
      newRows.set(destination, rows)
      const queue = configs[destination].value
      queue.scripts = queue.scripts.concat(rows)
    }
    while (imports.size) {
      await nextTick()
      try {
        await store.flush_config_saves()
        if (store.autosave_paused) throw new Error('配置保存已暂停')
        return
      } catch (error) {
        const data = error.response?.data
        if (error.response?.status !== 409 || data?.code !== 'copilot_scripts_missing') {
          throw new Error(
            `队列保存结果未确认，请刷新后核对。 ${data?.message || error.message || ''}`.trim(),
            { cause: error }
          )
        }
        let removed = false
        for (const [destination, members] of imports) {
          const missing = new Set(data.missing_scripts?.[destination])
          const kept = members.filter(({ script, index, id }) => {
            if (!missing.has(script.id)) return true
            errors[index] = id
              ? `第 ${index + 1} 份（${id}）：作业文件已被删除`
              : '作业文件已被删除'
            return false
          })
          if (kept.length === members.length) continue
          removed = true
          if (kept.length) imports.set(destination, kept)
          else imports.delete(destination)
          const queue = configs[destination].value
          const added = new Set(newRows.get(destination))
          queue.scripts = queue.scripts.filter(
            (row) => !missing.has(row.id) || !added.has(toRaw(row))
          )
          if (destination === kind)
            library.value = library.value.filter((script) => !missing.has(script.id))
        }
        if (!removed)
          throw new Error(data.message || '队列中有已删除的作业，保存失败', { cause: error })
      }
    }
  }
  async function upload({ file, onFinish, onError }) {
    loading.value = true
    try {
      await beginImport()
      const form = new FormData()
      form.append('copilot', file.file)
      const { data } = await axios.post(endpoint, form)
      await refresh()
      const imports = new Map([[kind, [{ script: data, index: 0 }]]])
      const errors = []
      await publishImports(imports, errors)
      if (!imports.size) throw new Error(errors[0])
      selected.value = data.id
      message.success('作业已导入并加入队列')
      onFinish()
    } catch (error) {
      message.error(error.response?.data?.message || error.message || '作业导入失败')
      onError()
    } finally {
      activity.imports.value--
      loading.value = false
    }
  }
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
      await beginImport()
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
          imports.get(destination).push({ script, index, id })
        } catch (error) {
          const reason = error.response?.data?.message || error.message || '作业导入失败'
          const number = typeof id === 'string' ? `（${id}）` : ''
          errors[index] = `第 ${index + 1} 份${number}：${reason}`
        }
      }

      if (cached.size) await refresh()
      await publishImports(imports, errors)
      if (imports.has(kind)) selected.value = imports.get(kind).at(-1).script.id
      failures.value = errors.filter(Boolean)
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
      activity.imports.value--
      loading.value = false
    }
  }
  return {
    backupWarning,
    code,
    canDelete,
    delete_script,
    download,
    failures,
    library,
    loading,
    refresh,
    selected,
    upload
  }
}
