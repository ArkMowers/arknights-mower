<script setup>
// PROTOTYPE 变体 F：工程图纸。外框是基建循环，回程线沿底边返回；闲时序列是框中嵌套的虚线框，
// 进入门槛画成框上的闸口。设备与运行节奏写在图纸右下角的标题栏里，点任何部件在右侧检视。
import { computed, ref } from 'vue'
import FieldEditor from './FieldEditor.vue'
import { insertTask, removeTask, moveTask, nextRun, fmt, MAA_MARGIN, LONG_MARGIN } from './data'
import { useFlow, idleLabel, pauseLabel, cadenceLabel, sectionTitle } from './shared'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state
const { of, spareOf, gate, reorderable } = useFlow(s)

const sel = ref('device')
const pick = (key) => (sel.value = sel.value === key ? null : key)
const task = computed(() => s.tasks.find((entry) => entry.id === sel.value))
function removeSelectedTask() {
  if (!task.value) return
  removeTask(s, task.value.id)
  sel.value = null
}

const stages = computed(() => [
  { id: 'daily', no: '1', title: '日常', rule: '顺序固定', tasks: of('daily') },
  {
    id: 'maa',
    no: '2',
    title: 'MAA 日常',
    rule: `每 ${s.globals.maaGap} 小时 · 前 ${MAA_MARGIN}停`,
    key: 'gap',
    tasks: of('maa')
  },
  {
    id: 'long',
    no: '3',
    title: '长任务',
    rule: `${pauseLabel(s)} 停运 · 前 ${LONG_MARGIN}停`,
    key: 'pause',
    tasks: of('long')
  }
])

const inspectorTitle = computed(() => {
  if (task.value) return task.value.name
  return {
    device: '设备',
    pace: '运行节奏',
    idle: '空闲动作',
    gap: 'MAA 间隔',
    pause: '长任务停运时段'
  }[sel.value]
})
</script>

