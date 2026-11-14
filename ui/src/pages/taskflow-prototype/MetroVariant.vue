<script setup>
// PROTOTYPE 变体 A：线路图。基建是一直在转的环线；空闲 ≥ 9 分钟时在换乘站分出支线，
// 依次停靠日常、MAA、长任务各站，到终点执行空闲动作后休眠回环线。
import { computed, ref } from 'vue'
import {
  sections,
  insertTask,
  removeTask,
  moveTask,
  nextRun,
  fmt,
  simulateDay,
  reorderable
} from './data'
import { cadenceLabel } from './shared'
import FieldEditor from './FieldEditor.vue'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state

const W = 1240
const H = 480
const C = { x: 210, y: 250 }
const R = 140
const X0 = 560
const X1 = 1110
const ROW1 = 90
const ROW2 = 410
const rad = (a) => (a * Math.PI) / 180
const onRing = (a, r = R) => ({ x: C.x + r * Math.cos(rad(a)), y: C.y + r * Math.sin(rad(a)) })
const hub = onRing(-25)
const back = onRing(25)

const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const ringPath = `M ${C.x + R} ${C.y} A ${R} ${R} 0 1 1 ${C.x - R} ${C.y} A ${R} ${R} 0 1 1 ${C.x + R} ${C.y}`
const outPath = `M ${hub.x} ${hub.y} L 390 ${hub.y} Q 430 ${hub.y} 430 ${hub.y - 40} L 430 130 Q 430 ${ROW1} 470 ${ROW1} L ${X1} ${ROW1}`
const turnPath = `M ${X1} ${ROW1} Q ${X1 + 50} ${ROW1} ${X1 + 50} ${ROW1 + 50} L ${X1 + 50} ${ROW2 - 50} Q ${X1 + 50} ${ROW2} ${X1} ${ROW2}`
const sleepPath = `M ${X0 - 100} ${ROW2} L 470 ${ROW2} Q 430 ${ROW2} 430 ${ROW2 - 40} L 430 ${back.y + 40} Q 430 ${back.y} 390 ${back.y} L ${back.x} ${back.y}`

const of = (section) => s.tasks.filter((t) => t.section === section)
const hasSpare = (section) => s.spare.some((t) => t.section === section)

const layout = computed(() => {
  const stations = []
  const slots = []
  // 环线：返回点之后顺时针排开，换乘站之前结束
  const base = of('base')
  const step = 230 / Math.max(base.length - 1, 1)
  base.forEach((task, i) => {
    const a = 62 + i * step
    const p = onRing(a)
    const l = onRing(a, R + 30)
    const cos = Math.cos(rad(a))
    stations.push({
      task,
      ...p,
      lx: l.x,
      ly: l.y + 4,
      anchor: cos > 0.3 ? 'start' : cos < -0.3 ? 'end' : 'middle'
    })
    if (hasSpare('base')) slots.push({ section: 'base', index: i + 1, ...onRing(a + step / 2) })
  })
  if (!base.length && hasSpare('base')) slots.push({ section: 'base', index: 0, ...onRing(180) })
  // 第一行：日常线
  const daily = of('daily')
  const s1 = (X1 - X0) / Math.max(daily.length - 1, 1)
  daily.forEach((task, i) => {
    const x = X0 + i * s1
    // 站点较多，标签上下交错避免重叠
    const ly = i % 2 ? ROW1 + 34 : ROW1 - 22
    stations.push({ task, x, y: ROW1, lx: x, ly, anchor: 'middle' })
    if (hasSpare('daily') && i < daily.length - 1)
      slots.push({ section: 'daily', index: i + 1, x: x + s1 / 2, y: ROW1 })
  })
  if (hasSpare('daily'))
    slots.push({ section: 'daily', index: daily.length, x: X1 + 50, y: ROW1 + 60 })
  // 第二行：MAA 线、长任务线，最后是终点
  // 空线路仍保留一个位置，移出最后一站后可以从这里重新插入。
  const row2 = ['maa', 'long'].flatMap((section) => {
    const tasks = of(section)
    return tasks.length ? tasks : [{ section, empty: true }]
  })
  const s2 = (X1 - X0) / row2.length
  const ends = {}
  row2.forEach((task, i) => {
    const x = X1 - i * s2
    ends[task.section] = x
    if (task.empty) {
      if (hasSpare(task.section)) slots.push({ section: task.section, index: 0, x, y: ROW2 })
      return
    }
    stations.push({ task, x, y: ROW2, lx: x, ly: ROW2 + 30, anchor: 'middle' })
    if (hasSpare(task.section)) {
      const sectionIndex = of(task.section).indexOf(task) + 1
      slots.push({ section: task.section, index: sectionIndex, x: x - s2 / 2, y: ROW2 })
    }
  })
  return { stations, slots, maaEnd: ends.maa ?? X1, longEnd: ends.long ?? ends.maa ?? X1 }
})

