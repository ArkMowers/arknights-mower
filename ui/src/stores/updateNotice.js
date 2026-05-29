import { defineStore } from 'pinia'
import { ref } from 'vue'

import axios from 'axios'

export const useUpdateNoticeStore = defineStore('updateNotice', () => {
  const notice = ref({
    current_version: '',
    previous_version: '',
    should_show: false,
    changelog: ''
  })

  async function loadUpdateNotice() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/update-notice`)
    notice.value = {
      current_version: response.data.current_version || '',
      previous_version: response.data.previous_version || '',
      should_show: Boolean(response.data.should_show),
      changelog: response.data.changelog || ''
    }
    return notice.value
  }

  async function ackUpdateNotice(version) {
    await axios.post(`${import.meta.env.VITE_HTTP_URL}/update-notice/ack`, { version })
    notice.value = {
      ...notice.value,
      should_show: false
    }
  }

  return {
    notice,
    loadUpdateNotice,
    ackUpdateNotice
  }
})
