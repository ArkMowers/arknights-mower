import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { extract_inventory_counts } from '@/utils/trigger_inventory'

export const usedepotStore = defineStore('depot', () => {
  /**
   * 缓存是否还在有效期内。
   *
   * 仓库页（report）与触发条件（inventory）各留一份缓存是故意的：前者要分类、档位、
   * 扫描时间，后者只要一张扁平的数量表，刷新节奏也不同（15s / 30s）。但"什么时候算
   * 过期"只能有一份实现，抄成两处迟早有一处把比较方向写反。
   */
  function isCacheFresh(loadedAt, ttl) {
    return loadedAt > 0 && Date.now() - loadedAt < ttl
  }

  const inventory = ref({})
  const inventoryLoaded = ref(false)
  const inventoryLoadError = ref('')
  let inventoryLoadedAt = 0
  let inventoryRequest = null

  // 仓库页自己的状态。与上面的 inventory 分开存：trigger 只关心扁平的数量表，
  // 仓库页还要分类、档位、扫描时间，把渲染需要的东西塞进 inventory 会污染调用方。
  const report = ref(null)
  const reportLoaded = ref(false)
  const reportError = ref('')
  const loading = ref(false)
  const history = ref([])
  const historyError = ref('')
  const historyLoading = ref(false)
  let reportLoadedAt = 0
  let reportRequest = null
  let historyRequest = null

  async function getDepotinfo() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
    return response.data
  }

  async function loadInventory(force = false) {
    if (!force && inventoryLoaded.value && isCacheFresh(inventoryLoadedAt, 30_000)) {
      return inventory.value
    }
    if (inventoryRequest) return inventoryRequest
    inventoryLoadError.value = ''
    inventoryRequest = getDepotinfo()
      .then((response) => {
        inventory.value = extract_inventory_counts(response)
        inventoryLoaded.value = true
        inventoryLoadedAt = Date.now()
        return inventory.value
      })
      .catch((error) => {
        inventoryLoadError.value = error?.message || '读取库存失败'
        throw error
      })
      .finally(() => {
        inventoryRequest = null
      })
    return inventoryRequest
  }

  /**
   * 快照序列，供环比与趋势使用。失败时只记错误、不抛，趋势不该拖垮整页。
   *
   * 默认不传 limit：取多少条由设置里的「仓库历史条数」决定（服务端按配置决定上限），
   * 页面不需要知道那个数。要临时少取一点时才显式传。
   */
  async function loadHistory(limit) {
    if (historyRequest) return historyRequest
    historyLoading.value = true
    historyError.value = ''
    historyRequest = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/depot/history`, {
        params: limit ? { limit } : {}
      })
      .then((response) => {
        const snapshots = response.data?.snapshots
        history.value = Array.isArray(snapshots) ? snapshots : []
        return history.value
      })
      .catch((error) => {
        historyError.value = error?.message || '读取历史失败'
        history.value = []
        return []
      })
      .finally(() => {
        historyLoading.value = false
        historyRequest = null
      })
    return historyRequest
  }

  /**
   * 仓库页一次拉全量。两个请求并行且各自失败互不牵连：历史挂了仍然要能看当前仓库。
   * getDepotinfo 失败时走它的 catch（那里已写好 reportError）并让本函数 reject 出去，
   * 页面据此提示刷新失败；历史失败在 loadHistory 内部已经降级成空数组。
   */
  async function loadReport({ force = false, ttl = 15_000 } = {}) {
    if (!force && report.value && reportLoaded.value && isCacheFresh(reportLoadedAt, ttl)) {
      return report.value
    }
    if (reportRequest) return reportRequest
    loading.value = true
    reportError.value = ''
    reportRequest = Promise.all([
      getDepotinfo().catch((error) => {
        reportError.value = error?.message || '读取仓库失败'
        throw error
      }),
      loadHistory()
    ])
      .then(([response]) => {
        report.value = response
        reportLoaded.value = true
        reportLoadedAt = Date.now()
        return response
      })
      .finally(() => {
        loading.value = false
        reportRequest = null
      })
    return reportRequest
  }

  return {
    getDepotinfo,
    loadInventory,
    loadHistory,
    loadReport,
    inventory,
    inventoryLoaded,
    inventoryLoadError,
    report,
    reportLoaded,
    reportError,
    history,
    historyError,
    historyLoading,
    loading
  }
})
