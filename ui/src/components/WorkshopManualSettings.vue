<script setup>
import { ref } from 'vue'
import { pinyin_match } from '@/utils/common'
import { render_op_label } from '@/utils/op_select'

defineProps({ operators: Array, item_list: Array, migrationWarning: String })
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
      <span>无缝合成材料设置</span>
      <help-text>自动专精备料期间，修改会保存并在备料结束后生效。</help-text>
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
      >新增设置</n-button
    >
    <n-list bordered>
      <n-list-item v-for="(setting, idx) in settings" :key="idx">
        <div class="flex justify-between w-full">
          <div>
            <strong>干员:</strong> {{ setting.operator }}, 启用: {{ setting.enabled }}<br />
            <ul>
              <li v-for="(item, i) in setting.items" :key="i">
                {{ item.item_names }} - 子项下限: {{ item.children_lower_limit }}, 自身上限:
                {{ item.self_upper_limit }}
              </li>
            </ul>
          </div>
          <n-button @click="openEdit(idx)" style="margin-right: 20px">编辑</n-button>
          <n-button type="error" @click="settings.splice(idx, 1)">删除</n-button>
        </div>
      </n-list-item>
    </n-list>
  </n-form-item>
  <n-modal
    style="width: 500px"
    v-model:show="showSettingModal"
    preset="dialog"
    title="新增干员设置"
    :mask-closable="false"
    @update:show="workshop_setting_close"
  >
    <div style="display: flex; align-items: center; gap: 12px">
      <span style="font-size: 12px; white-space: nowrap">干员：</span>
      <n-select
        filterable
        :options="operators"
        class="operator-select"
        v-model:value="tempSetting.operator"
        :filter="(p, o) => pinyin_match(o.label, p)"
        :render-label="render_op_label"
      />
      <span style="font-size: 12px; white-space: nowrap">启用：</span>
      <n-switch v-model:value="tempSetting.enabled" />
    </div>
    <n-form :model="tempSetting">
      <n-dynamic-input v-model:value="tempSetting.items" :on-create="createNewItem">
        <template #default="{ value }">
          <div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">合成材料： </span>
              <n-select
                multiple
                tag
                :options="item_list"
                v-model:value="value.item_names"
                :filter="(p, o) => pinyin_match(o.label, p)"
                filterable
              />
              <help-text>
                <div>加工站干员合成材料的白名单</div>
              </help-text>
            </div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">合成数量上限： </span>
              <mower-input-number
                v-model:value="value.self_upper_limit"
                :min="0"
                placeholder="自身上限"
              />
              <help-text>
                <div>设置占位，可能没用</div>
              </help-text>
            </div>
            <div style="display: flex; flex-direction: row; align-self: center">
              <span style="white-space: nowrap; margin-top: 5px">子材料数量下限： </span>
              <mower-input-number
                v-model:value="value.children_lower_limit"
                :min="0"
                placeholder="子项下限"
              />
              <help-text>
                <div>设置占位，可能没用</div>
              </help-text>
            </div>
          </div>
        </template>
      </n-dynamic-input>
    </n-form>
  </n-modal>
</template>
