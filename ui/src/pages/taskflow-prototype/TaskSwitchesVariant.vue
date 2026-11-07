<script setup>
// PROTOTYPE：左侧选择任务或分类，右侧编辑参数；仅操作本页示例，不连接配置存储。
import { computed, reactive, ref, watch } from 'vue'
import ArrowResetIcon from '@vicons/fluent/es/ArrowReset20Regular'
import InfoIcon from '@vicons/fluent/es/Info20Regular'
import {
  categoryFieldBindings,
  connectionDefinition,
  createTaskSwitchesState,
  taskDefinitions,
  taskGroups
} from './taskSwitchesData'
import TaskChecklistNavigation from '@/task-workflow/TaskChecklistNavigation.vue'

defineOptions({ name: 'TaskSwitchesPrototype' })
defineProps({ state: { type: Object, default: null } })

const draft = reactive(createTaskSwitchesState())
const selectedId = ref('recruit')
const navigationKey = ref(0)
const selectedTask = computed(() => taskDefinitions.find((task) => task.id === selectedId.value))
const selectedCategory = computed(() =>
  taskGroups.find((group) => selectedId.value === `category:${group.id}`)
)
const selected = computed(() => {
  if (selectedId.value === 'connection') return connectionDefinition
  if (selectedCategory.value) {
    return {
      title: selectedCategory.value.label,
      description: selectedCategory.value.description
    }
  }
  return selectedTask.value
})
const configurable = taskDefinitions.filter((task) => task.mode !== 'automatic')
const categoryTaskFields = new Set(
  Object.values(categoryFieldBindings)
    .flat()
    .filter((binding) => binding.source === 'task')
    .map((binding) => `${binding.taskId}:${binding.key}`)
)
const sharedFields = {
  dailyGap: { type: 'number', min: 0.1, max: 24, step: 0.5, unit: '小时' }
}
watch(
  () => draft.connection.preset_id,
  (presetId) => {
    if (presetId === 'manual.physical' && draft.shared.idleAction === 'close') {
      draft.shared.idleAction = 'home'
    }
  }
)
const taskStatuses = computed(() =>
  Object.fromEntries(taskDefinitions.map((task) => [task.id, isEnabled(task)]))
)
const fields = computed(() => {
  let definitions
  if (selectedId.value === 'connection') {
    definitions = connectionDefinition.fields.map((field) => ({
      ...field,
      source: field.source || 'connection'
    }))
  } else if (selectedCategory.value) {
    definitions = categoryFieldBindings[selectedCategory.value.id].map((binding) => {
      const original =
        binding.source === 'shared'
          ? sharedFields[binding.key]
          : taskDefinitions
              .find((task) => task.id === binding.taskId)
              .fields.find((field) => field.key === binding.key)
      return { ...original, ...binding }
    })
  } else {
    definitions = selectedTask.value.fields
      .filter((field) => !categoryTaskFields.has(`${selectedId.value}:${field.key}`))
      .map((field) => ({ ...field, source: 'task', taskId: selectedId.value }))
  }
  return definitions.filter((field) => {
    if (!field.visibleWhen) return true
    return fieldState(field)[field.visibleWhen.key] === field.visibleWhen.value
  })
})

function fieldState(field) {
  if (field.source === 'shared') return draft.shared
  if (field.source === 'connection') return draft.connection
  return draft.values[field.taskId]
}
function fieldOptions(field) {
  if (field.key !== 'idleAction') return field.options
  return field.options.map((option) => ({
    ...option,
    disabled: option.value === 'close' && draft.connection.preset_id === 'manual.physical'
  }))
}

function isEnabled(task) {
  if (task.id === 'reward')
    return task.fields.some((field) => draft.values.reward[field.key] === true)
  if (task.id === 'workshop') return draft.values.workshop['workshop_settings.0.enabled'] === true
  if (task.id === 'drone') return Boolean(draft.values.drone.drone_room)
  return task.mode === 'automatic' || draft.enabled[task.id]
}
function openTask(id) {
  selectedId.value = id
}
function engine(task) {
  const runner = task.fields.find(
    (field) =>
      field.options?.some((option) => option.value === 'mower') &&
      field.options?.some((option) => option.value === 'maa')
  )
  if (runner) return draft.values[task.id][runner.key] === 'maa' ? 'MAA' : 'Mower'
  if (task.id === 'long') {
    const mode = draft.values.long.maa_long_task_type
    return ['rogue', 'sss', 'rcl'].includes(mode) ? 'MAA' : 'Mower'
  }
  return task.engine
}
function setAll(value) {
  for (const task of configurable) draft.enabled[task.id] = value
}
function toggleTask(id, value) {
  if (configurable.some((task) => task.id === id)) draft.enabled[id] = value
}
function reset() {
  Object.assign(draft, createTaskSwitchesState())
  navigationKey.value += 1
}
</script>

