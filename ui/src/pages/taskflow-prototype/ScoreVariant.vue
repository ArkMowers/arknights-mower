<script setup>
// PROTOTYPE 变体 C：乐谱。每个循环是一行谱，任务是音符，停用的任务是休止符。
// 反复记号标出循环方式；乐器名是设备，速度记号是截图节奏，终止线上的延长记号是空闲动作。
// 点击音符，谱行下方就地展开它的设置，像在乐谱上写批注。
import { computed, ref } from 'vue'
import { sections, insertTask, removeTask, moveTask, nextRun, reorderable } from './data'
import { cadenceLabel } from './shared'
import FieldEditor from './FieldEditor.vue'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state

const order = ['base', 'daily', 'maa', 'long']
const GAP = 10 // 谱线间距
const TOP = 30
const lineY = (i) => TOP + i * GAP
const STEP = 86
const HEAD = 120 // 谱号与反复记号占位

// 给每个音符一个稳定的音高，让谱面有起伏
const pitch = (id) => [...id].reduce((sum, c) => sum + c.charCodeAt(0), 0) % 7
const noteY = (id) => TOP + 40 - pitch(id) * (GAP / 2) - 5

const markings = computed(() => ({
  base: { left: '‖:', right: ':‖', text: '∞ 按任务时间', open: true },
  daily: { left: '‖:', right: ':‖', text: '空闲 ≥ 9 分', open: false },
  maa: { left: '‖:', right: ':‖', text: `× 每 ${s.globals.maaGap} 小时`, open: false },
  long: {
    left: '',
    right: '',
    text: `${String(s.globals.longPause[1]).padStart(2, '0')}:00 起 ~ 下个基建任务前`,
    open: false
  }
}))

const staves = computed(() =>
  order.map((key) => {
    const notes = s.tasks
      .filter((t) => t.section === key)
      .map((task, i) => ({ task, x: HEAD + 30 + i * STEP, y: noteY(task.id) }))
    return { key, notes, need: HEAD + 30 + Math.max(notes.length, 1) * STEP + 40 }
  })
)
// 所有谱行等宽，像真正的总谱一样上下对齐
const width = computed(() => Math.max(...staves.value.map((st) => st.need), 860))

