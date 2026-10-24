import { initializeManager, managerCall } from '../../manager/bridge.js'

const actions = [
  'add',
  'remove',
  'rename',
  'set_path',
  'update_settings',
  'update_all_settings',
  'start',
  'stop',
  'start_all',
  'stop_all'
]

function requestError(failure) {
  if ([404, 405].includes(failure.response?.status))
    return new Error('当前 Mower 版本不支持网页实例管理，请更新 Mower 后重试')
  return new Error(failure.response?.data?.message || failure.message || '实例管理请求失败，请重试')
}

export function createInstanceManagement({
  axios = null,
  target = window,
  getTargets = () => []
} = {}) {
  const base = `${import.meta.env.VITE_HTTP_URL || ''}/instances`
  const nativeApi = () => target.pywebview?.api
  const useNative = () => typeof nativeApi()?.get_instances === 'function'

  async function request(action, args = []) {
    if (useNative()) {
      const method = nativeApi()[action]
      if (typeof method !== 'function')
        throw new Error('当前桌面版本不支持此实例操作，请更新 Mower')
      return method.apply(nativeApi(), args)
    }
    if (!axios) throw new Error('实例管理连接尚未就绪，请重新加载')
    try {
      if (action === 'get_instances') return (await axios.get(base, { timeout: 15000 })).data
      const submitted = [...args]
      if (['add', 'start_all', 'stop_all'].includes(action)) submitted.push(getTargets())
      const { data } = await axios.post(
        `${base}/actions`,
        { action, args: submitted },
        { headers: { 'X-Mower-Settings': '1' }, timeout: 15000 }
      )
      if (data?.ok === false) throw new Error(data.message || '实例操作失败，请重试')
      return data
    } catch (failure) {
      throw requestError(failure)
    }
  }

  function validate(instances) {
    if (!Array.isArray(instances)) throw new Error('实例列表格式不正确，请重试')
    return instances
  }

  const api = Object.fromEntries(
    actions.map((action) => [action, (...args) => request(action, args)])
  )
  api.get_instances = async () => validate(await request('get_instances'))
  api.select_path = (...args) => request('select_path', args)

  return {
    api,
    get nativeDirectoryPicker() {
      return useNative() && typeof nativeApi().select_path === 'function'
    },
    async initialize(renderInstances) {
      if (useNative() || target.pywebview || !axios) {
        await initializeManager(async (instances) => {
          await renderInstances(validate(instances))
        }, target)
        return
      }
      await renderInstances(await managerCall(api.get_instances))
    }
  }
}
