<script setup>
// PROTOTYPE 变体 D：∞ 回路。左环是基建（一直在转），右环是闲时出环；交汇点 O 是判断：
// 距下个基建任务 ≥ 9 分钟才驶入右环，依次经过日常 → MAA → 长任务，回到 O 后执行空闲动作并休眠。
// 光点沿回路流动表示当前执行位置；设备在交汇点（整套回路的心脏），节奏控制光点的流速。
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
import {
  W,
  H,
  O,
  sampleLobe,
  center,
  pathBetween,
  placeAlong,
  pointAt,
  normalAt
} from './loopGeometry'
import FieldEditor from './FieldEditor.vue'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state

const left = sampleLobe('left')
const right = sampleLobe('right')
const MARGIN = 95
const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const leftStops = computed(() =>
  placeAlong(
    left,
    s.tasks.filter((t) => t.section === 'base'),
    MARGIN
  )
)
const outer = computed(() => s.tasks.filter((t) => t.section !== 'base'))
const rightStops = computed(() => placeAlong(right, outer.value, MARGIN))

// 右环按段着色：每一段从该组第一个站前到最后一个站后
const segments = computed(() => {
  const list = rightStops.value
  const keys = ['daily', 'maa', 'long']
  const out = []
  let cursor = MARGIN * 0.6
  keys.forEach((key, k) => {
    const mine = list.filter((st) => st.item.section === key)
    if (!mine.length) return
    const next = list.find((st, i) => i > list.indexOf(mine.at(-1)))
    const end = next ? (mine.at(-1).s + next.s) / 2 : right.L - MARGIN * 0.6
    const midS = (cursor + end) / 2
    const [mx, my] = pointAt(right, midS)
    const [nx, ny] = normalAt(right, midS)
    // 段名放在环内侧，避开外侧的站名
    out.push({ key, d: pathBetween(right, cursor, end), mid: [mx - nx * 46, my - ny * 46 + 4], k })
    cursor = end
  })
  return out
})
const leftPath = pathBetween(left, 0, left.L)
const rightPath = pathBetween(right, 0, right.L)
const sleepPath = computed(() => pathBetween(right, right.L - MARGIN * 0.6, right.L))
const flowPath = `${leftPath} ${rightPath.replace('M', 'L')}`
const pace = computed(() => s.globals.pace.fields[0].value)
const flowDur = computed(() => `${Math.max(6, pace.value / 30)}s`)

// 插入口：每段尾部一个 + 号
const slots = computed(() => {
  const out = []
  const groups = [
    ['base', leftStops.value, left],
    ['daily', rightStops.value.filter((x) => x.item.section === 'daily'), right],
    ['maa', rightStops.value.filter((x) => x.item.section === 'maa'), right],
    ['long', rightStops.value.filter((x) => x.item.section === 'long'), right]
  ]
  for (const [key, list, lobe] of groups) {
    if (!s.spare.some((t) => t.section === key)) continue
    const last = list.at(-1)
    let at = last ? last.s + (key === 'base' ? 34 : 30) : left.L / 2
    if (!last && key !== 'base') {
      const order = ['daily', 'maa', 'long']
      const rank = order.indexOf(key)
      const previous = rightStops.value.filter((st) => order.indexOf(st.item.section) < rank).at(-1)
      const next = rightStops.value.find((st) => order.indexOf(st.item.section) > rank)
      const start = previous?.s ?? MARGIN
      const end = next?.s ?? right.L - MARGIN
      const before = previous ? order.indexOf(previous.item.section) : -1
      const after = next ? order.indexOf(next.item.section) : order.length
      at = start + ((rank - before) / (after - before)) * (end - start)
    }
    const p = pointAt(lobe, at)
    out.push({ key, index: list.length, x: p[0], y: p[1] })
  }
  return out
})

const label = (st) => {
  const [x, y] = st.p
  const [nx, ny] = st.n
  return {
    x: x + nx * 30,
    y: y + ny * 30 + 5,
    anchor: nx > 0.35 ? 'start' : nx < -0.35 ? 'end' : 'middle'
  }
}

