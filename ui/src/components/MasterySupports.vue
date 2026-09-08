<template>
  <n-modal
    :show="show"
    @update:show="$emit('update:show', $event)"
    preset="card"
    title="专精协助方案"
    style="width: min(660px, 95vw); max-height: 90vh"
    content-style="overflow-y: auto; min-height: 0"
    :mask-closable="!saving"
    :closable="!saving"
    :close-on-esc="!saving"
  >
    <n-space vertical :size="16">
      <n-text strong>{{ name }}</n-text>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-alert v-if="!editable" type="info"
        >当前没有可编辑的阶段。训练中可以修改后续尚未开始的阶段。</n-alert
      >
      <n-text depth="3">
        中枢加成：{{
          plan?.support_plan?.central_bonus || 0
        }}%。自动方案排除非训练室排班干员及动态加速干员。
      </n-text>
      <n-spin :show="loading">
        <n-space vertical :size="12">
          <n-card
            v-for="stage in stages"
            :key="stage.level"
            size="small"
            :title="`专${stage.level}`"
          >
            <n-space vertical>
              <n-text v-if="stage.level <= editableAfter" depth="3"
                >该阶段已开始或已完成，协助者已锁定。</n-text
              >
              <n-text depth="3">{{ stage.manual ? '自选协助者' : '自动推荐' }}</n-text>
              <n-text
                v-if="
                  plan.support_runtime?.level === stage.level &&
                  plan.support_runtime.working_operator
                "
                depth="3"
              >
                实际协助者：{{ plan.support_runtime.working_operator }}
              </n-text>
              <label :for="`support-${stage.level}`">开始协助者</label>
              <n-select
                :id="`support-${stage.level}`"
                v-model:value="stage.operator"
                :options="options"
                filterable
                :disabled="stage.level <= editableAfter || saving"
              />
              <template v-if="stage.level < plan.target_level">
                <label :for="`reducer-${stage.level}`">后段接班者（可留空）</label>
                <n-select
                  :id="`reducer-${stage.level}`"
                  v-model:value="stage.swap_target"
                  :options="options"
                  filterable
                  clearable
                  :disabled="stage.level <= editableAfter || saving"
                  placeholder="不换人"
                />
              </template>
              <n-text v-if="stage.activate_with" depth="3"
                >本级开训前需保留 {{ stage.activate_with }}，触发减半后再换人。</n-text
              >
            </n-space>
          </n-card>
          <n-empty v-if="!stages.length" description="此旧计划没有自动协助方案，请重新添加计划" />
        </n-space>
      </n-spin>
      <n-text depth="3"
        >自选不要求专精速度加成；保存时检查排班冲突。没有减半技能的接班者不会产生减半效果。</n-text
      >
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button @click="$emit('update:show', false)" :disabled="saving">关闭</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!editable || !stages.length || loading"
          @click="save"
          >保存协助者</n-button
        >
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { supportEditableAfter } from '@/utils/masterySupport'
import { NAlert, NButton, NCard, NEmpty, NModal, NSelect, NSpace, NSpin, NText } from 'naive-ui'

const props = defineProps({ show: Boolean, plan: Object, name: String })
const emit = defineEmits(['update:show', 'saved'])
const stages = ref([])
const operators = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const editableAfter = computed(() => supportEditableAfter(props.plan))
const editable = computed(() => stages.value.some((s) => s.level > editableAfter.value))
const options = computed(() =>
  operators.value
    .filter((o) => o.name !== props.name)
    .map((o) => ({
      value: o.name,
      label: o.blocked.length ? `${o.name}（非训练室排班占用）` : o.name,
      disabled: o.blocked.length > 0
    }))
)

watch(
  () => props.show,
  async (show) => {
    if (!show) return
    const planId = props.plan?.id
    stages.value = (props.plan?.support_plan?.stages || []).map((s) => ({ ...s }))
    operators.value = []
    loading.value = true
    error.value = ''
    try {
      const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/supports`)
      if (props.show && props.plan?.id === planId) operators.value = data.operators
    } catch (e) {
      error.value = e.response?.data?.error || e.message
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

async function save() {
  saving.value = true
  error.value = ''
  try {
    await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/supports`, {
      id: props.plan.id,
      stages: stages.value.map(({ level, operator, swap_target }) => ({
        level,
        operator,
        swap_target
      }))
    })
    emit('saved')
    emit('update:show', false)
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    saving.value = false
  }
}
</script>