<template>
  <section class="sc">
    <div class="sc-sheet">
      <!-- 图纸 -->
      <div class="sc-drawing">
        <div class="sc-frame" aria-label="基建循环">
          <span class="sc-tag">循环 A · 一直运行</span>

          <div class="sc-lane">
            <div class="sc-lane-head">
              <b>基建队列</b>
              <span>按时间排序，跑单优先</span>
            </div>
            <div class="sc-parts">
              <button
                v-for="t in of('base')"
                :key="t.id"
                type="button"
                class="sc-part"
                :class="{ 'is-sel': sel === t.id, 'is-off': !t.enabled }"
                @click="pick(t.id)"
              >
                <span class="sc-part-name">{{ t.name }}</span>
                <span class="sc-part-meta">{{ t.enabled ? nextRun(s, t.id) : '停用' }}</span>
              </button>
              <button
                v-for="t in spareOf('base')"
                :key="t.id"
                type="button"
                class="sc-part sc-part--spare"
                @click="(insertTask(s, t.id, 'base'), (sel = t.id))"
              >
                + {{ t.name }}
              </button>
            </div>
          </div>

          <!-- 闸口：进入闲时序列的条件 -->
          <div class="sc-gate" :class="{ 'is-open': gate?.open }">
            <span class="sc-gate-mark" aria-hidden="true" />
            <span>
              距下一项基建任务 <b>≥ 9 分钟</b> 时进入
              <em>现在 {{ gate?.gap }} 分钟 · {{ gate?.open ? '可进入' : '不进入' }}</em>
            </span>
          </div>

          <div class="sc-frame sc-frame--inner" aria-label="闲时序列">
            <span class="sc-tag">序列 B · 闲时</span>
            <div class="sc-stages">
              <div v-for="st in stages" :key="st.id" class="sc-stage">
                <component
                  :is="st.key ? 'button' : 'div'"
                  :type="st.key ? 'button' : undefined"
                  class="sc-stage-head"
                  :class="{ 'is-sel': st.key && sel === st.key, 'is-btn': st.key }"
                  @click="st.key && pick(st.key)"
                >
                  <span class="sc-no">{{ st.no }}</span>
                  <b>{{ st.title }}</b>
                  <span class="sc-rule">{{ st.rule }}</span>
                </component>
                <ol class="sc-list">
                  <li v-for="t in st.tasks" :key="t.id">
                    <button
                      type="button"
                      class="sc-item"
                      :class="{ 'is-sel': sel === t.id, 'is-off': !t.enabled }"
                      @click="pick(t.id)"
                    >
                      {{ t.name }}
                    </button>
                  </li>
                  <li v-for="t in spareOf(st.id)" :key="t.id">
                    <button
                      type="button"
                      class="sc-item sc-item--spare"
                      @click="(insertTask(s, t.id, st.id), (sel = t.id))"
                    >
                      + {{ t.name }}
                    </button>
                  </li>
                </ol>
              </div>

              <div class="sc-stage sc-stage--end">
                <button
                  type="button"
                  class="sc-stage-head is-btn"
                  :class="{ 'is-sel': sel === 'idle' }"
                  @click="pick('idle')"
                >
                  <span class="sc-no">4</span>
                  <b>空闲</b>
                  <span class="sc-rule">{{ idleLabel(s) }}</span>
                </button>
                <div class="sc-stage-head">
                  <span class="sc-no">5</span>
                  <b>休眠</b>
                  <span class="sc-rule">到 {{ gate?.at }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 回程线：沿外框底边回到基建队列 -->
          <div class="sc-return" aria-hidden="true">
            <span>回到基建队列</span>
          </div>
        </div>

        <!-- 标题栏：全局设置 -->
        <div class="sc-titleblock">
          <button
            type="button"
            class="sc-tb-cell sc-tb-wide"
            :class="{ 'is-sel': sel === 'device' }"
            @click="pick('device')"
          >
            <span class="sc-tb-k">设备</span>
            <span class="sc-tb-v">{{ s.globals.device.name }}</span>
            <span class="sc-tb-s">{{ s.globals.device.adb }} · {{ s.globals.device.status }}</span>
          </button>
          <button
            type="button"
            class="sc-tb-cell"
            :class="{ 'is-sel': sel === 'device' }"
            @click="pick('device')"
          >
            <span class="sc-tb-k">截图 / 触控</span>
            <span class="sc-tb-v">{{ s.globals.device.fields[0].value }}</span>
            <span class="sc-tb-s">{{ s.globals.device.fields[1].value }}</span>
          </button>
          <button
            v-for="f in s.globals.pace.fields.slice(0, 3)"
            :key="f.key"
            type="button"
            class="sc-tb-cell"
            :class="{ 'is-sel': sel === 'pace' }"
            @click="pick('pace')"
          >
            <span class="sc-tb-k">{{ f.label }}</span>
            <span class="sc-tb-v"
              >{{ f.value }}<small>{{ f.unit }}</small></span
            >
          </button>
          <div class="sc-tb-cell">
            <span class="sc-tb-k">图名</span>
            <span class="sc-tb-v">Mower 调度</span>
            <span class="sc-tb-s">{{ fmt(s.now) }}</span>
          </div>
        </div>
      </div>

      <!-- 检视栏 -->
      <aside class="sc-inspector" :class="{ 'is-empty': !sel }">
        <template v-if="sel">
          <header>
            <span class="sc-tb-k">{{ task ? sectionTitle[task.section] : '全局' }}</span>
            <h2>{{ inspectorTitle }}</h2>
            <p v-if="task">
              {{ cadenceLabel(s, task) }} · 下次 {{ task.enabled ? nextRun(s, task.id) : '—' }}
            </p>
          </header>

          <template v-if="task">
            <label class="sc-enable">
              <span>启用</span>
              <n-switch v-model:value="task.enabled" size="small" />
            </label>
            <FieldEditor :fields="task.fields" />
            <footer>
              <template v-if="reorderable(task.section)">
                <n-button size="small" secondary @click="moveTask(s, task.id, -1)">前移</n-button>
                <n-button size="small" secondary @click="moveTask(s, task.id, 1)">后移</n-button>
              </template>
              <span v-else class="sc-note">{{
                task.section === 'base'
                  ? '基建队列按时间排序，不能调整顺序'
                  : '日常顺序由 Mower 固定'
              }}</span>
              <n-button size="small" quaternary type="error" @click="removeSelectedTask"
                >移出</n-button
              >
            </footer>
          </template>
          <FieldEditor v-else-if="sel === 'device'" :fields="s.globals.device.fields" />
          <FieldEditor v-else-if="sel === 'pace'" :fields="s.globals.pace.fields" />
          <n-radio-group
            v-else-if="sel === 'idle'"
            v-model:value="s.globals.idle.value"
            class="sc-radios"
          >
            <n-radio v-for="[v, label] in s.globals.idle.options" :key="v" :value="v">{{
              label
            }}</n-radio>
          </n-radio-group>
          <label v-else-if="sel === 'gap'" class="sc-enable">
            <span>间隔</span>
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
          <div v-else-if="sel === 'pause'" class="sc-pause">
            <label v-for="(label, i) in ['开始', '结束']" :key="label" class="sc-enable">
              <span>{{ label }}</span>
              <n-input-number
                v-model:value="s.globals.longPause[i]"
                size="small"
                :min="0"
                :max="24"
                style="width: 140px"
              >
                <template #suffix>时</template>
              </n-input-number>
            </label>
          </div>
        </template>
        <p v-else class="sc-note">点图纸上的任意部件查看和修改设置。</p>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.sc {
  /* 亮色主题下 --mower-text 为空，原型里先兜底 */
  --tx: var(--mower-text, var(--n-text-color, rgb(31, 34, 37)));
  --tx-m: var(--mower-text-muted, color-mix(in srgb, var(--tx) 60%, transparent));
  --sc-ink: var(--tx);
  --sc-line: color-mix(in srgb, var(--tx) 70%, transparent);
  --sc-hair: color-mix(in srgb, var(--tx) 16%, transparent);
  --sc-grid: color-mix(in srgb, var(--tx) 5%, transparent);
  --sc-mono: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  --sc-accent: var(--mower-primary);
  padding: 32px 32px 110px;
  color: var(--sc-ink);
}
.sc-sheet {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 28px;
  max-width: 1360px;
  margin: 0 auto;
}
.sc-drawing {
  position: relative;
  padding: 26px;
  border: 1px solid var(--sc-hair);
  background-color: var(--mower-surface);
  background-image:
    linear-gradient(var(--sc-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--sc-grid) 1px, transparent 1px);
  background-size: 20px 20px;
}
.sc-frame {
  position: relative;
  padding: 30px 24px 56px;
  border: 1.5px solid var(--sc-line);
}
.sc-frame--inner {
  margin-top: 0;
  padding: 30px 20px 20px;
  border: 1.5px dashed var(--sc-line);
  background: color-mix(in srgb, var(--mower-surface) 80%, transparent);
}
.sc-tag {
  position: absolute;
  top: -9px;
  left: 16px;
  padding: 0 8px;
  font: 11px/18px var(--sc-mono);
  letter-spacing: 0.04em;
  background: var(--mower-surface);
}
.sc-lane-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 14px;
}
.sc-lane-head span,
.sc-rule {
  font-size: 12px;
  color: var(--tx-m);
}
.sc-parts {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}
.sc-part {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 96px;
  margin: 0 -1px -1px 0;
  padding: 8px 12px;
  border: 1px solid var(--sc-line);
  font: inherit;
  color: inherit;
  text-align: left;
  background: var(--mower-surface);
  cursor: pointer;
  transition: background 160ms cubic-bezier(0.32, 0.72, 0, 1);
}
.sc-part-name {
  font-size: 13px;
  font-weight: 500;
}
.sc-part-meta {
  font: 11px var(--sc-mono);
  color: var(--tx-m);
}
.sc-part--spare,
.sc-item--spare {
  justify-content: center;
  border-style: dashed;
  color: var(--tx-m);
  background: transparent;
}
.sc-part:hover,
.sc-item:hover,
.sc-stage-head.is-btn:hover,
.sc-tb-cell:is(button):hover {
  background: var(--mower-control-hover);
}
.is-sel {
  position: relative;
  z-index: 1;
  outline: 2px solid var(--sc-accent);
  outline-offset: -1px;
}
.is-off {
  color: var(--tx-m);
}
.is-off .sc-part-name,
.sc-item.is-off {
  text-decoration: line-through;
}