const hover = ref(null)
const inserting = ref(null)
const selectedTask = computed(() => s.tasks.find((t) => t.id === s.selected))
const idleLabel = computed(
  () => s.globals.idle.options.find(([v]) => v === s.globals.idle.value)[1]
)
const upcoming = computed(() => {
  const runs = simulateDay(s)
  return [...runs.filter((r) => r.hour > s.now), ...runs.filter((r) => r.hour <= s.now)]
    .slice(0, 4)
    .map((r) => ({ ...r, task: s.tasks.find((t) => t.id === r.id) }))
})
function pick(id) {
  s.selected = s.selected === id ? null : id
  inserting.value = null
}
function doInsert(id) {
  insertTask(s, id, inserting.value.key, inserting.value.index)
  inserting.value = null
}
const pct = (x, y) => ({ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` })
const [lcx, lcy] = center('left')
const [rcx, rcy] = center('right')
</script>
<template>
  <div class="loop" :class="{ 'loop--open': s.selected }">
    <div class="loop-stage">
      <svg :viewBox="`0 0 ${W} ${H}`" class="loop-svg" aria-hidden="true">
        <defs>
          <filter id="loop-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="loop-core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#fff" stop-opacity="0.9" />
            <stop offset="100%" stop-color="#fff" stop-opacity="0" />
          </radialGradient>
        </defs>

        <!-- 底轨 -->
        <path :d="leftPath" class="track" />
        <path :d="rightPath" class="track" />
        <!-- 着色段 -->
        <path :d="leftPath" class="lane" :stroke="sections.base.color" />
        <path
          v-for="seg in segments"
          :key="seg.key"
          :d="seg.d"
          class="lane"
          :stroke="sections[seg.key].color"
        />
        <path :d="sleepPath" class="lane lane--sleep" />
        <!-- 流动光点 -->
        <g v-if="!reduceMotion" filter="url(#loop-glow)">
          <circle r="6" class="spark">
            <animateMotion :dur="flowDur" repeatCount="indefinite" :path="flowPath" />
          </circle>
          <circle r="4" class="spark spark--b">
            <animateMotion :dur="flowDur" begin="-3s" repeatCount="indefinite" :path="leftPath" />
          </circle>
        </g>

        <!-- 环心文字 -->
        <text :x="lcx" :y="lcy - 14" class="lobe-title">基建</text>
        <text :x="lcx" :y="lcy + 12" class="lobe-sub">一直在转 · 跑单优先</text>
        <text :x="rcx" :y="rcy - 14" class="lobe-title">闲时</text>
        <text :x="rcx" :y="rcy + 12" class="lobe-sub">空闲 ≥ 9 分钟才驶入</text>

        <!-- 分段名 -->
        <text
          v-for="seg in segments"
          :key="`${seg.key}-t`"
          :x="seg.mid[0]"
          :y="seg.mid[1]"
          class="seg-name"
          :fill="sections[seg.key].color"
        >
          {{ sections[seg.key].title.replace('线', '') }}
        </text>

        <!-- 站名 -->
        <text
          v-for="st in [...leftStops, ...rightStops]"
          :key="`${st.item.id}-l`"
          :x="label(st).x"
          :y="label(st).y"
          :text-anchor="label(st).anchor"
          class="stop-name"
          :class="{
            'is-off': !st.item.enabled,
            'is-picked': s.selected === st.item.id,
            'is-hover': hover === st.item.id
          }"
        >
          {{ st.item.name }}
        </text>
      </svg>

      <!-- 站点（可点） -->
      <button
        v-for="st in [...leftStops, ...rightStops]"
        :key="st.item.id"
        type="button"
        class="stop"
        :class="{ 'is-on': s.selected === st.item.id, 'is-off': !st.item.enabled }"
        :style="{ ...pct(st.p[0], st.p[1]), '--c': sections[st.item.section].color }"
        :aria-label="`${sections[st.item.section].title} · ${st.item.name}${st.item.enabled ? '' : '（停用）'}`"
        :aria-pressed="s.selected === st.item.id"
        @mouseenter="hover = st.item.id"
        @mouseleave="hover = null"
        @click="pick(st.item.id)"
      ></button>

      <button
        v-for="slot in slots"
        :key="`${slot.key}-slot`"
        type="button"
        class="slot"
        :style="{ ...pct(slot.x, slot.y), '--c': sections[slot.key].color }"
        :aria-label="`往${sections[slot.key].title}加任务`"
        @click="inserting = inserting?.key === slot.key ? null : slot"
      >
        +
      </button>
      <div v-if="inserting" class="slot-menu" :style="pct(inserting.x, inserting.y)" role="menu">
        <button
          v-for="t in s.spare.filter((t) => t.section === inserting.key)"
          :key="t.id"
          type="button"
          role="menuitem"
          @click="doInsert(t.id)"
        >
          {{ t.name }}<small>{{ t.trigger }}</small>
        </button>
      </div>

      <!-- 交汇点：设备 -->
      <button
        type="button"
        class="heart"
        :class="{ 'is-on': s.selected === 'device' }"
        :style="pct(O.x, O.y)"
        @click="pick('device')"
      >
        <span class="heart-pulse" aria-hidden="true"></span>
        <b>{{ s.globals.device.name.split(' · ')[0] }}</b>
        <small>{{ s.globals.device.status }}</small>
      </button>

      <!-- 返回点：空闲动作 -->
      <button
        type="button"
        class="rest"
        :class="{ 'is-on': s.selected === 'idle' }"
        :style="pct(O.x, O.y + 150)"
        @click="pick('idle')"
      >
        休眠前 · {{ idleLabel }}
      </button>
    </div>

    <!-- 底部状态条：节奏 + 接下来 -->
    <footer class="hud">
      <button
        type="button"
        class="hud-pace"
        :class="{ 'is-on': s.selected === 'pace' }"
        @click="pick('pace')"
      >
        <span class="hud-k">流速</span>
        <b>{{ pace }}<small>ms</small></b>
      </button>
      <button
        type="button"
        class="hud-gate"
        :class="{ 'is-on': s.selected === 'gate' }"
        @click="pick('gate')"
      >
        <span class="hud-k">出环条件</span>
        <b>≥ 9 分钟 · MAA 每 {{ s.globals.maaGap }} 小时</b>
      </button>
      <ol class="hud-next" aria-label="接下来">
        <li
          v-for="run in upcoming"
          :key="run.id + run.hour"
          :style="{ '--c': sections[run.section].color }"
        >
          <time>{{ fmt(run.hour) }}</time
          >{{ run.task?.name }}
        </li>
      </ol>
    </footer>

    <aside v-if="s.selected" class="inspect" aria-live="polite">
      <button type="button" class="inspect-close" aria-label="关闭" @click="s.selected = null">
        ×
      </button>
      <template v-if="selectedTask">
        <p class="inspect-k" :style="{ '--c': sections[selectedTask.section].color }">
          {{ sections[selectedTask.section].title }}
        </p>
        <h2>{{ selectedTask.name }}</h2>
        <p class="inspect-sub">
          {{ cadenceLabel(s, selectedTask) }} · 下一次
          {{ selectedTask.enabled ? nextRun(s, selectedTask.id) : '—' }}
        </p>
        <label class="inspect-row"
          ><span>启用</span><n-switch v-model:value="selectedTask.enabled"
        /></label>
        <FieldEditor :fields="selectedTask.fields" />
        <div class="inspect-actions">
          <n-button
            v-if="reorderable(selectedTask.section)"
            size="small"
            quaternary
            @click="moveTask(s, selectedTask.id, -1)"
            >提前</n-button
          >
          <n-button
            v-if="reorderable(selectedTask.section)"
            size="small"
            quaternary
            @click="moveTask(s, selectedTask.id, 1)"
            >推后</n-button
          >
          <n-button size="small" quaternary type="error" @click="removeTask(s, selectedTask.id)"
            >移出回路</n-button
          >
        </div>
      </template>
      <template v-else-if="s.selected === 'device'">
        <p class="inspect-k" style="--c: #22c55e">交汇点 · 设备</p>
        <h2>{{ s.globals.device.name }}</h2>
        <p class="inspect-sub">
          {{ s.globals.device.adb }} · {{ s.globals.device.cpu }} · {{ s.globals.device.ram }}
        </p>
        <div class="inspect-actions">
          <n-button size="small" type="primary">测试连接</n-button>
          <n-button size="small">检测实例</n-button>
        </div>
        <FieldEditor :fields="s.globals.device.fields" />
      </template>
      <template v-else-if="s.selected === 'pace'">
        <p class="inspect-k" style="--c: #94a3b8">流速</p>
        <h2>截图与等待</h2>
        <FieldEditor :fields="s.globals.pace.fields" />
        <p class="inspect-sub">回路上的光点速度跟着截图间隔变化。</p>
      </template>
      <template v-else-if="s.selected === 'gate'">
        <p class="inspect-k" style="--c: #94a3b8">出环条件</p>
        <h2>什么时候驶入闲时环</h2>
        <label class="inspect-row">
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
        <label class="inspect-row">
          <span>长任务暂停</span>
          <span class="inspect-range">
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
        <p class="inspect-sub">
          距下个基建任务不足 9 分钟时不出环；MAA 在基建任务前 5 分钟、长任务前 30 秒收回。
        </p>
      </template>
      <template v-else-if="s.selected === 'idle'">
        <p class="inspect-k" style="--c: #94a3b8">回到交汇点后</p>
        <h2>空闲动作</h2>
        <n-radio-group v-model:value="s.globals.idle.value">
          <n-space vertical>
            <n-radio v-for="[v, l] in s.globals.idle.options" :key="v" :value="v" :label="l" />
          </n-space>
        </n-radio-group>
      </template>
    </aside>
  </div>
</template>
<style scoped>
/* 深色舞台：无论亮暗主题都用夜色背景，让发光的回路成为唯一主角 */
.loop {
  --bg: #0b0d12;
  --ink: #e7eaf0;
  --muted: #8b93a5;
  --panel: rgba(20, 23, 31, 0.86);
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 1fr auto;
  min-height: calc(100vh - 32px);
  padding: 20px 24px 96px;
  box-sizing: border-box;
  color: var(--ink);
  background:
    radial-gradient(ellipse at 40% 45%, rgba(34, 197, 94, 0.1), transparent 55%),
    radial-gradient(ellipse at 72% 50%, rgba(99, 102, 241, 0.1), transparent 55%),
    radial-gradient(circle at 1px 1px, rgba(255, 255, 255, 0.05) 1px, transparent 0) 0 0 / 22px 22px,
    var(--bg);
}
.loop-stage {
  position: relative;
  width: 100%;
  max-width: 1200px;
  aspect-ratio: 1200 / 600;
  justify-self: center;
  align-self: center;
}
.loop-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.06);
  stroke-width: 26;
  stroke-linecap: round;
}
.lane {
  fill: none;
  stroke-width: 6;
  stroke-linecap: round;
  filter: drop-shadow(0 0 6px currentColor);
}
.lane--sleep {
  stroke: #64748b;
  stroke-width: 3;
  stroke-dasharray: 2 9;
}
.spark {
  fill: #fff;
}
.spark--b {
  fill: #86efac;
}
.lobe-title {
  font-size: 40px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-anchor: middle;
  fill: rgba(255, 255, 255, 0.92);
}
.lobe-sub {
  font-size: 14px;
  text-anchor: middle;
  fill: var(--muted);
}
.seg-name {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.3em;
  text-anchor: middle;
}
.stop-name {
  font-size: 15px;
  font-weight: 600;
  fill: var(--ink);
  pointer-events: none;
  transition: fill 0.15s ease;
}
.stop-name.is-off {
  fill: #4b5262;
  text-decoration: line-through;
}
.stop-name.is-hover,
.stop-name.is-picked {
  fill: #fff;
  font-weight: 800;
}
.stop {
  position: absolute;
  width: 18px;
  height: 18px;
  padding: 0;
  transform: translate(-50%, -50%);
  border: 0;
  border-radius: 50%;
  background: var(--bg);
  box-shadow:
    inset 0 0 0 4px var(--c),
    0 0 14px var(--c);
  cursor: pointer;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}
.stop:hover,
.stop:focus-visible {
  outline: none;
  transform: translate(-50%, -50%) scale(1.35);
}
.stop.is-on {
  transform: translate(-50%, -50%) scale(1.5);
  background: var(--c);
  box-shadow:
    0 0 0 6px color-mix(in srgb, var(--c) 30%, transparent),
    0 0 26px var(--c);
}
.stop.is-off {
  box-shadow: inset 0 0 0 2px #4b5262;
}
.slot {
  position: absolute;
  width: 22px;
  height: 22px;
  transform: translate(-50%, -50%);
  border: 1px dashed var(--c);
  border-radius: 50%;
  font-size: 14px;
  line-height: 20px;
  color: var(--c);
  background: var(--bg);
  cursor: pointer;
  opacity: 0.35;
  transition: opacity 0.15s ease;
}
.loop-stage:hover .slot,
.slot:focus-visible {
  opacity: 1;
  outline: none;
}
.slot-menu {
  position: absolute;
  z-index: 6;
  transform: translate(-50%, 18px);
  display: flex;
  flex-direction: column;
  min-width: 190px;
  padding: 6px;
  border-radius: 12px;
  background: var(--panel);
  backdrop-filter: blur(14px);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08),
    0 20px 40px -12px #000;
}
.slot-menu button {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  background: none;
  cursor: pointer;
}
.slot-menu button:hover {
  background: rgba(255, 255, 255, 0.08);
}
.slot-menu small {
  color: var(--muted);
}
.heart {
  position: absolute;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 112px;
  height: 112px;
  transform: translate(-50%, -50%);
  border: 0;
  border-radius: 50%;
  font: inherit;
  color: #fff;
  background: radial-gradient(circle at 40% 35%, #1f2937, #05070a 70%);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12),
    0 0 0 10px rgba(11, 13, 18, 0.9),
    0 0 50px rgba(34, 197, 94, 0.35);
  cursor: pointer;
}
.heart b {
  font-size: 15px;
}
.heart small {
  margin-top: 2px;
  font-size: 11px;
  color: #4ade80;
}
.heart-pulse {
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  border: 1.5px solid rgba(74, 222, 128, 0.6);
  animation: heart 2.4s ease-out infinite;
}
@keyframes heart {
  from {
    transform: scale(0.9);
    opacity: 1;
  }
  to {
    transform: scale(1.5);
    opacity: 0;
  }
}
.rest {
  position: absolute;
  z-index: 2;
  transform: translate(-50%, 0);
  white-space: nowrap;
  padding: 5px 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  color: var(--muted);
  background: rgba(11, 13, 18, 0.9);
  cursor: pointer;
}
.rest:hover {
  color: var(--ink);
}
.is-on.heart,
.is-on.rest,
.hud .is-on {
  outline: 2px solid #4ade80;
  outline-offset: 3px;
}
.hud {
  display: flex;
  align-items: stretch;
  gap: 10px;
  justify-self: center;
  max-width: 100%;
  padding: 8px;
  border-radius: 18px;
  background: var(--panel);
  backdrop-filter: blur(14px);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.07);
}
.hud button {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 6px 14px;
  border: 0;
  border-radius: 12px;
  font: inherit;
  text-align: left;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.05);
  cursor: pointer;
}
.hud button:hover {
  background: rgba(255, 255, 255, 0.1);
}
.hud-k {
  font-size: 11px;
  color: var(--muted);
}
.hud b {
  font-size: 15px;
  font-variant-numeric: tabular-nums;
}
.hud b small {
  margin-left: 2px;
  font-size: 11px;
  color: var(--muted);
}
.hud-next {
  display: flex;
  gap: 14px;
  align-items: center;
  margin: 0;
  padding: 0 10px;
  list-style: none;
  font-size: 13px;
  white-space: nowrap;
  overflow-x: auto;
}
.hud-next li {
  display: flex;
  align-items: center;
  gap: 6px;
}
.hud-next li::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c);
  box-shadow: 0 0 8px var(--c);
}
.hud-next time {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.inspect {
  position: absolute;
  z-index: 10;
  top: 20px;
  right: 20px;
  bottom: 96px;
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 22px 20px;
  overflow-y: auto;
  box-sizing: border-box;
  border-radius: 20px;
  background: var(--panel);
  backdrop-filter: blur(18px);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08),
    0 30px 60px -20px #000;
  animation: inspect-in 0.2s ease-out;
}
@keyframes inspect-in {
  from {
    opacity: 0;
    transform: translateX(12px);
  }
}
.inspect h2 {
  margin: -8px 0 0;
  font-size: 24px;
  color: #fff;
}
.inspect-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  font-size: 18px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.06);
  cursor: pointer;
}
.inspect-k {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.inspect-k::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c);
  box-shadow: 0 0 10px var(--c);
}
.inspect-sub {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
}
.inspect-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.inspect-range {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.inspect-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.inspect :deep(.proto-field-label) {
  color: var(--ink);
}
@container main-content (max-width: 900px) {
  .loop {
    padding: 12px 8px 96px;
  }
  .loop-stage {
    min-width: 760px;
  }
  .loop {
    overflow-x: auto;
  }
  .inspect {
    position: fixed;
    top: auto;
    left: 8px;
    right: 8px;
    bottom: 70px;
    width: auto;
    max-height: 60vh;
  }
}
@media (prefers-reduced-motion: reduce) {
  .heart-pulse,
  .inspect {
    animation: none;
  }
  .stop,
  .slot,
  .stop-name {
    transition: none;
  }
}
</style>
