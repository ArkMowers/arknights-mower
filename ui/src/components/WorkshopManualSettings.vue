<script setup>
import { computed, inject, ref } from 'vue'
import { pinyin_match } from '@/utils/common'
import { render_op_option, render_op_label } from '@/utils/op_select'

const props = defineProps({ operators: Array, item_list: Array, migrationWarning: String })
const settings = defineModel({ type: Array, default: () => [] })
const mobile = inject('mobile', ref(false))

const materialGroups = computed(() => {
  const gold = { type: 'group', key: 'gold', label: '金材料', children: [] }
  const purple = { type: 'group', key: 'purple', label: '紫材料', children: [] }
  const other = { type: 'group', key: 'other', label: '其他材料', children: [] }
  for (const option of props.item_list ?? []) {
    if (option.tab === '精英材料' && option.apCost >= 8) gold.children.push(option)
    else if (option.tab === '精英材料' && option.apCost === 4) purple.children.push(option)
    else other.children.push(option)
  }
  return [gold, purple, other].filter((group) => group.children.length)
})
const quickSelectGroups = computed(() => materialGroups.value.filter(({ key }) => key !== 'other'))

function selectMaterialGroup(item, group) {
  item.item_names = [...new Set([...item.item_names, ...group.children.map(({ value }) => value)])]
}

function createMaterialOption(name) {
  const option = { label: name, value: name }
  return props.item_list?.some(({ value }) => value === name)
    ? { ...option, type: 'ignored' }
    : option
}

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
    style="width: min(560px, calc(100vw - 32px))"
    v-model:show="showSettingModal"
    preset="dialog"
    :title="editingIndex === null ? '新增干员设置' : '编辑干员设置'"
    positive-text="保存"
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
        :render-option="render_op_option"
      />
      <span style="font-size: 12px; white-space: nowrap">启用：</span>
      <n-switch v-model:value="tempSetting.enabled" />
    </div>
    <n-form :model="tempSetting" class="workshop-settings-form">
      <n-dynamic-input v-model:value="tempSetting.items" :on-create="createNewItem">
        <template #default="{ value }">
          <div class="workshop-material-setting">
            <div class="workshop-material-picker">
              <div class="workshop-material-toolbar">
                <div class="workshop-material-label">
                  <span>合成材料</span>
                  <help-text>加工站干员合成材料的白名单</help-text>
                </div>
                <div v-if="quickSelectGroups.length" class="workshop-material-actions">
                  <n-button
                    v-for="group in quickSelectGroups"
                    :key="group.key"
                    size="small"
                    secondary
                    :disabled="
                      group.children.every(({ value: name }) => value.item_names.includes(name))
                    "
                    @click="selectMaterialGroup(value, group)"
                  >
                    <span
                      :class="['workshop-material-dot', `workshop-material-dot--${group.key}`]"
                      aria-hidden="true"
                    />
                    全选{{ group.label }}
                  </n-button>
                </div>
              </div>
              <n-select
                multiple
                tag
                :on-create="createMaterialOption"
                :options="materialGroups"
                :max-tag-count="mobile ? 3 : 8"
                v-model:value="value.item_names"
                :filter="(p, o) => pinyin_match(o.label, p)"
                filterable
                placeholder="选择合成材料"
                :input-props="{ 'aria-label': '合成材料' }"
              />
            </div>
            <div class="workshop-material-limits">
              <div class="workshop-material-picker">
                <div class="workshop-material-label">
                  <span>成品库存上限</span>
                  <help-text>成品库存达到此数量后停止合成</help-text>
                </div>
                <mower-input-number
                  v-model:value="value.self_upper_limit"
                  :min="0"
                  :input-props="{ 'aria-label': '成品库存上限' }"
                />
              </div>
              <div class="workshop-material-picker">
                <div class="workshop-material-label">
                  <span>子材料库存下限</span>
                  <help-text>为每种子材料保留的最低库存，合成时不会消耗到低于此数量</help-text>
                </div>
                <mower-input-number
                  v-model:value="value.children_lower_limit"
                  :min="0"
                  :input-props="{ 'aria-label': '子材料库存下限' }"
                />
              </div>
            </div>
          </div>
        </template>
      </n-dynamic-input>
    </n-form>
  </n-modal>
</template>

<style scoped>
.workshop-settings-form {
  margin-block-start: 14px;
}

.workshop-material-setting {
  display: grid;
  flex: 1;
  gap: 10px;
  min-width: 0;
}

.workshop-material-picker {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.workshop-material-toolbar,
.workshop-material-label,
.workshop-material-actions {
  display: flex;
  align-items: center;
}

.workshop-material-toolbar {
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 12px;
}

.workshop-material-actions {
  flex-wrap: wrap;
  gap: 8px;
}

.workshop-material-actions .n-button {
  padding-inline: 8px;
}

.workshop-material-limits {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 132px), 1fr));
  gap: 10px 12px;
}

.workshop-material-dot {
  width: 8px;
  height: 8px;
  margin-inline-end: 6px;
  border-radius: 50%;
}

.workshop-material-dot--gold {
  background: #d4a017;
}

.workshop-material-dot--purple {
  background: #9568cf;
}
</style>