const insertAt = ref(null)
function openInsert(slot) {
  insertAt.value = insertAt.value?.x === slot.x && insertAt.value?.y === slot.y ? null : slot
}
function doInsert(id) {
  insertTask(s, id, insertAt.value.section, insertAt.value.index)
  insertAt.value = null
}

const selectedTask = computed(
  () => s.tasks.find((t) => t.id === s.selected) ?? s.spare.find((t) => t.id === s.selected)
)
const board = computed(() => {
  const runs = simulateDay(s)
  const later = [...runs.filter((r) => r.hour > s.now), ...runs.filter((r) => r.hour <= s.now)]
  return later.slice(0, 6).map((r) => ({ ...r, task: s.tasks.find((t) => t.id === r.id) }))
})
const idleLabel = computed(
  () => s.globals.idle.options.find(([v]) => v === s.globals.idle.value)[1]
)
const pct = (x, y) => ({ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` })
function pick(id) {
  s.selected = s.selected === id ? null : id
  insertAt.value = null
}
</script>
<template>
  <div class="metro" :class="{ 'metro--open': s.selected }">
    <header class="metro-top">
      <button
        type="button"
        class="metro-train"
        :class="{ 'is-on': s.selected === 'device' }"
        @click="pick('device')"
      >
        <span class="metro-train-nose" aria-hidden="true"></span>
        <span class="metro-train-body">
          <b>{{ s.globals.device.name }}</b>
          <small>{{ s.globals.device.status }} · {{ s.globals.device.adb }}</small>
        </span>
        <span class="metro-train-tag">列车</span>
      </button>
      <button
        type="button"
        class="metro-speed"
        :class="{ 'is-on': s.selected === 'pace' }"
        @click="pick('pace')"
      >
        <span>行车节奏</span>
        <b>{{ s.globals.pace.fields[0].value }} ms</b>
        <small>截图间隔 · 场景等待</small>
      </button>
      <div class="metro-board" aria-label="接下来发车">
        <div class="metro-board-head">
          <span>接下来</span><span>{{ fmt(s.now) }}</span>
        </div>
        <ol>
          <li v-for="run in board" :key="run.id + run.hour">
            <i :style="{ background: sections[run.section].color }"></i>
            <span>{{ run.task?.name }}</span>
            <time>{{ fmt(run.hour) }}</time>
          </li>
        </ol>
      </div>
    </header>

    <div class="metro-scroll">
      <div class="metro-map">
        <svg :viewBox="`0 0 ${W} ${H}`" aria-hidden="true">
          <path :d="ringPath" class="line" :stroke="sections.base.color" />
          <path :d="outPath" class="line" :stroke="sections.daily.color" />
          <path :d="turnPath" class="line" :stroke="sections.maa.color" />
          <path
            :d="`M ${X1} ${ROW2} L ${layout.maaEnd - 30} ${ROW2}`"
            class="line"
            :stroke="sections.maa.color"
          />
          <path
            :d="`M ${layout.maaEnd - 30} ${ROW2} L ${X0} ${ROW2}`"
            class="line"
            :stroke="sections.long.color"
          />
          <path :d="sleepPath" class="line line--sleep" />
          <circle v-if="!reduceMotion" r="9" class="metro-dot">
            <animateMotion dur="14s" repeatCount="indefinite" :path="ringPath" />
          </circle>
          <text
            v-for="st in layout.stations"
            :key="`${st.task.id}-label`"
            :x="st.lx"
            :y="st.ly"
            class="metro-label"
            :class="{ 'is-off': !st.task.enabled, 'is-picked': s.selected === st.task.id }"
            :text-anchor="st.anchor"
          >
            {{ st.task.name }}
          </text>
          <text :x="C.x" :y="C.y - 8" class="metro-ring-title">基建环线</text>
          <text :x="C.x" :y="C.y + 14" class="metro-ring-sub">按任务时间排队 · 跑单优先</text>
          <text :x="442" :y="(ROW1 + hub.y) / 2 + 6" class="metro-cond">空闲 ≥ 9 分钟</text>
          <text :x="442" :y="(ROW2 + back.y) / 2 + 6" class="metro-cond">休眠至下个基建任务</text>
          <text :x="X1 + 62" :y="(ROW1 + ROW2) / 2" class="metro-cond metro-cond--v">
            每 {{ s.globals.maaGap }} 小时
          </text>
        </svg>

        <button
          type="button"
          class="metro-hub"
          :style="pct(hub.x, hub.y)"
          :class="{ 'is-on': s.selected === 'gap' }"
          @click="pick('gap')"
        >
          换乘
        </button>

        <button
          v-for="st in layout.stations"
          :key="st.task.id"
          type="button"
          class="metro-station"
          :class="{
            'is-on': s.selected === st.task.id,
            'is-off': !st.task.enabled
          }"
          :style="{ ...pct(st.x, st.y), '--c': sections[st.task.section].color }"
          :aria-label="`${sections[st.task.section].title} · ${st.task.name}${st.task.enabled ? '' : '（停运）'}`"
          :aria-pressed="s.selected === st.task.id"
          @click="pick(st.task.id)"
        >
          <span class="metro-station-dot"></span>
        </button>

        <button
          v-for="slot in layout.slots"
          :key="slot.section + slot.index + slot.x"
          type="button"
          class="metro-slot"
          :style="{ ...pct(slot.x, slot.y), '--c': sections[slot.section].color }"
          :aria-label="`在${sections[slot.section].title}插入站点`"
          @click="openInsert(slot)"
        >
          +
        </button>

        <div v-if="insertAt" class="metro-insert" :style="pct(insertAt.x, insertAt.y)" role="menu">
          <b>插入到{{ sections[insertAt.section].title }}</b>
          <button
            v-for="t in s.spare.filter((t) => t.section === insertAt.section)"
            :key="t.id"
            type="button"
            role="menuitem"
            @click="doInsert(t.id)"
          >
            {{ t.name }} <small>{{ t.trigger }}</small>
          </button>
        </div>

        <button
          type="button"
          class="metro-terminal"
          :style="pct(X0 - 58, ROW2)"
          :class="{ 'is-on': s.selected === 'idle' }"
          @click="pick('idle')"
        >
          <small>终点</small>{{ idleLabel }}
        </button>

        <ul class="metro-legend">
          <li v-for="(meta, key) in sections" :key="key">
            <i :style="{ background: meta.color }"></i>{{ meta.title }}
          </li>
        </ul>
      </div>
    </div>

    <aside v-if="s.selected" class="metro-panel" aria-live="polite">
      <template v-if="selectedTask">
        <div class="metro-panel-line" :style="{ '--c': sections[selectedTask.section].color }">
          {{ sections[selectedTask.section].title }}
        </div>
        <h2>{{ selectedTask.name }}</h2>
        <dl class="metro-facts">
          <div>
            <dt>发车条件</dt>
            <dd>{{ cadenceLabel(s, selectedTask) }}</dd>
          </div>
          <div>
            <dt>下一班</dt>
            <dd>{{ selectedTask.enabled ? nextRun(s, selectedTask.id) : '停运' }}</dd>
          </div>
        </dl>
        <label class="metro-toggle">
          <span>本站运营</span>
          <n-switch v-model:value="selectedTask.enabled" />
        </label>
        <FieldEditor :fields="selectedTask.fields" />
        <div class="metro-panel-actions">
          <template v-if="reorderable(selectedTask.section)">
            <n-button size="small" @click="moveTask(s, selectedTask.id, -1)">前移一站</n-button>
            <n-button size="small" @click="moveTask(s, selectedTask.id, 1)">后移一站</n-button>
          </template>
          <span v-else class="metro-note">{{
            selectedTask.section === 'base' ? '基建队列按时间排序' : '日常顺序固定'
          }}</span>
          <n-button size="small" type="error" ghost @click="removeTask(s, selectedTask.id)"
            >撤站</n-button
          >
        </div>
        <p class="metro-note">{{ sections[selectedTask.section].note }}</p>
      </template>
      <template v-else-if="s.selected === 'device'">
        <div class="metro-panel-line" style="--c: #111">列车</div>
        <h2>{{ s.globals.device.name }}</h2>
        <dl class="metro-facts">
          <div>
            <dt>状态</dt>
            <dd>{{ s.globals.device.status }}</dd>
          </div>
          <div>
            <dt>ADB</dt>
            <dd>{{ s.globals.device.adb }}</dd>
          </div>
          <div>
            <dt>处理器</dt>
            <dd>{{ s.globals.device.cpu }}</dd>
          </div>
          <div>
            <dt>内存</dt>
            <dd>{{ s.globals.device.ram }}</dd>
          </div>
        </dl>
        <div class="metro-panel-actions">
          <n-button size="small" type="primary">测试连接</n-button>
          <n-button size="small">检测实例</n-button>
        </div>
        <FieldEditor :fields="s.globals.device.fields" />
      </template>
      <template v-else-if="s.selected === 'pace'">
        <div class="metro-panel-line" style="--c: #111">行车节奏</div>
        <h2>截图与等待</h2>
        <FieldEditor :fields="s.globals.pace.fields" />
        <p class="metro-note">越快越灵敏，越慢越省资源。所有线路共用。</p>
      </template>
      <template v-else-if="s.selected === 'idle'">
        <div class="metro-panel-line" style="--c: #64748b">终点站</div>
        <h2>空闲时</h2>
        <n-radio-group v-model:value="s.globals.idle.value">
          <n-space vertical>
            <n-radio v-for="[v, l] in s.globals.idle.options" :key="v" :value="v" :label="l" />
          </n-space>
        </n-radio-group>
        <p class="metro-note">跑完所有支线后执行，然后休眠到下一个基建任务。</p>
      </template>
      <template v-else-if="s.selected === 'gap'">
        <div class="metro-panel-line" style="--c: #64748b">换乘站</div>
        <h2>支线发车规则</h2>
        <label class="metro-toggle">
          <span>MAA 发车间隔</span>
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
        <label class="metro-toggle">
          <span>长任务停运</span>
          <span class="metro-range">
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
        <p class="metro-note">距下一个基建任务不足 9 分钟时不换乘，列车留在环线。</p>
      </template>
    </aside>
  </div>
</template>
<style scoped>
.metro {
  --ink: var(--mower-text);
  --muted: var(--mower-text-muted);
  --paper: var(--mower-surface, #fff);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto 1fr;
  gap: 20px;
  min-height: 100%;
  padding: 24px 28px 80px;
  box-sizing: border-box;
  color: var(--ink);
}
.metro--open {
  grid-template-columns: minmax(0, 1fr) 340px;
}
.metro-top {
  grid-column: 1 / -1;
  display: flex;
  gap: 14px;
  align-items: stretch;
}
.metro-top > button {
  border: 0;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.metro-train {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 22px 12px 16px;
  border-radius: 14px 40px 40px 14px;
  color: #fff;
  background: linear-gradient(180deg, #2b2b2e, #141416);
  box-shadow: inset 0 -4px 0 #16a34a;
}
.metro-train-nose {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fde047;
  box-shadow: 0 0 10px #fde047;
}
.metro-train-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metro-train-body small {
  opacity: 0.65;
}
.metro-train-tag {
  margin-left: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.14);
}
.metro-speed {
  display: grid;
  grid-template-columns: auto auto;
  column-gap: 10px;
  align-content: center;
  padding: 10px 18px;
  border-radius: 14px;
  color: var(--ink);
  background: var(--mower-control-surface);
}
.metro-speed span,
.metro-speed small {
  color: var(--muted);
  font-size: 12px;
}
.metro-speed b {
  font-size: 20px;
  font-variant-numeric: tabular-nums;
}
.metro-speed small {
  grid-column: 1 / -1;
}
.metro-board {
  flex: 1;
  min-width: 0;
  padding: 10px 14px;
  border-radius: 14px;
  color: #fbbf24;
  background: #0b0b0c;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}
.metro-board-head {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #a3a3a3;
}
.metro-board ol {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 18px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}
.metro-board li {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.metro-board li span {
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.metro-board i {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.is-on {
  outline: 3px solid color-mix(in srgb, var(--mower-primary) 45%, transparent);
  outline-offset: 2px;
}
.metro-scroll {
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 48px;
}
.metro-scroll .metro-map {
  min-width: 860px;
}
.metro-label {
  font-size: 17px;
  font-weight: 600;
  fill: var(--ink);
  paint-order: stroke;
  stroke: var(--paper);
  stroke-width: 5px;
  stroke-linejoin: round;
  dominant-baseline: middle;
  pointer-events: none;
}
.metro-label.is-off {
  fill: var(--muted);
  text-decoration: line-through;
}
.metro-label.is-picked {
  fill: var(--mower-primary);
}
.metro-map {
  position: relative;
  min-width: 0;
  aspect-ratio: 1240 / 480;
  align-self: start;
}
.metro-map svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.line {
  fill: none;
  stroke-width: 10;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.line--sleep {
  stroke: var(--muted);
  stroke-width: 4;
  stroke-dasharray: 2 10;
  opacity: 0.6;
}
.metro-dot {
  fill: #fde047;
  stroke: #111;
  stroke-width: 3;
}
.metro-ring-title {
  text-anchor: middle;
  font-size: 26px;
  font-weight: 700;
  fill: var(--ink);
}
.metro-ring-sub,
.metro-cond {
  text-anchor: middle;
  font-size: 15px;
  fill: var(--muted);
}
.metro-cond {
  text-anchor: start;
}
.metro-cond--v {
  writing-mode: vertical-rl;
  text-anchor: middle;
}
.metro-station,
.metro-slot,
.metro-hub,
.metro-terminal {
  position: absolute;
  transform: translate(-50%, -50%);
  border: 0;
  padding: 0;
  font: inherit;
  cursor: pointer;
  background: none;
}
.metro-station-dot {
  display: block;
  width: 22px;
  height: 22px;
  box-sizing: border-box;
  border: 5px solid var(--c);
  border-radius: 50%;
  background: var(--paper);
  transition: transform 0.15s ease;
}
.metro-station:hover .metro-station-dot,
.metro-station:focus-visible .metro-station-dot {
  transform: scale(1.25);
}
.metro-station:focus-visible {
  outline: none;
}
.metro-station.is-on {
  outline: none;
}
.metro-station.is-on .metro-station-dot {
  border-width: 7px;
  transform: scale(1.35);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--c) 25%, transparent);
}
.metro-station.is-off .metro-station-dot {
  border-color: color-mix(in srgb, var(--c) 30%, var(--paper));
  border-style: dashed;
}
.metro-slot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 14px;
  line-height: 18px;
  color: var(--c);
  background: var(--paper);
  box-shadow: inset 0 0 0 2px var(--c);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.metro-map:hover .metro-slot,
.metro-slot:focus-visible {
  opacity: 1;
  outline: none;
}
.metro-hub {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink);
  background: var(--paper);
  box-shadow:
    inset 0 0 0 5px var(--ink),
    0 0 0 4px var(--paper);
}
.metro-terminal {
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  padding: 6px 12px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: #475569;
}
.metro-terminal small {
  font-size: 10px;
  font-weight: 400;
  opacity: 0.75;
}
.metro-insert {
  position: absolute;
  z-index: 5;
  transform: translate(-50%, 18px);
  display: flex;
  flex-direction: column;
  min-width: 180px;
  padding: 6px;
  border-radius: 10px;
  background: var(--paper);
  box-shadow:
    0 10px 30px -10px rgba(0, 0, 0, 0.35),
    0 0 0 1px var(--mower-border);
}
.metro-insert b {
  padding: 4px 8px 6px;
  font-size: 12px;
  color: var(--muted);
}
.metro-insert button {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 8px;
  border: 0;
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  text-align: left;
  color: var(--ink);
  background: none;
  cursor: pointer;
}
.metro-insert button:hover,
.metro-insert button:focus-visible {
  outline: none;
  background: var(--mower-control-hover);
}
.metro-insert small {
  color: var(--muted);
}
.metro-legend {
  position: absolute;
  right: 0;
  bottom: -40px;
  display: flex;
  gap: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--muted);
}
.metro-legend i {
  display: inline-block;
  width: 18px;
  height: 5px;
  margin-right: 6px;
  vertical-align: middle;
  border-radius: 3px;
}
.metro-panel {
  position: sticky;
  top: 16px;
  align-self: start;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-radius: 16px;
  background: var(--paper);
  box-shadow:
    0 0 0 1px var(--mower-border),
    0 18px 40px -24px rgba(0, 0, 0, 0.35);
}
.metro-panel h2 {
  margin: -6px 0 0;
  font-size: 22px;
}
.metro-panel-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
}
.metro-panel-line::before {
  content: '';
  width: 22px;
  height: 6px;
  border-radius: 3px;
  background: var(--c);
}
.metro-facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 0;
}
.metro-facts div {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--mower-control-surface);
}
.metro-facts dt {
  font-size: 11px;
  color: var(--muted);
}
.metro-facts dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 600;
}
.metro-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.metro-range {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.metro-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.metro-note {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
}
@container main-content (max-width: 900px) {
  .metro,
  .metro--open {
    grid-template-columns: minmax(0, 1fr);
    padding: 16px 12px 80px;
  }
  .metro-top {
    flex-wrap: wrap;
  }
  .metro-board ol {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (prefers-reduced-motion: reduce) {
  .metro-station-dot,
  .metro-slot {
    transition: none;
  }
}
</style>
