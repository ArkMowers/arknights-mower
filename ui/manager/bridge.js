// pywebview can inject its API before Vue mounts, so the event alone is not
// enough. Bound both bridge startup and the API call so failures are retryable.
export function loadInstances(target = window, timeout = 15000) {
  return new Promise((resolve, reject) => {
    let started = false
    const timer = setTimeout(() => {
      cleanup()
      reject(new Error('加载实例列表超时，请重试'))
    }, timeout)

    function cleanup() {
      clearTimeout(timer)
      target.removeEventListener('pywebviewready', ready)
    }

    function ready() {
      const api = target.pywebview?.api
      if (started || typeof api?.get_instances !== 'function') return
      started = true
      target.removeEventListener('pywebviewready', ready)
      Promise.resolve()
        .then(() => api.get_instances())
        .then((instances) => {
          if (!Array.isArray(instances)) throw new Error('实例列表格式错误，请重试')
          cleanup()
          resolve(instances)
        })
        .catch((error) => {
          cleanup()
          reject(error)
        })
    }

    target.addEventListener('pywebviewready', ready)
    ready()
  })
}

export async function initializeManager(renderInstances, target = window, timeout = 15000) {
  const instances = await loadInstances(target, timeout)
  await renderInstances(instances)
  await target.pywebview.api.mark_ready()
}
