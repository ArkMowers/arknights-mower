<script setup>
// PROTOTYPE 变体 E：程序清单。把调度循环排成一段带缩进轨的“代码”，
// 嵌套 = 缩进，条件 = 关键字行，点任意一行在原地展开它的设置。
import { computed, ref } from 'vue'
import FieldEditor from './FieldEditor.vue'
import { insertTask, removeTask, moveTask, nextRun, fmt, MAA_MARGIN, LONG_MARGIN } from './data'
import { useFlow, idleLabel, pauseLabel, cadenceLabel } from './shared'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state
const { of, spareOf, gate, reorderable } = useFlow(s)

const open = ref(null)
const inserting = ref(null)
const toggle = (key) => (open.value = open.value === key ? null : key)

const pauseFields = computed(() => [
  {
    key: 'a',
    label: '停运开始',
    type: 'number',
    unit: '时',
    min: 0,
    max: 23,
    value: s.globals.longPause[0]
  },
  {
    key: 'b',
    label: '停运结束',
    type: 'number',
    unit: '时',
    min: 0,
    max: 24,
    value: s.globals.longPause[1]
  }
])
function setPause(i, v) {
  s.globals.longPause[i] = v ?? 0
}

// 清单行：depth 决定缩进轨数，kind 决定排版
const lines = computed(() => {
  const out = []
  const push = (line) => out.push({ ...line, no: out.length + 1 })
  push({ kind: 'global', key: 'device', depth: 0, kw: '设备', depthRails: [] })
  push({ kind: 'global', key: 'pace', depth: 0, kw: '节奏', depthRails: [] })
  push({ kind: 'blank', depth: 0 })
  push({ kind: 'loop', depth: 0, kw: '循环', text: '一直运行' })
  push({
    kind: 'head',
    section: 'base',
    depth: 1,
    kw: '基建队列',
    text: '按任务时间排序，跑单优先'
  })
  for (const t of of('base')) push({ kind: 'task', task: t, depth: 2 })
  if (spareOf('base').length) push({ kind: 'insert', section: 'base', depth: 2 })
  push({ kind: 'blank', depth: 1 })
  push({ kind: 'gate', depth: 1, kw: '当', text: '距下一项基建任务 ≥ 9 分钟' })
  push({ kind: 'head', section: 'daily', depth: 2, kw: '日常', text: '顺序固定' })
  for (const t of of('daily')) push({ kind: 'task', task: t, depth: 3 })
  if (spareOf('daily').length) push({ kind: 'insert', section: 'daily', depth: 3 })
  push({ kind: 'cond', key: 'gap', section: 'maa', depth: 2, kw: '每', text: 'MAA 日常' })
  for (const t of of('maa')) push({ kind: 'task', task: t, depth: 3 })
  if (spareOf('maa').length) push({ kind: 'insert', section: 'maa', depth: 3 })
  push({ kind: 'cond', key: 'pause', section: 'long', depth: 2, kw: '停运时段外', text: '长任务' })
  for (const t of of('long')) push({ kind: 'task', task: t, depth: 3 })
  if (spareOf('long').length) push({ kind: 'insert', section: 'long', depth: 3 })
  push({ kind: 'global', key: 'idle', depth: 2, kw: '空闲' })
  push({ kind: 'sleep', depth: 2, kw: '休眠' })
  push({ kind: 'end', depth: 1 })
  push({ kind: 'end', depth: 0 })
  return out
})
</script>

