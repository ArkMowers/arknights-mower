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
const groups_without_condition = computed(() =>
  backup_groups.value.filter(
    (group) =>
      group.id !== 'default' &&
      !group.trigger?.function &&
      ['left', 'operator', 'right'].every((key) => {
        const value = group.trigger?.[key]
        return value == null || (typeof value === 'string' && !value.trim())
      })
  )
)
const new_group_name = ref('')
function create_group() {
  if (edit_locked.value || !new_group_name.value.trim()) return
  const used_ids = new Set(backup_groups.value.map((group) => group.id))
  let number = 1
  while (used_ids.has(`group-${number}`)) number += 1
  const group = {
    id: `group-${number}`,
    name: new_group_name.value.trim(),
    exclusive_with: [],
    trigger: { left: 'True', operator: '', right: '' }
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
  for (const group of backup_groups.value) {
    group.exclusive_with = (group.exclusive_with ?? []).filter((other) => other !== id)
  }
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
const exclusion_options = computed(() =>
  backup_groups.value
    .filter((group) => group.id !== 'default' && group.id !== editing_group.value)
    .map((group) => ({ label: group.name, value: group.id }))
)
function update_group_exclusions(ids) {
  const selected = selected_group.value
  if (edit_locked.value || !selected || selected.id === 'default') return
  const allowed = new Set(exclusion_options.value.map((option) => option.value))
  selected.exclusive_with = [...new Set(ids)].filter((id) => allowed.has(id))
  for (const group of backup_groups.value) {
    if (group.id === selected.id) continue
    const others = (group.exclusive_with ?? []).filter((id) => id !== selected.id)
    group.exclusive_with = selected.exclusive_with.includes(group.id)
      ? [...others, selected.id]
      : others
  }
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
    <div v-if="current_backup" style="margin-top: 5px">
      <n-form
        :disabled="edit_locked"
        label-placement="left"
        label-width="80"
        style="min-width: 420px; display: grid; gap: 8px; margin-bottom: 8px"
      >
        <n-form-item label="副表分组" :show-feedback="false">
          <n-select
            :value="current_backup.group_ids"
            :options="group_options"
            multiple
            @update:value="update_memberships"
          />
        </n-form-item>
        <n-form-item label="副表类型" :show-feedback="false">
          <n-radio-group v-model:value="current_backup.type">
            <n-radio-button value="global">全局副表</n-radio-button>
            <n-radio-button value="exclusive">互斥副表</n-radio-button>
          </n-radio-group>
        </n-form-item>
      </n-form>
      <n-text depth="3" style="display: block; margin-bottom: 12px">
        {{
          current_backup.type === 'exclusive'
            ? '至少一个归属分组生效时参与选择；每个生效分组最多一张互斥副表。跨组副表占用全部生效归属分组的名额，当前项仍符合条件时优先保留。'
            : '至少一个归属分组生效时检查自身条件，可与其他副表叠加；跨组归属只应用一次。'
        }}
      </n-text>
      <n-collapse style="margin-bottom: 16px">
        <n-collapse-item title="分组条件与管理" name="groups">
          <n-alert :show-icon="false" type="info" style="margin-bottom: 12px">
            分组默认可同时生效，新建分组的条件为
            True。有互斥关系时，按下方列表从上到下选择；被排除的分组不影响其他组。默认分组始终生效，不参与分组互斥；其中的副表仍须满足自身条件。旧配置已保留原有互斥关系，可在下方调整。
          </n-alert>
          <n-alert
            v-if="groups_without_condition.length"
            :show-icon="false"
            type="warning"
            title="请为分组添加生效条件"
          >
            {{ groups_without_condition.map((group) => group.name).join('、') }}
            尚未设置生效条件，不会生效。请在下方选择分组并添加生效条件。
          </n-alert>
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
              <n-form-item label="互斥分组" :show-feedback="false">
                <n-select
                  :value="selected_group.exclusive_with ?? []"
                  :options="exclusion_options"
                  multiple
                  clearable
                  placeholder="不选则允许与其他组同时生效"
                  :disabled="edit_locked"
                  @update:value="update_group_exclusions"
                />
              </n-form-item>
              <n-text depth="3"
                >互斥关系双向同步。排在前面的分组优先生效；全局副表也受分组归属限制。</n-text
              >
              <n-text>{{ selected_group.name }}的生效条件</n-text>
              <n-scrollbar x-scrollable>
                <trigger-editor :data="selected_group.trigger" @update="update_group_trigger" />
              </n-scrollbar>
            </template>
            <n-text v-else depth="3"
              >默认分组始终生效，不需要设置分组条件；其中的副表仍须满足自身条件。</n-text
            >
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
    </div>
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