/* 闸口：从基建队列下落进入闲时序列 */
.sc-gate {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 72px;
  margin-bottom: 10px;
  padding-left: 40px;
  font-size: 13px;
}
.sc-gate-mark {
  position: relative;
  align-self: stretch;
  width: 0;
  border-left: 1.5px solid var(--sc-line);
}
.sc-gate-mark::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -8px;
  width: 13px;
  height: 13px;
  border: 1.5px solid var(--sc-line);
  background: var(--mower-surface);
  transform: translateY(-50%) rotate(45deg);
}
.sc-gate.is-open .sc-gate-mark::before {
  background: var(--sc-accent);
  border-color: var(--sc-accent);
}
.sc-gate-mark::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: -5px;
  border: 4px solid transparent;
  border-top: 6px solid var(--sc-line);
}
.sc-gate em {
  margin-left: 10px;
  font: normal 11px var(--sc-mono);
  color: var(--tx-m);
}
.sc-stages {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) minmax(0, 0.8fr);
  border-left: 1px solid var(--sc-hair);
}
.sc-stage {
  min-width: 0;
  border-right: 1px solid var(--sc-hair);
}
.sc-stage-head {
  display: grid;
  grid-template-columns: 22px 1fr;
  gap: 2px 6px;
  width: 100%;
  padding: 8px 12px 10px;
  border: 0;
  border-bottom: 1px solid var(--sc-hair);
  font: inherit;
  font-size: 13.5px;
  color: inherit;
  text-align: left;
  background: none;
}
.sc-stage-head.is-btn {
  cursor: pointer;
}
.sc-stage-head .sc-rule {
  grid-column: 2;
}
.sc-no {
  grid-row: span 2;
  font: 11px/20px var(--sc-mono);
  color: var(--tx-m);
}
.sc-list {
  margin: 0;
  padding: 6px 0 10px;
  list-style: none;
  counter-reset: step;
}
.sc-item {
  display: block;
  width: 100%;
  padding: 4px 12px 4px 40px;
  border: 0;
  font: inherit;
  font-size: 13px;
  color: inherit;
  text-align: left;
  background: none;
  cursor: pointer;
  counter-increment: step;
  position: relative;
}
.sc-item:not(.sc-item--spare)::before {
  content: counter(step, decimal-leading-zero);
  position: absolute;
  left: 12px;
  font: 11px/20px var(--sc-mono);
  color: var(--tx-m);
}
.sc-item--spare {
  border: 0;
}
.sc-stage--end .sc-stage-head:last-child {
  border-bottom: 0;
}

