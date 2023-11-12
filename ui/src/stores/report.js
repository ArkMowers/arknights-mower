import { defineStore } from 'pinia'
import axios from 'axios'
export const useReportStore = defineStore('record', () => {
    async function getReportData() {
        const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/report/getReportData`)
        return response.data
    }
    return {
        getReportData
    }
})
