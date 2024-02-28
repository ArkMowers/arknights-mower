<template>
  <div class="card-container" style="user-select: text">
    <n-grid x-gap="10px" y-gap="10px" cols="1" responsive="screen">
      <n-gi v-for="(categoryItems, categoryName) in categorizedMaterials" :key="categoryName">
        <n-h2>{{ categoryName }}</n-h2>
        <n-grid x-gap="10px" y-gap="10px" cols="2 m:6 l:6 " responsive="screen">
          <n-gi v-for="(itemData, itemId) in categoryItems" :key="itemId">
            <n-thing>
              <template #avatar>
                <n-avatar color="000" size="large" :src="'/depot/' + itemData['name'] + '.png'" />
              </template>
              <template #header>{{ itemData['displayName'] }}</template>
              <template #description>拥有：{{ itemData['quantity'][0] }}</template>
            </n-thing>
          </n-gi>
        </n-grid>
      </n-gi>
    </n-grid>
  </div>
</template>
<style>
.card-container {
  display: flex;
  margin: 10px, 0px, 0px, 50px;
  flex-wrap: wrap;
}
</style>
<script setup>
import { ref, onMounted, computed } from 'vue'
import { usedepotStore, tireCategories } from '@/stores/depot'
import itemsData from './key_mapping.json'

const depotStore = usedepotStore()
const { getDepotinfo } = depotStore

const itemsdict = ref(itemsData)
const reportData = ref([])

async function fetchData() {
  reportData.value = await getDepotinfo()
}

onMounted(fetchData)

const translatedDict = computed(() => {
  const translated = {}
  for (const [key, value] of Object.entries(reportData.value)) {
    translated[key] = [
      itemsdict.value[key]?.[1] ?? '未知', // Use optional chaining for potential undefined value
      value
    ]
  }
  return translated
})

const tierData = ref(
  Object.fromEntries(Object.entries(tireCategories).map(([key, value]) => [key, ref(value)]))
)

function findMatchingKey(value) {
  return Object.entries(itemsdict.value).find(([key, val]) => val.includes(value))?.[0] ?? null
}

const categorizedMaterials = computed(() => {
  const categorized = {
    常用: [],
    杂物: [],
    信物: [],
    基建材料: []
  }
  const categorizedKeys = new Set()

  for (const key in translatedDict.value) {
    if (key.startsWith('p_char_') || key.startsWith('tier6_')) {
      categorized['信物'].push(createMaterialObject(key, translatedDict.value[key]))
      categorizedKeys.add(key)
    } else if (key.startsWith('MTL_BASE') || key.startsWith('COIN_FURN')) {
      categorized['基建材料'].push(createMaterialObject(key, translatedDict.value[key]))
      categorizedKeys.add(key)
    } else if (
      key.startsWith('DIAMOND') ||
      key.startsWith('MTL_DIAMOND') ||
      key.startsWith('GOLD')
    ) {
      categorized['常用'].push(createMaterialObject(key, translatedDict.value[key]))
      categorizedKeys.add(key)
    }
  }

  for (const tier in tierData.value) {
    tierData.value[tier].forEach((materialName) => {
      let materialInfo = Object.entries(translatedDict.value).find(
        ([key, [name, quantity]]) => name === materialName
      )

      if (!materialInfo) {
        materialInfo = [findMatchingKey(materialName), [materialName, [0, 0]]]
      }

      if (!categorized[tier]) {
        categorized[tier] = []
      }
      categorized[tier].push(createMaterialObject(materialInfo[0], materialInfo[1]))
      categorizedKeys.add(materialInfo[0])
    })
  }

  for (const key in translatedDict.value) {
    if (!categorizedKeys.has(key)) {
      categorized['杂物'].push(createMaterialObject(key, translatedDict.value[key]))
    }
  }
  return categorized
})

function createMaterialObject(key, value) {
  return {
    name: key,
    displayName: value[0],
    quantity: value[1]
  }
}
</script>
