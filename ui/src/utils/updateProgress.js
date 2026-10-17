// Completion belongs to the page visit that observed the task running.
// Backend results remain available for recovery and other clients.
export function createUpdateProgressSession() {
  let observed = false
  let observedId = ''
  return (job) => {
    if (!job || job.status === 'idle') {
      observed = false
      observedId = ''
      return false
    }
    if (job.status === 'running') {
      observed = true
      observedId = job.id || ''
      return true
    }
    return observed && (!observedId || !job.id || observedId === job.id)
  }
}
