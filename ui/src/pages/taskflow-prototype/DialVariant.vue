<script setup>
// PROTOTYPE 变体 B：同心表盘。一圈是一天（4:00 刷新在正上方），由内到外是基建、日常、MAA、长任务。
// 每次发车是圈上的一个刻点；长任务是一段弧；空白扇区是停运时段。表芯是设备，表冠是节奏。
import { computed, ref } from 'vue'
import { sections, insertTask, removeTask, simulateDay, nextRun, fmt } from './data'
import { cadenceLabel } from './shared'
import FieldEditor from './FieldEditor.vue'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state

const SIZE = 640
const C = SIZE / 2
const order = ['base', 'daily', 'maa', 'long']
const radius = { base: 120, daily: 170, maa: 215, long: 258 }
// 4:00 在正上方
const angle = (hour) => ((hour - 4) / 24) * 360 - 90
const rad = (a) => (a * Math.PI) / 180
const at = (hour, r) => ({
  x: C + r * Math.cos(rad(angle(hour))),
  y: C + r * Math.sin(rad(angle(hour)))
})
function arc(h0, h1, r) {
  const a = at(h0, r)
  const b = at(h1, r)
  const large = (h1 - h0 + 24) % 24 > 12 ? 1 : 0
  return `M ${a.x} ${a.y} A ${r} ${r} 0 ${large} 1 ${b.x} ${b.y}`
}

const runs = computed(() => simulateDay(s))
const focus = ref(null) // 悬停或选中时只高亮这个任务的刻点
const lit = computed(() => focus.value ?? s.selected)
const marks = computed(() =>
  runs.value.map((run, i) => ({
    ...run,
    key: `${run.id}-${i}`,
    ...at(run.hour, radius[run.section])
  }))
)
const hand = computed(() => at(s.now, radius.long + 26))
const pauseArc = computed(() => arc(s.globals.longPause[0], s.globals.longPause[1], radius.long))
const hours = Array.from({ length: 24 }, (_, i) => i)