const open = computed(() => s.tasks.find((t) => t.id === s.selected))
const inserting = ref(null) // { section, index }
function toggleInsert(section, index) {
  const same = inserting.value?.section === section && inserting.value?.index === index
  inserting.value = same ? null : { section, index }
}
function doInsert(id) {
  insertTask(s, id, inserting.value.section, inserting.value.index)
  inserting.value = null
}
function pick(id) {
  s.selected = s.selected === id ? null : id
  inserting.value = null
}
const tempo = computed(() => s.globals.pace.fields[0].value)
const idleLabel = computed(
  () => s.globals.idle.options.find(([v]) => v === s.globals.idle.value)[1]
)
// 节奏越快音符越密：仅作示意
const tempoWord = computed(() =>
  tempo.value <= 300 ? 'Presto' : tempo.value <= 700 ? 'Allegro' : 'Andante'
)
</script>
<template>
  <article class="score">
    <header class="score-head">
      <p class="score-sub">Arknights Mower · 自动化总谱</p>
      <h1>任务配置</h1>
      <div class="score-meta">
        <button
          type="button"
          class="score-instrument"
          :class="{ 'is-on': s.selected === 'device' }"
          @click="pick('device')"
        >
          <small>为</small>{{ s.globals.device.name }}<small>而作</small>
        </button>
        <button
          type="button"
          class="score-tempo"
          :class="{ 'is-on': s.selected === 'pace' }"
          @click="pick('pace')"
        >
          <i>{{ tempoWord }}</i> ♩ = {{ tempo }} ms
        </button>
      </div>
      <div v-if="s.selected === 'device' || s.selected === 'pace'" class="score-note-card">
        <template v-if="s.selected === 'device'">
          <p class="score-note-title">
            乐器 · {{ s.globals.device.status }} · {{ s.globals.device.adb }}
          </p>
          <n-space>
            <n-button size="small" type="primary">测试连接</n-button>
            <n-button size="small">检测实例</n-button>
          </n-space>
          <FieldEditor :fields="s.globals.device.fields" />
        </template>
        <template v-else>
          <p class="score-note-title">速度 · 所有声部共用</p>
          <FieldEditor :fields="s.globals.pace.fields" />
        </template>
      </div>
    </header>

    <section v-for="(staff, si) in staves" :key="staff.key" class="score-system">
      <div class="score-part" :style="{ '--c': sections[staff.key].color }">
        <b>{{ sections[staff.key].title.replace('线', '') }}</b>
        <small>{{ sections[staff.key].note }}</small>
      </div>
      <div class="score-staff-wrap">
        <svg
          :width="width"
          height="110"
          class="score-staff"
          :style="{ '--c': sections[staff.key].color }"
          aria-hidden="true"
        >
          <line v-for="i in 5" :key="i" x1="0" :x2="width" :y1="lineY(i - 1)" :y2="lineY(i - 1)" />
          <text x="6" :y="lineY(3) + 6" class="score-clef">𝄞</text>
          <text x="44" :y="TOP - 10" class="score-mark">{{ markings[staff.key].text }}</text>
          <text
            v-if="markings[staff.key].left"
            :x="HEAD - 30"
            :y="lineY(2) + 8"
            class="score-repeat"
          >
            {{ markings[staff.key].left }}
          </text>
          <template v-for="n in staff.notes" :key="n.task.id">
            <g v-if="n.task.enabled" class="score-glyph">
              <line :x1="n.x + 8" :x2="n.x + 8" :y1="n.y + 4" :y2="n.y - 32" class="score-stem" />
              <ellipse
                :cx="n.x"
                :cy="n.y + 5"
                rx="9"
                ry="6.5"
                transform-origin="center"
                class="score-head-dot"
              />
            </g>
            <text v-else :x="n.x - 6" :y="lineY(3)" class="score-rest">𝄽</text>
            <text :x="n.x" y="98" class="score-lyric" :class="{ 'is-off': !n.task.enabled }">
              {{ n.task.name }}
            </text>
          </template>
          <template v-if="si < staves.length - 1">
            <text
              v-if="markings[staff.key].right"
              :x="width - 34"
              :y="lineY(2) + 8"
              class="score-repeat"
            >
              {{ markings[staff.key].right }}
            </text>
          </template>
          <template v-else>
            <text :x="width - 12" y="98" class="score-lyric">{{ idleLabel }}</text>
            <line
              :x1="width - 14"
              :x2="width - 14"
              :y1="lineY(0)"
              :y2="lineY(4)"
              class="score-bar"
            />
            <rect
              :x="width - 8"
              :y="lineY(0)"
              width="5"
              :height="GAP * 4"
              class="score-bar-thick"
            />
          </template>
        </svg>

        <button
          v-for="n in staff.notes"
          :key="`${n.task.id}-hit`"
          type="button"
          class="score-hit"
          :class="{ 'is-on': s.selected === n.task.id }"
          :style="{ left: `${n.x - 24}px` }"
          :aria-label="`${sections[staff.key].title} · ${n.task.name}${n.task.enabled ? '' : '（休止）'}`"
          :aria-expanded="s.selected === n.task.id"
          @click="pick(n.task.id)"
        ></button>
        <template v-if="s.spare.some((t) => t.section === staff.key)">
          <button
            v-for="(n, i) in [...staff.notes, null]"
            :key="`${staff.key}-ins-${i}`"
            type="button"
            class="score-ins"
            :style="{
              left: `${HEAD + 30 + i * STEP - STEP / 2}px`,
              '--c': sections[staff.key].color
            }"
            :aria-label="`在${sections[staff.key].title}第 ${i + 1} 拍插入音符`"
            @click="toggleInsert(staff.key, i)"
          >
            +
          </button>
        </template>
        <button
          v-if="si === staves.length - 1"
          type="button"
          class="score-fermata"
          :class="{ 'is-on': s.selected === 'idle' }"
          :style="{ left: `${width - 10}px` }"
          :aria-label="`空闲时：${idleLabel}`"
          @click="pick('idle')"
        >
          <span aria-hidden="true">𝄐</span>
        </button>
      </div>

      <div v-if="inserting?.section === staff.key" class="score-palette" role="menu">
        <span>插入一个音符：</span>
        <button
          v-for="t in s.spare.filter((t) => t.section === staff.key)"
          :key="t.id"
          type="button"
          role="menuitem"
          @click="doInsert(t.id)"
        >
          ♪ {{ t.name }}
        </button>
      </div>

      <div v-if="open && open.section === staff.key" class="score-note-card">
        <div class="score-note-row">
          <p class="score-note-title">
            <b>{{ open.name }}</b> · {{ cadenceLabel(s, open) }} · 下一次
            {{ open.enabled ? nextRun(s, open.id) : '—' }}
          </p>
          <label class="score-inline">
            {{ open.enabled ? '演奏' : '休止'
            }}<n-switch v-model:value="open.enabled" size="small" />
          </label>
        </div>
        <FieldEditor :fields="open.fields" />
        <n-space>
          <template v-if="reorderable(open.section)">
            <n-button size="small" quaternary @click="moveTask(s, open.id, -1)">← 前移</n-button>
            <n-button size="small" quaternary @click="moveTask(s, open.id, 1)">后移 →</n-button>
          </template>
          <span v-else class="score-note-title">{{
            open.section === 'base' ? '基建队列按时间排序' : '日常顺序固定'
          }}</span>
          <n-button size="small" quaternary type="error" @click="removeTask(s, open.id)"
            >删去</n-button
          >
        </n-space>
      </div>
      <div v-if="si === staves.length - 1 && s.selected === 'idle'" class="score-note-card">
        <p class="score-note-title">延长记号 · 全曲终了后停留</p>
        <n-radio-group v-model:value="s.globals.idle.value">
          <n-space>
            <n-radio v-for="[v, l] in s.globals.idle.options" :key="v" :value="v" :label="l" />
          </n-space>
        </n-radio-group>
      </div>
    </section>

    <footer class="score-foot">
      <span>D.C. 休眠至下个基建任务后从头演奏</span>
      <label>
        MAA 反复间隔
        <n-input-number
          v-model:value="s.globals.maaGap"
          size="tiny"
          :min="1"
          :max="24"
          style="width: 90px"
        />
        小时
      </label>
      <label>
        长任务休止
        <n-input-number
          v-model:value="s.globals.longPause[0]"
          size="tiny"
          :min="0"
          :max="23"
          style="width: 70px"
        />
        –
        <n-input-number
          v-model:value="s.globals.longPause[1]"
          size="tiny"
          :min="0"
          :max="23"
          style="width: 70px"
        />
      </label>
    </footer>
  </article>
