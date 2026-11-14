// The titlebar and Settings share one transaction: drain config/plan edits,
// request the existing process-control action, then persist the pending job.
// Polling/recovery stays in the existing ProcessControl component.
export async function readProcessActionStatus({ axios, base, pending }) {
  const { data } = await axios.get(base + '/status', {
    params: { id: pending.id },
    timeout: 3000
  })
  if (!data.ok) throw new Error(data.message || '进程状态查询失败')
  return data
}

export async function submitProcessAction({ axios, saves, action, base, pendingKey }) {
  await saves.pauseAndDrain()
  let mayHaveSubmitted = false
  try {
    mayHaveSubmitted = true
    const { data } = await axios.post(
      base + '/action',
      { action },
      { headers: { 'X-Mower-Control': '1' } }
    )
    if (!data.ok) {
      mayHaveSubmitted = false
      throw new Error(data.message || '进程操作已被拒绝')
    }
    const pending = { id: data.id, action, startedAt: Date.now() }
    sessionStorage.setItem(pendingKey, JSON.stringify(pending))
    return { data, pending }
  } catch (error) {
    // A lost response is ambiguous; don't unpause autosave while shutdown
    // might already be in flight. The existing recovery view owns next steps.
    if (!mayHaveSubmitted || (error.response?.status >= 400 && error.response.status < 500)) {
      saves.resume()
    }
    throw error
  }
}