const selectedTask = computed(() => s.tasks.find((t) => t.id === s.selected))
const byRing = computed(() =>
  Object.fromEntries(order.map((k) => [k, s.tasks.filter((t) => t.section === k)]))
)
const adding = ref(null)
function add(id) {
  insertTask(s, id, adding.value, byRing.value[adding.value].length)
  adding.value = null
}
function pick(id) {
  s.selected = s.selected === id ? null : id
}
const idleLabel = computed(
  () => s.globals.idle.options.find(([v]) => v === s.globals.idle.value)[1]
)
</script>
<template>
  <div class="dial-page">
    <!-- 左：图例兼任务目录，按圈分组；悬停任务名会在表盘上点亮它的所有刻点 -->
    <nav class="dial-index" aria-label="任务目录">
      <section v-for="key in order" :key="key" class="dial-group">
        <h3 :style="{ '--c': sections[key].color }">
          <span>{{ sections[key].title.replace('线', '') }}</span>
          <small>{{ sections[key].note }}</small>
        </h3>
        <button
          v-for="task in byRing[key]"
          :key="task.id"
          type="button"
          class="dial-task"
          :class="{ 'is-on': s.selected === task.id, 'is-off': !task.enabled }"
          :style="{ '--c': sections[key].color }"
          @mouseenter="focus = task.id"
          @mouseleave="focus = null"
          @focus="focus = task.id"
          @blur="focus = null"
          @click="pick(task.id)"
        >
          <i></i>{{ task.name }}
          <time>{{ task.enabled ? nextRun(s, task.id) : '停' }}</time>
        </button>
        <div v-if="s.spare.some((t) => t.section === key)" class="dial-add">
          <button type="button" class="dial-add-btn" @click="adding = adding === key ? null : key">
            + 加到这一圈
          </button>
          <div v-if="adding === key" class="dial-add-menu" role="menu">
            <button
              v-for="t in s.spare.filter((t) => t.section === key)"
              :key="t.id"
              type="button"
              role="menuitem"
              @click="add(t.id)"
            >
              {{ t.name }}
            </button>
          </div>
        </div>
      </section>
    </nav>

    <!-- 中：表盘 -->
    <div class="dial-face" :class="{ 'is-lit': lit }">
      <svg :viewBox="`0 0 ${SIZE} ${SIZE}`" role="img" aria-label="一天内各任务的发车时刻">
        <defs>
          <radialGradient id="dial-bg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="var(--dial-core)" />
            <stop offset="100%" stop-color="var(--dial-rim)" />
          </radialGradient>
        </defs>
        <circle :cx="C" :cy="C" :r="C - 6" fill="url(#dial-bg)" />
        <g class="dial-hours">
          <g v-for="h in hours" :key="h">
            <line
              :x1="at(h, C - 18).x"
              :y1="at(h, C - 18).y"
              :x2="at(h, C - (h % 6 === 4 ? 34 : 26)).x"
              :y2="at(h, C - (h % 6 === 4 ? 34 : 26)).y"
            />
            <text v-if="h % 3 === 1" :x="at(h, C - 46).x" :y="at(h, C - 46).y">{{ h }}</text>
          </g>
        </g>
        <circle
          v-for="key in order"
          :key="key"
          :cx="C"
          :cy="C"
          :r="radius[key]"
          class="dial-ring"
          :stroke="sections[key].color"
        />
        <path :d="pauseArc" class="dial-pause" />
        <template v-for="m in marks" :key="m.key">
          <path
            v-if="m.span"
            :d="arc(m.hour, m.hour + m.span, radius.long)"
            class="dial-span"
            :class="{ 'is-dim': lit && lit !== m.id }"
            :stroke="sections[m.section].color"
            @click="pick(m.id)"
          />
          <circle
            v-else
            :cx="m.x"
            :cy="m.y"
            :r="lit === m.id ? 9 : 6"
            class="dial-mark"
            :class="{ 'is-dim': lit && lit !== m.id }"
            :fill="sections[m.section].color"
            @click="pick(m.id)"
          >
            <title>{{ s.tasks.find((t) => t.id === m.id)?.name }} {{ fmt(m.hour) }}</title>
          </circle>
        </template>
        <line :x1="C" :y1="C" :x2="hand.x" :y2="hand.y" class="dial-hand" />
        <circle :cx="hand.x" :cy="hand.y" r="5" class="dial-hand-tip" />
        <text :x="C" :y="28" class="dial-refresh">4:00 刷新</text>
      </svg>

      <!-- 表芯：设备 -->
      <button
        type="button"
        class="dial-core"
        :class="{ 'is-on': s.selected === 'device' }"
        @click="pick('device')"
      >
        <small>{{ s.globals.device.status }}</small>
        <b>{{ s.globals.device.name.split(' · ')[0] }}</b>
        <span>{{ fmt(s.now) }}</span>
      </button>
      <!-- 表冠：节奏；底座：空闲时 -->
      <button
        type="button"
        class="dial-crown"
        :class="{ 'is-on': s.selected === 'pace' }"
        @click="pick('pace')"
      >
        <span>{{ s.globals.pace.fields[0].value }}</span
        ><small>ms</small>
      </button>
      <button
        type="button"
        class="dial-foot"
        :class="{ 'is-on': s.selected === 'idle' }"
        @click="pick('idle')"
      >
        空闲时 · {{ idleLabel }}
      </button>
    </div>

    <!-- 右：表盘背面的「机芯」，选中什么就调什么 -->
    <aside class="dial-panel" aria-live="polite">
      <template v-if="selectedTask">
        <p class="dial-kicker" :style="{ '--c': sections[selectedTask.section].color }">
          {{ sections[selectedTask.section].title }}
        </p>
        <h2>{{ selectedTask.name }}</h2>
        <p class="dial-when">
          {{ cadenceLabel(s, selectedTask) }} · 今天
          {{ runs.filter((r) => r.id === selectedTask.id).length }} 次 · 下一次
          {{ selectedTask.enabled ? nextRun(s, selectedTask.id) : '—' }}
        </p>
        <label class="dial-row"
          ><span>启用</span><n-switch v-model:value="selectedTask.enabled"
        /></label>
        <FieldEditor :fields="selectedTask.fields" />
        <n-button size="small" type="error" ghost @click="removeTask(s, selectedTask.id)"
          >从表盘移除</n-button
        >
      </template>
      <template v-else-if="s.selected === 'device'">
        <p class="dial-kicker" style="--c: #111">表芯</p>
        <h2>{{ s.globals.device.name }}</h2>
        <p class="dial-when">
          {{ s.globals.device.adb }} · {{ s.globals.device.cpu }} · {{ s.globals.device.ram }}
        </p>
        <n-space
          ><n-button size="small" type="primary">测试连接</n-button
          ><n-button size="small">检测实例</n-button></n-space
        >
        <FieldEditor :fields="s.globals.device.fields" />
      </template>
      <template v-else-if="s.selected === 'pace'">
        <p class="dial-kicker" style="--c: #111">表冠</p>
        <h2>节奏</h2>
        <FieldEditor :fields="s.globals.pace.fields" />
      </template>
      <template v-else-if="s.selected === 'idle'">
        <p class="dial-kicker" style="--c: #64748b">底座</p>
        <h2>空闲时</h2>
        <n-radio-group v-model:value="s.globals.idle.value">
          <n-space vertical>
            <n-radio v-for="[v, l] in s.globals.idle.options" :key="v" :value="v" :label="l" />
          </n-space>
        </n-radio-group>
      </template>
      <template v-else>
        <p class="dial-kicker" style="--c: #64748b">表盘</p>
        <h2>一天怎么过</h2>
        <p class="dial-when">
          点圈上的刻点或左侧任务来调整；悬停任务名会点亮它当天的所有发车时刻。
        </p>
        <label class="dial-row">
          <span>MAA 间隔</span>
          <n-input-number
            v-model:value="s.globals.maaGap"
            size="small"
            :min="1"
            :max="24"
            style="width: 120px"
          >
            <template #suffix>小时</template>
          </n-input-number>
        </label>
        <label class="dial-row">
          <span>长任务停运</span>
          <span class="dial-range">
            <n-input-number
              v-model:value="s.globals.longPause[0]"
              size="small"
              :min="0"
              :max="23"
              style="width: 72px"
            />
            –
            <n-input-number
              v-model:value="s.globals.longPause[1]"
              size="small"
              :min="0"
              :max="23"
              style="width: 72px"
            />
          </span>
        </label>
        <n-slider v-model:value="s.now" :min="0" :max="23.99" :step="0.05" :format-tooltip="fmt" />
        <small class="dial-when">拖动以模拟当前时刻</small>
      </template>
    </aside>
  </div>
