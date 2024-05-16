import { defineStore } from 'pinia'
import axios from 'axios'

export const usewatermarkStore = defineStore('watermark', () => {
  async function getwatermarkinfo() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/getwatermark`)
    return response.data.toString()
  }

  return {
    getwatermarkinfo
  }
})
