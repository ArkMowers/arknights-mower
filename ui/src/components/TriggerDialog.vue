<script setup>
import { computed, inject, ref, watch } from 'vue'
const show = inject('show_trigger_editor')
const edit_locked = inject('planEditLocked', ref(false))
watch(edit_locked, (locked) => {
  if (locked) show.value = false
})

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'

const plan_store = inject('planStore', null) || usePlanStore()
const { sub_plan, backup_plans, backup_groups } = storeToRefs(plan_store)
const current_backup = computed(() => backup_plans.value[sub_plan.value])
const group_options = computed(() =>
  backup_groups.value.map((group) => ({ label: group.name, value: group.id }))
)
const editing_group = ref('default')
watch(
  () => current_backup.value?.group_ids,
  (ids) => {
    if (!ids?.includes(editing_group.value)) editing_group.value = ids?.[0] ?? 'default'
  },
  { immediate: true, deep: true }
)
const selected_group = computed(() =>
  backup_groups.value.find((group) => group.id === editing_group.value)
)
const new_group_name = ref('')
function create_group() {
  if (edit_locked.value || !new_group_name.value.trim()) return
  const group = {
    id: crypto.randomUUID(),
    name: new_group_name.value.trim(),
    trigger: { left: '', operator: '', right: '' }
  }
  backup_groups.value.push(group)
  current_backup.value.group_ids = [
    ...new Set([...(current_backup.value.group_ids ?? []), group.id])
  ]
  editing_group.value = group.id
  new_group_name.value = ''
}
function remove_group(id) {
  if (edit_locked.value || id === 'default') return
  for (const backup of backup_plans.value) {
    backup.group_ids = (backup.group_ids ?? ['default']).filter((group) => group !== id)
    if (!backup.group_ids.length) backup.group_ids = ['default']
  }
  if (editing_group.value === id) editing_group.value = 'default'
  backup_groups.value = backup_groups.value.filter((group) => group.id !== id)
}
function move_group(id, offset) {
  if (edit_locked.value) return
  const groups = backup_groups.value
  const index = groups.findIndex((group) => group.id === id)
  const target = index + offset
  if (target < 0 || target >= groups.length || groups[target].id === 'default') return
  ;[groups[index], groups[target]] = [groups[target], groups[index]]
}
function update_memberships(ids) {
  if (!edit_locked.value) current_backup.value.group_ids = ids.length ? ids : ['default']
}
function update_group_trigger(data) {
  if (!edit_locked.value && selected_group.value?.id !== 'default')
    selected_group.value.trigger = data
}
const depot_store = usedepotStore()
const facility_store = useFacilityStore()
const mastery_store = useMasteryStore()

watch(show, (visible) => {
  if (visible) {
    depot_store.loadInventory(true).catch(() => {})
    facility_store.load(true).catch(() => {})
    mastery_store.loadPlanSummary(true).catch(() => {})
  }
})

function update_trigger(data) {
  if (edit_locked.value) return
  backup_plans.value[sub_plan.value].trigger = data
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="副表条件"
    :auto-focus="false"
    transform-origin="center"
    style="width: auto; max-width: 90vw"
  >
    <n-scrollbar v-if="current_backup" style="max-height: 80vh; margin-top: 5px">
      <n-form
        :disabled="edit_locked"
        label-placement="left"
        label-width="80"
        style="min-width: 420px"
      >
        <n-form-item label="副表分组">
          <n-select
            :value="current_backup.group_ids"
            :options="group_options"
            multiple
            @update:value="update_memberships"
          />
        </n-form-item>
        <n-form-item label="副表类型">
          <n-radio-group v-model:value="current_backup.type">
            <n-radio-button value="global">全局副表</n-radio-button>
            <n-radio-button value="exclusive">互斥副表</n-radio-button>
          </n-radio-group>
        </n-form-item>
      </n-form>
      <n-text depth="3" style="display: block; margin-bottom: 12px">
        {{
          current_backup.type === 'exclusive'
            ? '当前分组在所选分组中时参与选择；最多生效一张互斥副表，当前项失效后按顺序选择。'
            : '当前分组在所选分组中时检查自身条件，可与该组的其他副表叠加。'
        }}
      </n-text>
      <n-collapse style="margin-bottom: 16px">
        <n-collapse-item title="分组条件与管理" name="groups">
          <n-text depth="3"
            >自定义分组满足条件后保持生效，失效后按顺序选择；没有符合条件的分组时使用默认分组。</n-text
          >
          <n-space vertical style="margin-top: 12px">
            <n-space v-for="group in backup_groups" :key="group.id" align="center" :wrap="false">
              <n-input
                v-model:value="group.name"
                :disabled="edit_locked || group.id === 'default'"
                placeholder="分组名称"
              />
              <template v-if="group.id !== 'default'">
                <n-button
                  :disabled="
                    edit_locked || backup_groups.findIndex((item) => item.id === group.id) <= 1
                  "
                  @click="move_group(group.id, -1)"
                  >上移</n-button
                >
                <n-button
                  :disabled="edit_locked || backup_groups.at(-1).id === group.id"
                  @click="move_group(group.id, 1)"
                  >下移</n-button
                >
                <n-popconfirm @positive-click="remove_group(group.id)">
                  <template #trigger><n-button :disabled="edit_locked">删除</n-button></template>
                  删除此归属；没有剩余分组的副表将移入默认分组。
                </n-popconfirm>
              </template>
            </n-space>
            <n-space :wrap="false">
              <n-input
                v-model:value="new_group_name"
                :disabled="edit_locked"
                placeholder="新分组名称"
                @keyup.enter="create_group"
              />
              <n-button :disabled="edit_locked || !new_group_name.trim()" @click="create_group"
                >创建分组</n-button
              >
            </n-space>
            <n-select
              v-model:value="editing_group"
              :options="group_options"
              placeholder="选择要编辑条件的分组"
            />
            <template v-if="selected_group && selected_group.id !== 'default'">
              <n-text>{{ selected_group.name }}的生效条件</n-text>
              <trigger-editor :data="selected_group.trigger" @update="update_group_trigger" />
            </template>
            <n-text v-else depth="3">默认分组作为兜底，不需要设置分组条件。</n-text>
          </n-space>
        </n-collapse-item>
      </n-collapse>
      <n-text style="display: block; margin-bottom: 8px">副表自身条件</n-text>
      <n-scrollbar x-scrollable>
        <trigger-editor :data="backup_plans[sub_plan].trigger" @update="update_trigger" />
      </n-scrollbar>
      <n-card style="margin-top: 8px" content-style="padding: 8px" embedded>
        <n-code
          :code="JSON.stringify(backup_plans[sub_plan].trigger, null, 2)"
          language="json"
          word-wrap
        />
      </n-card>
    </n-scrollbar>
  </n-modal>
</template>

<style>
.dropdown-container {
  display: flex;
  align-items: center;
  margin-top: 5px;
}

.dropdown-label {
  flex: 0 0 40%;
  max-width: 125px;
}

.dropdown-select {
  flex: 1;
}
</style>