</template>
<style scoped>
.score {
  --ink: var(--mower-text);
  --muted: var(--mower-text-muted);
  --paper: #fbf8f1;
  --rule: #2a2724;
  max-width: 1120px;
  margin: 24px auto 90px;
  padding: 40px 48px 32px;
  box-sizing: border-box;
  color: #2a2724;
  background:
    radial-gradient(circle at 20% 0%, rgba(255, 255, 255, 0.8), transparent 40%), var(--paper);
  border-radius: 4px;
  box-shadow:
    0 1px 0 rgba(0, 0, 0, 0.04),
    0 24px 60px -30px rgba(60, 40, 20, 0.45);
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif;
}
html[data-mower-theme='dark'] .score {
  --paper: #1d1c1a;
  --rule: #d8d2c6;
  color: #e9e4d8;
}
.score-head {
  text-align: center;
  margin-bottom: 18px;
}
.score-head h1 {
  margin: 4px 0 14px;
  font-size: 40px;
  font-weight: 700;
  letter-spacing: 0.3em;
}
.score-sub {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.2em;
  opacity: 0.6;
}
.score-meta {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.score-meta button {
  border: 0;
  padding: 4px 8px;
  border-radius: 6px;
  font: inherit;
  color: inherit;
  background: none;
  cursor: pointer;
}
.score-meta button:hover {
  background: rgba(0, 0, 0, 0.05);
}
.score-instrument {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 15px;
}
.score-instrument small {
  opacity: 0.55;
}
.score-tempo {
  font-size: 16px;
  font-weight: 700;
}
.score-tempo i {
  margin-right: 8px;
}
.is-on {
  outline: 2px solid color-mix(in srgb, var(--mower-primary) 60%, transparent);
  outline-offset: 2px;
}
.score-system {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  column-gap: 12px;
  align-items: start;
  padding: 10px 0;
}
.score-part {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 28px;
  text-align: right;
}
.score-part b {
  font-size: 17px;
}
.score-part b::after {
  content: '';
  display: block;
  height: 3px;
  margin: 4px 0 0 auto;
  width: 28px;
  border-radius: 2px;
  background: var(--c);
}
.score-part small {
  font-family: system-ui, sans-serif;
  font-size: 11px;
  line-height: 1.4;
  opacity: 0.6;
}
.score-staff-wrap {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
}
.score-staff {
  display: block;
}
.score-staff line {
  stroke: var(--rule);
  stroke-width: 1;
  opacity: 0.7;
}
.score-clef {
  font-size: 56px;
  fill: var(--rule);
}
.score-mark {
  font-size: 13px;
  font-style: italic;
  fill: var(--rule);
  opacity: 0.75;
}
.score-repeat {
  font-size: 30px;
  font-weight: 700;
  fill: var(--rule);
}
.score-staff .score-stem {
  stroke: var(--c);
  stroke-width: 2.2;
  opacity: 1;
}
.score-head-dot {
  fill: var(--c);
  transform: rotate(-20deg);
  transform-box: fill-box;
}
.score-rest {
  font-size: 34px;
  fill: var(--rule);
  opacity: 0.45;
}
.score-lyric {
  font-size: 14px;
  text-anchor: middle;
  fill: var(--rule);
}
.score-lyric.is-off {
  opacity: 0.4;
}
.score-staff .score-bar {
  stroke-width: 1.5;
  opacity: 1;
}
.score-bar-thick {
  fill: var(--rule);
}
.score-hit {
  position: absolute;
  top: 0;
  width: 48px;
  height: 110px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
}
.score-hit:hover,
.score-hit:focus-visible {
  outline: none;
  background: rgba(0, 0, 0, 0.05);
}
.score-hit.is-on {
  background: color-mix(in srgb, var(--mower-primary) 12%, transparent);
}
.score-ins {
  position: absolute;
  top: 2px;
  width: 20px;
  height: 20px;
  transform: translateX(-50%);
  border: 0;
  border-radius: 50%;
  font-size: 13px;
  line-height: 20px;
  color: var(--c);
  background: var(--paper);
  box-shadow: inset 0 0 0 1.5px var(--c);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.score-staff-wrap:hover .score-ins,
.score-ins:focus-visible {
  opacity: 1;
  outline: none;
}
.score-fermata {
  position: absolute;
  top: -10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translateX(-50%);
  border: 0;
  font: inherit;
  color: inherit;
  background: none;
  cursor: pointer;
}
.score-fermata span {
  font-size: 30px;
  line-height: 1;
}
.score-fermata small {
  font-size: 11px;
  white-space: nowrap;
}
.score-palette {
  grid-column: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 13px;
}
.score-palette button {
  padding: 4px 10px;
  border: 1px dashed currentColor;
  border-radius: 999px;
  font: inherit;
  color: inherit;
  background: none;
  cursor: pointer;
}
.score-palette button:hover {
  background: rgba(0, 0, 0, 0.05);
}
.score-note-card {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 560px;
  margin: 8px 0 4px;
  padding: 14px 16px;
  border-left: 3px solid var(--mower-primary);
  font-family: system-ui, sans-serif;
  background: color-mix(in srgb, var(--paper) 70%, #fff);
  box-shadow: 0 8px 24px -16px rgba(0, 0, 0, 0.4);
}
.score-head .score-note-card {
  margin: 12px auto 0;
  text-align: left;
}
html[data-mower-theme='dark'] .score-note-card {
  background: #26241f;
}
.score-note-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.score-note-title {
  margin: 0;
  font-size: 13px;
}
.score-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.score-foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin-top: 22px;
  padding-top: 14px;
  border-top: 1px solid color-mix(in srgb, var(--rule) 25%, transparent);
  font-size: 13px;
  font-style: italic;
}
.score-foot label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-style: normal;
}
@container main-content (max-width: 760px) {
  .score {
    margin: 0;
    padding: 24px 14px;
  }
  .score-system {
    grid-template-columns: minmax(0, 1fr);
  }
  .score-part {
    padding-top: 0;
    text-align: left;
  }
  .score-part b::after {
    margin-left: 0;
  }
  .score-palette,
  .score-note-card {
    grid-column: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .score-ins {
    transition: none;
  }
}
</style>