</template>
<style scoped>
.dial-page {
  --ink: var(--mower-text);
  --muted: var(--mower-text-muted);
  --paper: var(--mower-surface, #fff);
  --dial-core: #fbfaf7;
  --dial-rim: #eeebe4;
  display: grid;
  grid-template-columns: 190px minmax(360px, 1fr) 290px;
  gap: 28px;
  align-items: start;
  padding: 24px 28px 90px;
  box-sizing: border-box;
  color: var(--ink);
}
html[data-mower-theme='dark'] .dial-page {
  --dial-core: #26262b;
  --dial-rim: #17171a;
}
.dial-index {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.dial-group h3 {
  display: flex;
  flex-direction: column;
  margin: 0 0 6px;
  padding-left: 10px;
  border-left: 4px solid var(--c);
  font-size: 15px;
}
.dial-group h3 small {
  font-size: 11px;
  font-weight: 400;
  color: var(--muted);
}
.dial-task {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  text-align: left;
  color: var(--ink);
  background: none;
  cursor: pointer;
}
.dial-task i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c);
}
.dial-task time {
  margin-left: auto;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.dial-task:hover,
.dial-task:focus-visible {
  outline: none;
  background: var(--mower-control-hover);
}
.dial-task.is-on {
  background: color-mix(in srgb, var(--c) 14%, transparent);
}
.dial-task.is-off {
  color: var(--muted);
  text-decoration: line-through;
}
.dial-task.is-off i {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--c);
}
.dial-add {
  position: relative;
}
.dial-add-btn {
  padding: 4px 8px;
  border: 0;
  font: inherit;
  font-size: 12px;
  color: var(--muted);
  background: none;
  cursor: pointer;
}
.dial-add-btn:hover {
  color: var(--mower-primary);
}
.dial-add-menu {
  position: absolute;
  z-index: 5;
  left: 0;
  display: flex;
  flex-direction: column;
  min-width: 140px;
  padding: 4px;
  border-radius: 8px;
  background: var(--paper);
  box-shadow:
    0 10px 30px -10px rgba(0, 0, 0, 0.35),
    0 0 0 1px var(--mower-border);
}
.dial-add-menu button {
  padding: 6px 8px;
  border: 0;
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  text-align: left;
  color: var(--ink);
  background: none;
  cursor: pointer;
}
.dial-add-menu button:hover {
  background: var(--mower-control-hover);
}
.dial-face {
  position: relative;
  width: 100%;
  max-width: 640px;
  justify-self: center;
}
.dial-face svg {
  display: block;
  width: 100%;
  height: auto;
  filter: drop-shadow(0 24px 40px rgba(0, 0, 0, 0.12));
}
.dial-hours line {
  stroke: var(--muted);
  stroke-width: 2;
  stroke-linecap: round;
}
.dial-hours text {
  font-size: 16px;
  font-weight: 600;
  text-anchor: middle;
  dominant-baseline: middle;
  fill: var(--muted);
  font-variant-numeric: tabular-nums;
}
.dial-ring {
  fill: none;
  stroke-width: 2;
  opacity: 0.35;
}
.dial-pause {
  fill: none;
  stroke: var(--muted);
  stroke-width: 18;
  stroke-dasharray: 2 6;
  opacity: 0.35;
}
.dial-span {
  fill: none;
  stroke-width: 14;
  stroke-linecap: round;
  opacity: 0.85;
  cursor: pointer;
}
.dial-mark {
  stroke: var(--paper);
  stroke-width: 2.5;
  cursor: pointer;
  transition:
    r 0.15s ease,
    opacity 0.15s ease;
}
.is-dim {
  opacity: 0.12;
}
.dial-hand {
  stroke: var(--ink);
  stroke-width: 2;
}
.dial-hand-tip {
  fill: #ef4444;
}
.dial-refresh {
  font-size: 12px;
  text-anchor: middle;
  fill: var(--muted);
}
.dial-core,
.dial-crown,
.dial-foot {
  position: absolute;
  border: 0;
  font: inherit;
  cursor: pointer;
}
.dial-core {
  left: 50%;
  top: 50%;
  width: 26%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: 50%;
  color: #fff;
  background: radial-gradient(circle at 35% 30%, #3a3a40, #101012);
  box-shadow:
    0 0 0 6px var(--paper),
    0 10px 24px rgba(0, 0, 0, 0.3);
}
.dial-core small {
  font-size: 11px;
  color: #4ade80;
}
.dial-core b {
  font-size: 15px;
}
.dial-core span {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.dial-crown {
  top: 50%;
  right: -22px;
  transform: translateY(-50%);
  width: 46px;
  height: 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--ink);
  background: repeating-linear-gradient(180deg, var(--dial-rim) 0 3px, var(--dial-core) 3px 6px);
  box-shadow: 0 0 0 1px var(--mower-border);
}
.dial-crown span {
  font-weight: 700;
}
.dial-crown small {
  font-size: 10px;
  color: var(--muted);
}
.dial-foot {
  left: 50%;
  bottom: -14px;
  transform: translateX(-50%);
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13px;
  color: #fff;
  background: #475569;
}
.dial-core.is-on,
.dial-crown.is-on,
.dial-foot.is-on {
  outline: 3px solid color-mix(in srgb, var(--mower-primary) 55%, transparent);
  outline-offset: 3px;
}
.dial-panel {
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
  border-radius: 18px;
  background: var(--paper);
  box-shadow:
    0 0 0 1px var(--mower-border),
    0 18px 40px -24px rgba(0, 0, 0, 0.35);
}
.dial-panel h2 {
  margin: -8px 0 0;
  font-size: 22px;
}
.dial-kicker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.dial-kicker::before {
  content: '';
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--c);
}
.dial-when {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
}
.dial-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.dial-range {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
@container main-content (max-width: 960px) {
  .dial-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .dial-index {
    flex-direction: row;
    flex-wrap: wrap;
    order: 2;
  }
  .dial-group {
    flex: 1 1 200px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .dial-mark {
    transition: none;
  }
}
</style>
