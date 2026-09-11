import { computed, ref, watch } from 'vue'

export function useSourceVersions(axios, base, initialBranch = 'alpha', initialRemote = 'origin') {
  const savedRemotes = ref([])
  let remoteRequest = 0
  const mode = ref('branch')
  const pulls = ref([])
  let nextPullId = 1
  const pullRows = ref([{ id: nextPullId++, number: null }])
  const pullNumbers = computed(() => pullRows.value.map((row) => row.number))
  const canCheckPulls = computed(
    () =>
      pullNumbers.value.length > 0 &&
      pullNumbers.value.every(Number.isInteger) &&
      new Set(pullNumbers.value).size === pullNumbers.value.length
  )
  const remote = ref(initialRemote)
  const branch = ref(initialBranch)
  const reference = ref(initialBranch)
  const history = ref(null)
  const checked = ref(null)
  const loading = ref(false)
  const checking = ref(false)
  const error = ref('')
  let historyRequest = 0
  let checkRequest = 0
  const message = (err) => err.response?.data?.message || err.message || '操作失败，请重试'

  watch(
    [mode, pullNumbers, remote, branch, reference],
    () => {
      checked.value = null
      checkRequest++
      checking.value = false
    },
    { flush: 'sync' }
  )

  async function loadHistory() {
    const request = ++historyRequest
    const selected = branch.value
    const selectedRemote = remote.value
    loading.value = true
    error.value = ''
    try {
      const { data } = await axios.get(`${base}/source/history`, {
        params: { branch: selected, remote: selectedRemote }
      })
      if (
        request !== historyRequest ||
        selected !== branch.value ||
        selectedRemote !== remote.value
      )
        return
      if (!data.ok) throw new Error(data.message)
      history.value = data
      if (!selected) {
        branch.value = data.branch
        reference.value = data.branch
      }
    } catch (err) {
      if (
        request === historyRequest &&
        selected === branch.value &&
        selectedRemote === remote.value
      )
        error.value = message(err)
    } finally {
      if (request === historyRequest) loading.value = false
    }
  }

  async function selectRemote(value) {
    const request = ++remoteRequest
    historyRequest++
    remote.value = value
    branch.value = ''
    reference.value = ''
    history.value = null
    pulls.value = []
    pullRows.value = [{ id: nextPullId++, number: null }]
    error.value = ''
    if (value !== 'origin') {
      loading.value = true
      try {
        const { data } = await axios.post(
          `${base}/source/remote`,
          { remote: value },
          {
            headers: { 'X-Mower-Update': '1' }
          }
        )
        if (request !== remoteRequest) return
        if (!data.ok) throw new Error(data.message)
        savedRemotes.value = data.remotes
        remote.value = data.source_url
      } catch (err) {
        if (request === remoteRequest) error.value = message(err)
        return
      } finally {
        if (request === remoteRequest) loading.value = false
      }
    }
    return refresh()
  }

  function selectBranch(value) {
    branch.value = value
    reference.value = value
    if (history.value) history.value = { ...history.value, commits: [] }
    return loadHistory()
  }

  async function loadPulls() {
    const request = ++historyRequest
    const selectedRemote = remote.value
    loading.value = true
    checked.value = null
    error.value = ''
    try {
      const { data } = await axios.get(`${base}/source/pulls`, {
        params: { remote: selectedRemote }
      })
      if (request !== historyRequest || selectedRemote !== remote.value) return
      if (!data.ok) throw new Error(data.message)
      pulls.value = data.pulls
    } catch (err) {
      if (request === historyRequest) error.value = message(err)
    } finally {
      if (request === historyRequest) loading.value = false
    }
  }

  function refresh() {
    return mode.value === 'pr' ? loadPulls() : loadHistory()
  }

  function selectMode(value) {
    mode.value = value
    return refresh()
  }

  function addPull(afterId) {
    if (pullRows.value.length >= 10) return
    const index = pullRows.value.findIndex((row) => row.id === afterId)
    pullRows.value.splice(index + 1, 0, { id: nextPullId++, number: null })
  }

  function removePull(id) {
    if (pullRows.value.length <= 1) return
    pullRows.value = pullRows.value.filter((row) => row.id !== id)
  }

  function selectPull(value, id = pullRows.value[0].id) {
    pullRows.value = pullRows.value.map((row) => (row.id === id ? { ...row, number: value } : row))
    // Multiple selections are checked together once the user finishes editing.
    if (pullRows.value.length === 1) return checkVersion()
  }

  async function checkVersion() {
    if (mode.value === 'pr' && !canCheckPulls.value) return
    const request = ++checkRequest
    checked.value = null
    checking.value = true
    error.value = ''
    try {
      const { data } = await axios.post(
        mode.value === 'pr' ? `${base}/source/pr/check` : `${base}/source/check`,
        mode.value === 'pr'
          ? { remote: remote.value, numbers: [...pullNumbers.value] }
          : { remote: remote.value, reference: reference.value, branch: branch.value },
        { headers: { 'X-Mower-Update': '1' } }
      )
      if (request !== checkRequest) return
      if (!data.ok) throw new Error(data.message)
      checked.value = data
    } catch (err) {
      if (request === checkRequest) error.value = message(err)
    } finally {
      if (request === checkRequest) checking.value = false
    }
  }

  return {
    savedRemotes,
    mode,
    pulls,
    pullRows,
    canCheckPulls,
    addPull,
    removePull,
    selectMode,
    selectPull,
    refresh,
    remote,
    selectRemote,
    branch,
    reference,
    history,
    checked,
    loading,
    checking,
    error,
    loadHistory,
    selectBranch,
    checkVersion
  }
}
