import { ref, watch } from 'vue'

export function useSourceVersions(axios, base, initialBranch = 'alpha') {
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
    [branch, reference],
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
    loading.value = true
    error.value = ''
    try {
      const { data } = await axios.get(`${base}/source/history`, { params: { branch: selected } })
      if (request !== historyRequest || selected !== branch.value) return
      if (!data.ok) throw new Error(data.message)
      history.value = data
    } catch (err) {
      if (request === historyRequest && selected === branch.value) error.value = message(err)
    } finally {
      if (request === historyRequest) loading.value = false
    }
  }

  function selectBranch(value) {
    branch.value = value
    reference.value = value
    if (history.value) history.value = { ...history.value, commits: [] }
    return loadHistory()
  }

  async function checkVersion() {
    const request = ++checkRequest
    checked.value = null
    checking.value = true
    error.value = ''
    try {
      const { data } = await axios.post(
        `${base}/source/check`,
        {
          reference: reference.value,
          branch: branch.value
        },
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
