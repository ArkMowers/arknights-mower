<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, ref } from 'vue'
import { operatorDisplayName, itemDisplayName } from '@/i18n/gameNames'
import { pinyin_match } from '@/utils/common'
import { render_op_option, render_op_label, filterOperatorOption } from '@/utils/op_select'

const props = defineProps({ operators: Array, item_list: Array, migrationWarning: String })
const materialOptions = computed(() =>
  (props.item_list || []).map((option) => ({
    ...option,
    label: itemDisplayName(option.value, option.label)
  }))
)
const settings = defineModel({ type: Array, default: () => [] })

const showSettingModal = ref(false)
const editingIndex = ref(null)

const tempSetting = ref({
  operator: '',
  items: []
})
const deepClone = (obj) => JSON.parse(JSON.stringify(obj))
const openEdit = (index) => {
  tempSetting.value = deepClone(settings.value[index])
  editingIndex.value = index
  showSettingModal.value = true
}

const workshop_setting_close = () => {
  if (editingIndex.value === null) {
    settings.value.push(deepClone(tempSetting.value))
  } else {
    settings.value[editingIndex.value] = deepClone(tempSetting.value)
  }
  showSettingModal.value = false
  editingIndex.value = null
}
function createNewItem() {
  return {
    item_names: [],
    children_lower_limit: 20,
    self_upper_limit: 20
  }
}
</script>

<template>
  <n-alert v-if="migrationWarning" type="warning" style="margin-bottom: 12px">
    {{ migrationWarning }}
  </n-alert>
  <n-form-item>
    <template #label>
      <span>{{ t('tasks.manualCraftingMaterials') }}</span>
      <help-text>{{ t('tasks.craftingEditDeferred') }}</help-text>
    </template>
    <n-button
      type="primary"
      @click="
        () => {
          tempSetting = { operator: '', items: [], enabled: true }
          editingIndex = null
          showSettingModal = true
        }
      "
      >{{ t('tasks.addSetting') }}</n-button
    >
    <n-list bordered>
      <n-list-item v-for="(setting, idx) in settings" :key="idx">
        <div class="flex justify-between w-full">
          <div>
            <strong>{{ t('tasks.operatorPrefix') }}</strong>
            {{ operatorDisplayName(setting.operator) }}{{ t('tasks.enabledPrefix')
            }}{{ setting.enabled }}<br />
            <ul>
              <li v-for="(item, i) in setting.items" :key="i">
                {{ item.item_names.map((name) => itemDisplayName(name)).join(', ')
                }}{{ t('tasks.ingredientMinimumPrefix') }}{{ item.children_lower_limit
                }}{{ t('tasks.productMaximumPrefix') }}{{ item.self_upper_limit }}
              </li>
            </ul>
          </div>
          <n-button @click="openEdit(idx)" style="margin-right: 20px">{{
            t('tasks.edit')
          }}</n-button>
          <n-button type="error" @click="settings.splice(idx, 1)">{{ t('tasks.delete') }}</n-button>
        </div>
      </n-list-item>
    </n-list>
  </n-form-item>
  <n-modal
    style="width: 500px"
    v-model:show="showSettingModal"
    preset="dialog"
    :title="t('tasks.addOperatorSettings')"
    :mask-closable="false"
    @update:show="workshop_setting_close"
  >
    <div style="display: flex; align-items: center; gap: 12px">
      <span style="font-size: 12px; white-space: nowrap">{{ t('tasks.operatorColon') }}</span>
      <n-select
        filterable
        :options="operators"
        class="operator-select"
        v-model:value="tempSetting.operator"
        :filter="filterOperatorOption"
        :render-label="render_op_label"
        :render-option="render_op_option"
      />
      <span style="font-size: 12px; white-space: nowrap">{{ t('tasks.enabledColon') }}</span>
      <n-switch v-model:value="tempSetting.enabled" />
    </div>
    <n-form :model="tempSetting">
      <n-dynamic-input v-model:value="tempSetting.items" :on-create="createNewItem">
        <template #default="{ value }">
          <div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">{{
                t('tasks.craftingMaterialsColon')
              }}</span>
              <n-select
                multiple
                tag
                :options="materialOptions"
                v-model:value="value.item_names"
                :filter="(p, o) => pinyin_match(o.value, p) || pinyin_match(o.label, p)"
                filterable
              />
              <help-text>
                <div>{{ t('tasks.craftingWhitelist') }}</div>
              </help-text>
            </div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">{{
                t('tasks.craftingMaximumColon')
              }}</span>
              <mower-input-number
                v-model:value="value.self_upper_limit"
                :min="0"
                :placeholder="t('tasks.productMaximum')"
              />
              <help-text>
                <div>{{ t('tasks.stopAtProductLimit') }}</div>
              </help-text>
            </div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">{{
                t('tasks.ingredientMinimumColon')
              }}</span>
              <mower-input-number
                v-model:value="value.children_lower_limit"
                :min="0"
                :placeholder="t('tasks.ingredientMinimum')"
              />
              <help-text>
                <div>{{ t('tasks.ingredientStockHelp') }}</div>
              </help-text>
            </div>
          </div>
        </template>
      </n-dynamic-input>
    </n-form>
  </n-modal>
</template>
