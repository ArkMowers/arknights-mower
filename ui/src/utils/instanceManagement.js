import { initializeManager } from '../../manager/bridge.js'

const actions = [
  'add',
  'remove',
  'rename',
  'update_settings',
  'update_all_settings',
  'start',
  'stop',
  'start_all',
  'stop_all'
]

const localManagerMessage = '实例管理仅支持本机多开管理器或 Mower 桌面窗口，请在本机打开。'

export function createInstanceManagement({ target = window } = {}) {
  const nativeApi = () => target.pywebview?.api
  const useNative = () => typeof nativeApi()?.get_instances === 'function'

  async function request(action, args = []) {
    if (!useNative()) throw new Error(localManagerMessage)
    const method = nativeApi()[action]
    if (typeof method !== 'function') throw new Error('当前桌面版本不支持此实例操作，请更新 Mower')
    return method.apply(nativeApi(), args)
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
    async initialize(renderInstances) {
      try {
        await initializeManager(async (instances) => {
          await renderInstances(validate(instances))
        }, target)
      } catch (failure) {
        if (!useNative()) throw new Error(localManagerMessage, { cause: failure })
        throw failure
      }
    }
  }
}
