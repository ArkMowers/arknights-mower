import { defineStore } from 'pinia'
import axios from 'axios'

export const useReportStore = defineStore('report', () => {
  async function getReportData() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/getReportData`)
    console.log(response.data)
    return response.data
  }
  async function getOrundumData() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/getOrundumData`)
    console.log(response.data)
    return response.data
  }
  return {
    getReportData,
    getOrundumData
  }
})
