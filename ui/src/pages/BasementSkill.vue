<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-button :loading="syncing" :disabled="loading" @click="syncCultivate">
        同步森空岛练度
      </n-button>
      <n-text depth="3">{{ dataMessage }}</n-text>
      <n-text v-if="error" type="error">{{ error }}</n-text>
    </n-space>
    <n-space align="center" class="skill-filters">
      <n-input v-model:value="name_select" clearable placeholder="干员名称 / 拼音" />
      <n-input v-model:value="des_select" clearable placeholder="技能名称或描述 / 拼音" />
      <n-select
        v-model:value="facility_select"
        clearable
        :options="facilityOptions"
        placeholder="全部设施"
      />
      <n-select
        v-model:value="ownership_select"
        clearable
        :options="ownershipOptions"
        placeholder="全部持有状态"
      />
      <n-select
        v-model:value="status_select"
        clearable
        :options="statusOptions"
        placeholder="全部解锁状态"
      />
    </n-space>
    <n-text depth="3">
      {{ filteredItems.length }} 名干员，{{ filteredSkillCount }}
      个技能版本。已替换表示同一技能的升级版本已解锁。
    </n-text>
    <n-empty v-if="!filteredItems.length" description="没有符合筛选条件的基建技能" />
    <n-virtual-list
      v-else
      :item-size="130"
      :items="filteredItems"
      item-resizable
      visible-items-tag="table"
      style="width: 100%; height: 65vh; border-style: none"
    >
      <template #default="{ item, index }">
        <tbody>
          <tr v-if="index === 0">
            <th>干员</th>
            <th>技能序号</th>
            <th>解锁条件</th>
            <th>当前状态</th>
            <th>技能名称</th>
            <th>进驻场所</th>
            <th>描述</th>
          </tr>
          <CustomComponent
            :avatar="item.avatar"
            :span="item.span"
            :child-skill="item.childSkill"
            :ownership="item.ownership"
            :progression="item.progression"
          />
        </tbody>
      </template>
    </n-virtual-list>
  </n-space>
</template>

<script setup>
import axios from 'axios'
import CustomComponent from '@/components/buffer.vue'
import { ref, computed, onMounted } from 'vue'
import { useBasementSkill } from '@/stores/basementSkill'
import {
  annotateBasementSkills,
  filterBasementSkills,
  ownershipLabels,
  skillStatusLabels
} from '@/utils/basementSkills'

const { skill, load } = useBasementSkill()
const snapshot = ref(null)
const loading = ref(false)
const syncing = ref(false)
const error = ref('')
const name_select = ref('')
const des_select = ref('')
const facility_select = ref(null)
const ownership_select = ref(null)
const status_select = ref(null)

const skill_items = computed(() => annotateBasementSkills(skill.value, snapshot.value))
const facilityOptions = computed(() =>
  [...new Set(skill.value.flatMap((operator) => operator.child_skill.map((s) => s.roomType)))].map(
    (value) => ({ value, label: value })
  )
)
const ownershipOptions = Object.entries(ownershipLabels).map(([value, label]) => ({ value, label }))
const statusOptions = Object.entries(skillStatusLabels)
  .filter(([value]) => value !== 'unowned')
  .map(([value, label]) => ({ value, label }))
const filteredItems = computed(() =>
  filterBasementSkills(skill_items.value, {
    name: name_select.value,
    description: des_select.value,
    facility: facility_select.value,
    ownership: ownership_select.value,
    status: status_select.value
  })
)
const filteredSkillCount = computed(() =>
  filteredItems.value.reduce((count, item) => count + item.childSkill.length, 0)
)
const dataMessage = computed(() => {
  if (loading.value) return '正在读取本地森空岛练度…'
  return snapshot.value?.message || '同步森空岛练度后可显示持有和技能解锁状态。'
})

async function loadOwnedOperators() {
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/basement-skill/operators`)
    snapshot.value = response.data
  } catch (e) {
    error.value = `读取森空岛练度失败：${e.message || e}`
  } finally {
    loading.value = false
  }
}

async function syncCultivate() {
  if (syncing.value || loading.value) return
  syncing.value = true
  error.value = ''
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/cultivate-fetch`)
    if (!response.data.success) {
      error.value = response.data.message || '同步森空岛练度失败'
      return
    }
    await loadOwnedOperators()
  } catch (e) {
    error.value = `同步森空岛练度失败：${e.message || e}`
  } finally {
    syncing.value = false
  }
}

onMounted(() => Promise.all([load(), loadOwnedOperators()]))
</script>

<style scoped>
.skill-filters :deep(.n-input),
.skill-filters :deep(.n-select) {
  width: 190px;
}
</style>
