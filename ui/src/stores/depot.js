import { defineStore } from 'pinia'
import axios from 'axios'

export const usedepotStore = defineStore('depot', () => {
  async function getDepotinfo() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
    return response.data
  }

  return {
    getDepotinfo
  }
})
