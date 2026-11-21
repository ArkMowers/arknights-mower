<script setup>
import { computed, ref, watch } from 'vue'
import { MAX_MOOD_VIEW_OPERATORS } from '@/utils/mood_observation'

const props = defineProps({
  show: { type: Boolean, default: false },
  view: { type: Object, default: null },
  catalog: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:show', 'save', 'remove'])
const name = ref('')
const selected = ref([])
const error = ref('')
const options = computed(() =>
  props.catalog.map((item) => ({
    label:
      item.name +
      (item.sampleCount === 0
        ? ' · 暂无记录'
        : item.sampleCount != null
          ? ' · ' + item.sampleCount + ' 条记录'
          : ''),
    value: item.name
  }))
)
watch(
  () => [props.show, props.view],
  () => {
    if (!props.show) return
    name.value = props.view?.name ?? ''
    selected.value = [...(props.view?.operators ?? [])]
    error.value = ''
  },
  { immediate: true }
)

function submit() {
  const title = name.value.trim()
  if (!title || title.length > 30) {
    error.value = '请输入 1～30 字的观察表名称'
    return
  }
  if (selected.value.length < 1 || selected.value.length > MAX_MOOD_VIEW_OPERATORS) {
    error.value = '每张观察表请选择 1～16 位干员'
    return
  }
  emit('save', { id: props.view?.id, name: title, operators: [...selected.value] })
}

function close() {
  emit('update:show', false)
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="view ? '编辑自定义观察表' : '新建自定义观察表'"
    style="width: min(94vw, 550px)"
    @update:show="emit('update:show', $event)"
  >
    <div class="observation-fields">
      <label>
        <span>观察表名称</span>
        <n-input v-model:value="name" maxlength="30" placeholder="例如：重点干员" />
      </label>
      <div class="observation-field">
        <span>选择干员（可跨任意原始编组）</span>
        <n-select
          v-model:value="selected"
          :options="options"
          multiple
          filterable
          tag
          clearable
          :max-tag-count="3"
          :max="MAX_MOOD_VIEW_OPERATORS"
          placeholder="搜索已有历史的干员；也可输入无记录的名字"
        />
      </div>
      <p class="observation-help">
        可搜索历史记录中的任意干员。没有记录时会明确提示；不会更改排班、采样或实际调度。
      </p>
      <p v-if="error" role="alert" class="observation-error">{{ error }}</p>
      <div class="observation-actions">
        <n-button v-if="view" type="error" secondary @click="emit('remove', view.id)"
          >删除观察表</n-button
        >
        <n-button @click="close">取消</n-button>
        <n-button type="primary" @click="submit">保存观察表</n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.observation-fields {
  display: flex;
  flex-direction: column;
  gap: 15px;
}
.observation-fields label,
.observation-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.observation-help {
  margin: 0;
  font-size: 12px;
  opacity: 0.75;
}
.observation-error {
  color: #d14545;
  font-size: 12px;
  margin: 0;
}
.observation-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.observation-actions :first-child:nth-last-child(3) {
  margin-right: auto;
}
</style>
