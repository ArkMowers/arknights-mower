import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { extract_inventory_counts } from '@/utils/trigger_inventory'

export const usedepotStore = defineStore('depot', () => {
  const inventory = ref({})
  const inventoryLoaded = ref(false)
  const inventoryLoadError = ref('')
  let inventoryLoadedAt = 0
  let inventoryRequest = null

  async function getDepotinfo() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/depot/readdepot`)
    return response.data
  }

  async function loadInventory(force = false) {
    if (!force && inventoryLoaded.value && Date.now() - inventoryLoadedAt < 30_000) {
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

  return {
    getDepotinfo,
    loadInventory,
    inventory,
    inventoryLoaded,
    inventoryLoadError
  }
})
