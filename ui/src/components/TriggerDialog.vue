<script setup>
import { i18n } from '@/i18n'
import { backupGroupDisplayName } from '@/i18n/plans'
const { t } = i18n.global
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
  backup_groups.value.map((group) => ({ label: backupGroupDisplayName(group), value: group.id }))
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
    :title="t('plans.backupConditions')"
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
        <n-form-item :label="t('plans.backupGroup')" :show-feedback="false">
          <n-select
            :value="current_backup.group_ids"
            :options="group_options"
            multiple
            @update:value="update_memberships"
          />
        </n-form-item>
        <n-form-item :label="t('plans.backupType')" :show-feedback="false">
          <n-radio-group v-model:value="current_backup.type">
            <n-radio-button value="global">{{ t('plans.globalBackup') }}</n-radio-button>
            <n-radio-button value="exclusive">{{ t('plans.exclusiveBackup') }}</n-radio-button>
          </n-radio-group>
        </n-form-item>
      </n-form>
      <n-text depth="3" style="display: block; margin-bottom: 12px">
        {{
          current_backup.type === 'exclusive'
            ? t('plans.exclusiveBackupHelp')
            : t('plans.globalBackupHelp')
        }}
      </n-text>
      <n-collapse style="margin-bottom: 16px">
        <n-collapse-item :title="t('plans.groupManagement')" name="groups">
          <n-alert :show-icon="false" type="info" style="margin-bottom: 12px">{{
            t('plans.groupSelectionHelp')
          }}</n-alert>
          <n-alert
            v-if="groups_without_condition.length"
            :show-icon="false"
            type="warning"
            :title="t('plans.missingGroupConditionTitle')"
          >
            {{ groups_without_condition.map((group) => group.name).join('、')
            }}{{ t('plans.missingGroupConditionHelp') }}</n-alert
          >
          <n-space vertical style="margin-top: 12px">
            <n-space v-for="group in backup_groups" :key="group.id" align="center" :wrap="false">
              <n-input
                :value="backupGroupDisplayName(group)"
                @update:value="group.id !== 'default' && !edit_locked && (group.name = $event)"
                :disabled="edit_locked || group.id === 'default'"
                :placeholder="t('plans.groupName')"
              />
              <template v-if="group.id !== 'default'">
                <n-button
                  :disabled="
                    edit_locked || backup_groups.findIndex((item) => item.id === group.id) <= 1
                  "
                  @click="move_group(group.id, -1)"
                  >{{ t('plans.moveUp') }}</n-button
                >
                <n-button
                  :disabled="edit_locked || backup_groups.at(-1).id === group.id"
                  @click="move_group(group.id, 1)"
                  >{{ t('plans.moveDown') }}</n-button
                >
                <n-popconfirm @positive-click="remove_group(group.id)">
                  <template #trigger
                    ><n-button :disabled="edit_locked">{{ t('plans.delete') }}</n-button></template
                  >{{ t('plans.deleteGroupHelp') }}</n-popconfirm
                >
              </template>
            </n-space>
            <n-space :wrap="false">
              <n-input
                v-model:value="new_group_name"
                :disabled="edit_locked"
                :placeholder="t('plans.newGroupName')"
                @keyup.enter="create_group"
              />
              <n-button :disabled="edit_locked || !new_group_name.trim()" @click="create_group">{{
                t('plans.createGroup')
              }}</n-button>
            </n-space>
            <n-select
              v-model:value="editing_group"
              :options="group_options"
              :placeholder="t('plans.chooseConditionGroup')"
            />
            <template v-if="selected_group && selected_group.id !== 'default'">
              <n-text>{{ t('plans.groupConditionsTitle', { name: selected_group.name }) }}</n-text>
              <trigger-editor :data="selected_group.trigger" @update="update_group_trigger" />
            </template>
            <n-text v-else depth="3">{{ t('plans.defaultGroupHelp') }}</n-text>
          </n-space>
        </n-collapse-item>
      </n-collapse>
      <n-text style="display: block; margin-bottom: 8px">{{
        t('plans.backupOwnConditions')
      }}</n-text>
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
