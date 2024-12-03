import { defineStore } from 'pinia'
import axios from 'axios'

export const useReportStore = defineStore('report', () => {
  // 通用请求函数
  async function fetchData(endpoint, params = {}) {
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/${endpoint}`, {
        params
      })
      console.log(`[${endpoint}] Response:`, response.data)
      return response.data
    } catch (error) {
      console.error(`[${endpoint}] Error:`, error)
      throw error // 抛出错误以便调用方处理
    }
  }

  // 特定请求函数
  async function getReportData() {
    return await fetchData('report/getReportData')
  }

  async function getOrundumData() {
    return await fetchData('report/getOrundumData')
  }

  async function restoreTradingHistory() {
    return await fetchData('report/restore-trading-history')
  }

  async function getTradingHistory(start = null, end = null) {
    const params = {}
    if (start) params.startDate = start
    if (end) params.endDate = end
    return await fetchData('report/trading_history', params)
  }

  return {
    getReportData,
    getOrundumData,
    getTradingHistory,
    restoreTradingHistory
  }
})
