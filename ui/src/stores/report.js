import { defineStore } from 'pinia'
import axios from 'axios'

export const useReportStore = defineStore('report', () => {
  async function getReportData() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/getReportData`)
    console.log(response.data)
    return response.data
  }

  return {
    getReportData
  }
})