/* 回程线 */
.sc-return {
  position: absolute;
  left: -1px;
  right: 24px;
  bottom: 18px;
  height: 0;
  border-top: 1.5px solid var(--sc-line);
}
.sc-return::before {
  content: '';
  position: absolute;
  top: -5px;
  left: 0;
  border: 4px solid transparent;
  border-right: 7px solid var(--sc-line);
  transform: translateX(-10px);
}
.sc-return span {
  position: absolute;
  right: 0;
  top: -9px;
  padding: 0 8px;
  font: 11px/18px var(--sc-mono);
  background: var(--mower-surface);
}

/* 标题栏 */
.sc-titleblock {
  display: grid;
  grid-template-columns: 2fr repeat(5, 1fr);
  margin-top: 22px;
  border: 1.5px solid var(--sc-line);
}
.sc-tb-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 8px 12px;
  border: 0;
  border-right: 1px solid var(--sc-hair);
  font: inherit;
  color: inherit;
  text-align: left;
  background: var(--mower-surface);
}
button.sc-tb-cell {
  cursor: pointer;
}
.sc-tb-cell:last-child {
  border-right: 0;
}
.sc-tb-k {
  font: 10.5px var(--sc-mono);
  letter-spacing: 0.04em;
  color: var(--tx-m);
}
.sc-tb-v {
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 500;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.sc-tb-v small {
  margin-left: 2px;
  font-size: 11px;
  font-weight: 400;
  color: var(--tx-m);
}
.sc-tb-s {
  font: 11px var(--sc-mono);
  color: var(--tx-m);
}

/* 检视栏 */
.sc-inspector {
  position: sticky;
  top: 24px;
  align-self: start;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border-top: 2px solid var(--sc-ink);
}
.sc-inspector h2 {
  margin: 4px 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.sc-inspector header p,
.sc-note {
  margin: 0;
  font-size: 12px;
  color: var(--tx-m);
}
.sc-inspector footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--sc-hair);
}
.sc-inspector footer > :last-child {
  margin-left: auto;
}
.sc-enable {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}
.sc-radios {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sc-pause {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
@media (max-width: 1100px) {
  .sc-sheet {
    grid-template-columns: 1fr;
  }
  .sc-inspector {
    position: static;
  }
  .sc-stages {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .sc-titleblock {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