<template>
  <section class="switch-prototype" aria-label="任务开关配置原型">
    <header class="prototype-heading">
      <div>
        <h1>任务配置</h1>
      </div>
      <div class="prototype-heading-actions">
        <span class="prototype-label" title="修改仅保留在本页，不写入实际配置"><i />交互原型</span>
        <button class="text-button reset-button" type="button" @click="reset">
          <n-icon :component="ArrowResetIcon" :size="16" />还原示例
        </button>
      </div>
    </header>

    <div class="switch-workspace">
      <TaskChecklistNavigation
        :key="navigationKey"
        connection-id="connection"
        :tasks="taskDefinitions"
        :groups="taskGroups"
        :selected-id="selectedId"
        :statuses="taskStatuses"
        @select="openTask"
        @toggle="toggleTask"
        @set-all="setAll"
      />

      <div class="configuration-column">
        <section class="task-inspector" :aria-label="`${selected.title}设置`">
          <header class="inspector-heading">
            <div>
              <h2>{{ selected.title }}</h2>
            </div>
            <div class="inspector-actions">
              <n-popover trigger="click" style="max-width: 320px">
                <template #trigger>
                  <button
                    class="inspector-help"
                    type="button"
                    :aria-label="`${selected.title}说明`"
                  >
                    <n-icon :component="InfoIcon" :size="18" />
                  </button>
                </template>
                <div class="inspector-help-content">
                  <p>{{ selected.description }}</p>
                  <p v-if="selected.condition">{{ selected.condition }}</p>
                  <p v-if="selected.effect">{{ selected.effect }}</p>
                  <p v-if="selectedTask && engine(selectedTask) === 'MAA'">
                    需要先配置 MAA 核心与连接方式。
                  </p>
                </div>
              </n-popover>
              <span v-if="selectedTask?.mode === 'automatic'" class="automatic-status">
                {{ isEnabled(selectedTask) ? selectedTask.automaticLabel || '自动执行' : '未启用' }}
              </span>
              <n-switch
                v-else-if="selectedTask"
                v-model:value="draft.enabled[selectedId]"
                :aria-label="`启用${selected.title}`"
              />
            </div>
          </header>

          <div class="inspector-content">
            <div v-if="fields.length" class="settings-fields">
              <div v-for="field in fields" :key="field.key" class="setting-field">
                <div class="field-label">
                  <label :for="`prototype-${selectedId}-${field.key}`">{{ field.label }}</label>
                  <n-popover v-if="field.help" trigger="click" style="max-width: 280px">
                    <template #trigger
                      ><button
                        class="field-help-button"
                        type="button"
                        :aria-label="`${field.label}说明`"
                      >
                        ?
                      </button></template
                    >
                    {{ field.help }}
                  </n-popover>
                </div>
                <div class="setting-control">
                  <n-select
                    v-if="field.type === 'select'"
                    v-model:value="fieldState(field)[field.key]"
                    :options="fieldOptions(field)"
                    :consistent-menu-width="false"
                    :input-props="{
                      id: `prototype-${selectedId}-${field.key}`,
                      'aria-label': field.label
                    }"
                    :aria-label="field.label"
                  />
                  <n-input-number
                    v-else-if="field.type === 'number'"
                    v-model:value="fieldState(field)[field.key]"
                    :min="field.min"
                    :max="field.max"
                    :step="field.step || 1"
                    :input-props="{
                      id: `prototype-${selectedId}-${field.key}`,
                      'aria-label': field.label
                    }"
                  >
                    <template v-if="field.unit" #suffix>{{ field.unit }}</template>
                  </n-input-number>
                  <n-switch
                    v-else-if="field.type === 'switch'"
                    v-model:value="fieldState(field)[field.key]"
                    :aria-label="field.label"
                  />
                  <input
                    v-else-if="field.type === 'time'"
                    :id="`prototype-${selectedId}-${field.key}`"
                    v-model="fieldState(field)[field.key]"
                    type="time"
                    class="prototype-time"
                    :aria-label="field.label"
                  />
                  <n-input
                    v-else
                    v-model:value="fieldState(field)[field.key]"
                    :input-props="{
                      id: `prototype-${selectedId}-${field.key}`,
                      'aria-label': field.label
                    }"
                  />
                </div>
              </div>
            </div>

            <div v-else class="simple-task-note">无需额外设置</div>

            <nav v-if="selected.links?.length" class="related-links" aria-label="相关设置">
              <router-link v-for="link in selected.links" :key="link.to" :to="link.to"
                >{{ link.label }} ›</router-link
              >
            </nav>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.switch-prototype {
  --prototype-accent: var(--mower-primary, #168658);
  box-sizing: border-box;
  width: 100%;
  max-width: 1320px;
  margin: 0 auto;
  padding: 24px;
  color: var(--mower-text);
  font-size: 14px;
  line-height: 1.6;
}
.prototype-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 22px;
}
.prototype-heading h1 {
  font-size: 25px;
  letter-spacing: -0.7px;
  line-height: 1.3;
  margin: 0;
  font-weight: 650;
}
.prototype-heading-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.prototype-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--mower-text-muted);
}
.prototype-label i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c0914a;
  display: inline-block;
  flex: none;
}
.text-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 0;
  background: none;
  padding: 4px 0;
  color: var(--prototype-accent);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.reset-button {
  color: var(--mower-text-muted);
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--prototype-accent);
  outline-offset: 3px;
}
.text-button:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.switch-workspace {
  display: grid;
  grid-template-columns: 310px minmax(0, 1fr);
  align-items: start;
  gap: 22px;
}
.configuration-column {
  min-width: 0;
}
.task-inspector {
  border: 1px solid var(--mower-border);
  border-radius: 10px;
  background: var(--mower-surface);
  overflow: hidden;
}
.inspector-heading {
  padding: 20px 26px 18px;
  border-bottom: 1px solid var(--mower-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.inspector-heading h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 21px;
  font-weight: 600;
  line-height: 1.5;
  margin: 0;
}
.inspector-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}
.inspector-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--mower-text-muted);
  cursor: pointer;
}
.inspector-help-content p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.7;
}
.inspector-help-content p:last-child {
  margin-bottom: 0;
}
.automatic-status {
  font-size: 12px;
  color: var(--mower-text-muted);
  white-space: nowrap;
}
.inspector-content {
  padding: 22px 26px;
}
.settings-fields {
  display: grid;
  gap: 17px;
}
.setting-field {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.field-label {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 35px;
  font-size: 13px;
}
.field-help-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--mower-control-surface);
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.setting-control {
  min-width: 0;
}
.setting-control > .n-select,
.setting-control > .n-input-number {
  max-width: 290px;
}
.setting-control > .n-switch {
  margin-top: 7px;
}
.prototype-time {
  box-sizing: border-box;
  height: 35px;
  width: 100%;
  max-width: 290px;
  padding: 0 12px;
  border: 1px solid var(--mower-border);
  border-radius: 6px;
  background: var(--mower-surface);
  color: var(--mower-text);
  font: inherit;
  color-scheme: light dark;
}
.related-links {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 18px;
  font-size: 12px;
}
.related-links a {
  color: var(--prototype-accent);
  text-decoration: none;
}
.related-links a:hover {
  text-decoration: underline;
}
.simple-task-note {
  padding: 20px 0;
  color: var(--mower-text-muted);
  font-size: 13px;
}
@container main-content (max-width: 1000px) {
  .switch-prototype {
    padding: 20px 16px;
  }
  .switch-workspace {
    gap: 16px;
  }
  .inspector-heading {
    padding: 20px;
    align-items: flex-start;
  }
  .inspector-content {
    padding: 20px 20px 22px;
  }
  .setting-field {
    grid-template-columns: 110px minmax(0, 1fr);
    gap: 12px;
  }
}
@container main-content (max-width: 760px) {
  .prototype-heading {
    gap: 12px;
    align-items: flex-start;
  }
  .prototype-heading-actions {
    flex-direction: column;
    align-items: flex-end;
    gap: 5px;
  }
  .switch-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}
@container main-content (max-width: 440px) {
  .switch-prototype {
    padding-inline: 12px;
  }
  .setting-field {
    grid-template-columns: minmax(0, 1fr);
    gap: 7px;
  }
  .inspector-heading h2 {
    font-size: 19px;
  }
}
</style>