<template>
  <section class="ls">
    <header class="ls-head">
      <h1>任务配置</h1>
      <p>
        现在 <b>{{ fmt(s.now) }}</b
        >，下一项基建任务是 {{ gate?.name }}（{{ gate?.at }}），还有 {{ gate?.gap }} 分钟，
        <span :class="gate?.open ? 'ls-ok' : 'ls-wait'">{{
          gate?.open ? '闲时序列可以进入' : '闲时序列不进入'
        }}</span
        >。
      </p>
    </header>

    <ol class="ls-code" aria-label="调度清单">
      <li
        v-for="line in lines"
        :key="line.no"
        class="ls-line"
        :class="[
          `ls-line--${line.kind}`,
          line.task && !line.task.enabled && 'is-off',
          line.task && open === line.task.id && 'is-open',
          line.key && open === line.key && 'is-open'
        ]"
      >
        <span class="ls-no" aria-hidden="true">{{ line.no }}</span>
        <span class="ls-rails" aria-hidden="true">
          <i v-for="d in line.depth" :key="d" :class="`ls-rail ls-rail--${d}`" />
        </span>

        <div class="ls-body">
          <!-- 全局设置：设备 / 节奏 / 空闲 -->
          <template v-if="line.kind === 'global'">
            <button class="ls-row" type="button" @click="toggle(line.key)">
              <span class="ls-kw">{{ line.kw }}</span>
              <template v-if="line.key === 'device'">
                <span class="ls-val">{{ s.globals.device.name }}</span>
                <span class="ls-dim">{{ s.globals.device.adb }}</span>
                <span class="ls-dot" />{{ s.globals.device.status }}
                <span class="ls-dim"
                  >· {{ s.globals.device.fields[0].value }} 截图 ·
                  {{ s.globals.device.fields[1].value }} 触控</span
                >
              </template>
              <template v-else-if="line.key === 'pace'">
                <span v-for="f in s.globals.pace.fields" :key="f.key" class="ls-pair">
                  <span class="ls-dim">{{ f.label }}</span> <span class="ls-val">{{ f.value }}</span
                  ><span class="ls-dim">{{ f.unit }}</span>
                </span>
              </template>
              <template v-else>
                <span class="ls-val">{{ idleLabel(s) }}</span>
                <span class="ls-dim">做完以上任务后</span>
              </template>
            </button>
            <div v-if="open === line.key" class="ls-detail">
              <FieldEditor v-if="line.key === 'device'" :fields="s.globals.device.fields" />
              <FieldEditor v-else-if="line.key === 'pace'" :fields="s.globals.pace.fields" />
              <n-radio-group v-else v-model:value="s.globals.idle.value" size="small">
                <n-radio-button v-for="[v, label] in s.globals.idle.options" :key="v" :value="v">{{
                  label
                }}</n-radio-button>
              </n-radio-group>
            </div>
          </template>

          <div v-else-if="line.kind === 'loop'" class="ls-row ls-static">
            <span class="ls-kw ls-kw--loop">{{ line.kw }}</span>
            <span class="ls-dim">{{ line.text }}</span>
          </div>

          <div v-else-if="line.kind === 'gate'" class="ls-row ls-static">
            <span class="ls-kw">{{ line.kw }}</span>
            <span class="ls-val">{{ line.text }}</span>
            <span class="ls-dim">· 现在 {{ gate?.gap }} 分钟</span>
          </div>

          <div v-else-if="line.kind === 'head'" class="ls-row ls-static">
            <span class="ls-kw">{{ line.kw }}</span>
            <span class="ls-dim">{{ line.text }}</span>
          </div>

          <!-- 带参数的条件行：MAA 间隔 / 停运时段 -->
          <template v-else-if="line.kind === 'cond'">
            <button class="ls-row" type="button" @click="toggle(line.key)">
              <template v-if="line.key === 'gap'">
                <span class="ls-kw">每</span>
                <span class="ls-token">{{ s.globals.maaGap }} 小时</span>
                <span class="ls-val">{{ line.text }}</span>
                <span class="ls-dim">· 基建任务前 {{ MAA_MARGIN }}停下</span>
              </template>
              <template v-else>
                <span class="ls-kw">在</span>
                <span class="ls-token">{{ pauseLabel(s) }}</span>
                <span class="ls-kw">之外</span>
                <span class="ls-val">{{ line.text }}</span>
                <span class="ls-dim">· 基建任务前 {{ LONG_MARGIN }}停下</span>
              </template>
            </button>
            <div v-if="open === line.key" class="ls-detail">
              <label v-if="line.key === 'gap'" class="ls-inline">
                MAA 间隔
                <n-input-number
                  v-model:value="s.globals.maaGap"
                  size="small"
                  :min="1"
                  :max="24"
                  style="width: 140px"
                >
                  <template #suffix>小时</template>
                </n-input-number>
              </label>
              <div v-else class="ls-inline">
                <label v-for="(f, i) in pauseFields" :key="f.key" class="ls-inline">
                  {{ f.label }}
                  <n-input-number
                    :value="f.value"
                    size="small"
                    :min="f.min"
                    :max="f.max"
                    style="width: 120px"
                    @update:value="(v) => setPause(i, v)"
                  >
                    <template #suffix>时</template>
                  </n-input-number>
                </label>
              </div>
            </div>
          </template>

          <template v-else-if="line.kind === 'task'">
            <div class="ls-row ls-task">
              <n-checkbox
                v-model:checked="line.task.enabled"
                size="small"
                :aria-label="`启用${line.task.name}`"
              />
              <button class="ls-name" type="button" @click="toggle(line.task.id)">
                {{ line.task.name }}
              </button>
              <span class="ls-dim">{{ cadenceLabel(s, line.task) }}</span>
              <span class="ls-next">{{
                line.task.enabled ? nextRun(s, line.task.id) : '停用'
              }}</span>
            </div>
            <div v-if="open === line.task.id" class="ls-detail">
              <FieldEditor :fields="line.task.fields" />
              <div class="ls-actions">
                <template v-if="reorderable(line.task.section)">
                  <n-button size="tiny" quaternary @click="moveTask(s, line.task.id, -1)"
                    >上移</n-button
                  >
                  <n-button size="tiny" quaternary @click="moveTask(s, line.task.id, 1)"
                    >下移</n-button
                  >
                </template>
                <span v-else class="ls-dim">{{
                  line.task.section === 'base' ? '基建队列按时间排序' : '日常顺序固定'
                }}</span>
                <n-button size="tiny" quaternary type="error" @click="removeTask(s, line.task.id)"
                  >移出循环</n-button
                >
              </div>
            </div>
          </template>

          <template v-else-if="line.kind === 'insert'">
            <template v-if="spareOf(line.section).length">
              <button
                v-if="inserting !== line.section"
                class="ls-row ls-add"
                type="button"
                @click="inserting = line.section"
              >
                + 插入任务
              </button>
              <div v-else class="ls-row ls-chips">
                <button
                  v-for="t in spareOf(line.section)"
                  :key="t.id"
                  class="ls-chip"
                  type="button"
                  @click="(insertTask(s, t.id, line.section), (open = t.id), (inserting = null))"
                >
                  + {{ t.name }}
                </button>
                <button class="ls-chip ls-chip--ghost" type="button" @click="inserting = null">
                  取消
                </button>
              </div>
            </template>
          </template>

          <div v-else-if="line.kind === 'sleep'" class="ls-row ls-static">
            <span class="ls-kw">{{ line.kw }}</span>
            <span class="ls-dim">直到下一项基建任务</span>
            <span class="ls-val">{{ gate?.at }}</span>
          </div>

          <div v-else-if="line.kind === 'end'" class="ls-row ls-static ls-end">
            {{ line.depth === 0 ? '回到基建队列' : '闲时序列结束' }}
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.ls {
  /* 亮色主题下 --mower-text 为空，原型里先兜底 */
  --tx: var(--mower-text, var(--n-text-color, rgb(31, 34, 37)));
  --tx-m: var(--mower-text-muted, color-mix(in srgb, var(--tx) 60%, transparent));
  --ls-mono: 'JetBrains Mono', 'Cascadia Code', 'SFMono-Regular', Consolas, monospace;
  --ls-rule: color-mix(in srgb, var(--tx) 12%, transparent);
  --ls-rail: color-mix(in srgb, var(--tx) 18%, transparent);
  max-width: 980px;
  margin: 0 auto;
  padding: 40px 32px 120px;
  color: var(--tx);
}
.ls-head h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.ls-head p {
  margin: 0 0 28px;
  font-size: 13px;
  color: var(--tx-m);
}
.ls-head b {
  font-family: var(--ls-mono);
  font-weight: 500;
  color: var(--tx);
}
.ls-ok {
  color: var(--mower-success-text, var(--mower-primary));
}
.ls-wait {
  color: var(--mower-warning-text, var(--mower-warning));
}
.ls-code {
  margin: 0;
  padding: 14px 0;
  list-style: none;
  border-top: 1px solid var(--ls-rule);
  border-bottom: 1px solid var(--ls-rule);
  font-size: 13.5px;
  line-height: 1.5;
}
.ls-line {
  display: grid;
  grid-template-columns: 40px auto 1fr;
  align-items: start;
}
.ls-no {
  padding: 5px 14px 0 0;
  font: 11px/22px var(--ls-mono);
  text-align: right;
  color: color-mix(in srgb, var(--tx) 30%, transparent);
  user-select: none;
}
.ls-rails {
  display: flex;
  align-self: stretch;
}
.ls-rail {
  width: 26px;
  border-left: 1px solid var(--ls-rail);
}
/* 第一层轨是“循环”，第二层是“闲时序列”：加深以示嵌套 */
.ls-rail--1 {
  border-left: 2px solid color-mix(in srgb, var(--mower-primary) 55%, transparent);
}
.ls-rail--2 {
  border-left: 1px solid color-mix(in srgb, var(--tx) 32%, transparent);
}
.ls-rail--3 {
  border-left: 1px solid var(--ls-rail);
}
.ls-line--gate .ls-rails .ls-rail:last-child,
.ls-line--loop + .ls-line .ls-rail:last-child {
  border-top-left-radius: 6px;
}
.ls-body {
  min-width: 0;
  padding: 2px 0;
}
.ls-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  width: 100%;
  min-height: 26px;
  padding: 2px 10px;
  border: 0;
  border-radius: 6px;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
}
button.ls-row {
  cursor: pointer;
}
button.ls-row:hover,
.ls-task:hover {
  background: var(--mower-control-hover);
}
.is-open > .ls-body > .ls-row {
  background: color-mix(in srgb, var(--mower-primary) 9%, transparent);
}
.ls-kw {
  font-family: var(--ls-mono);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--mower-primary);
}
.ls-kw--loop {
  font-size: 13px;
}
.ls-val {
  font-weight: 500;
}
.ls-dim {
  color: var(--tx-m);
}
.ls-pair {
  white-space: nowrap;
}
.ls-pair .ls-val {
  font-family: var(--ls-mono);
}
.ls-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: -4px;
  border-radius: 50%;
  background: var(--mower-success, #16a34a);
  transform: translateY(-2px);
}
.ls-token {
  padding: 0 6px;
  border-bottom: 1px dashed color-mix(in srgb, var(--mower-primary) 60%, transparent);
  font-family: var(--ls-mono);
  font-weight: 500;
}
.ls-task {
  align-items: center;
}
.ls-name {
  padding: 0;
  border: 0;
  font: inherit;
  font-weight: 500;
  color: inherit;
  background: none;
  cursor: pointer;
}
.ls-name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.ls-next {
  margin-left: auto;
  font: 12px var(--ls-mono);
  color: var(--tx-m);
}
.is-off .ls-name {
  color: var(--tx-m);
  text-decoration: line-through;
}
.ls-detail {
  max-width: 520px;
  margin: 6px 10px 12px;
  padding: 14px 16px;
  border-left: 2px solid var(--mower-primary);
  background: color-mix(in srgb, var(--tx) 3.5%, transparent);
  animation: ls-in 220ms cubic-bezier(0.32, 0.72, 0, 1);
}
@keyframes ls-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
}
.ls-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--ls-rule);
  font-size: 12px;
}
.ls-actions .n-button:last-child {
  margin-left: auto;
}
.ls-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.ls-inline + .ls-inline {
  margin-left: 18px;
}
.ls-add {
  font-size: 12.5px;
  color: var(--tx-m);
  cursor: pointer;
}
.ls-add:hover {
  color: var(--mower-primary);
}
.ls-chips {
  gap: 6px;
}
.ls-chip {
  padding: 1px 10px;
  border: 1px dashed color-mix(in srgb, var(--mower-primary) 55%, transparent);
  border-radius: 999px;
  font: inherit;
  font-size: 12.5px;
  color: var(--mower-primary);
  background: none;
  cursor: pointer;
}
.ls-chip--ghost {
  border-color: var(--ls-rule);
  color: var(--tx-m);
}
.ls-line--blank .ls-body {
  min-height: 10px;
}
.ls-end {
  font: 12px var(--ls-mono);
  color: color-mix(in srgb, var(--tx) 40%, transparent);
}
@media (prefers-reduced-motion: reduce) {
  .ls-detail {
    animation: none;
  }
}
@media (max-width: 720px) {
  .ls {
    padding: 24px 12px 100px;
  }
  .ls-rail {
    width: 14px;
  }
  .ls-no {
    display: none;
  }
  .ls-line {
    grid-template-columns: auto 1fr;
  }
}
</style>
