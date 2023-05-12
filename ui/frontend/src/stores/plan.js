import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const usePlanStore = defineStore('plan', () => {
  const ling_xi = ref(1)
  const max_resting_count = ref('')
  const exhaust_require = ref('')
  const rest_in_full = ref('')
  const resting_priority = ref('')

  async function load_plan() {
    const response = await axios.get('http://localhost:8000/plan')
    ling_xi.value = response.data.conf.ling_xi.toString()
    max_resting_count.value = response.data.conf.max_resting_count.toString()
    exhaust_require.value = response.data.conf.exhaust_require
    rest_in_full.value = response.data.conf.rest_in_full
    resting_priority.value = response.data.conf.resting_priority
  }

  return {
    load_plan,
    ling_xi,
    max_resting_count,
    exhaust_require,
    rest_in_full,
    resting_priority
  }
})
