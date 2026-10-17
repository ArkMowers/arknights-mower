import { defineStore } from 'pinia'
import axios from 'axios'

const moodApi = import.meta.env.VITE_MOOD_HISTORY_API || import.meta.env.VITE_HTTP_URL || ''
const mainApi = import.meta.env.VITE_HTTP_URL || ''

export const useRecordStore = defineStore('record', () => {
  async function getMoodRatios() {
    const response = await axios.get(`${mainApi}/record/getMoodRatios`)
    return response.data
  }

  // An optional local read-only bridge serves a running packaged Mower without
  // restarting it. In a normal deployment these GETs use the same Flask backend.
  async function getMoodCatalog() {
    const response = await axios.get(`${moodApi}/record/mood-available-operators`)
    return response.data
  }

  async function getMoodSeries(names) {
    if (!Array.isArray(names) || !names.length) return []
    const response = await axios.get(`${moodApi}/record/mood-series`, {
      params: { names: JSON.stringify([...new Set(names)].slice(0, 16)) }
    })
    return response.data
  }

  return { getMoodRatios, getMoodCatalog, getMoodSeries }
})
