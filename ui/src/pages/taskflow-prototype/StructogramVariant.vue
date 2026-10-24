<script setup>
// PROTOTYPE 变体 G：结构图（Nassi–Shneiderman）。循环画成包住循环体的 ⊐ 形色块，
// 条件画成带判定栏的块；嵌套越深底色越深。点块在块下方展开设置，全局设置是最外层的“前置”块。
import { computed, ref } from 'vue'
import FieldEditor from './FieldEditor.vue'
import { insertTask, removeTask, moveTask, nextRun, fmt, MAA_MARGIN, LONG_MARGIN } from './data'
import { useFlow, idleLabel, pauseLabel, cadenceLabel } from './shared'

const props = defineProps({ state: { type: Object, required: true } })
const s = props.state
const { of, spareOf, gate, reorderable } = useFlow(s)

const open = ref(null)
const toggle = (key) => (open.value = open.value === key ? null : key)

const groups = computed(() => [
  { id: 'daily', title: '日常', cond: '依次执行', note: '顺序由 Mower 固定' },
  {
    id: 'maa',
    title: 'MAA 日常',
    cond: `距上次 ≥ ${s.globals.maaGap} 小时`,
    key: 'gap',
    note: `基建任务前 ${MAA_MARGIN}停下`
  },
  {
    id: 'long',
    title: '长任务',
    cond: `不在 ${pauseLabel(s)}`,
    key: 'pause',
    note: `基建任务前 ${LONG_MARGIN}停下`
  }
])
</script>

<template>
  <section class="ns">
    <header class="ns-head">
      <h1>任务配置</h1>
      <span class="ns-clock">{{ fmt(s.now) }}</span>
    </header>

    <div class="ns-chart">
      <!-- 前置：全局设置 -->
      <div class="ns-pre">
        <button
          type="button"
          class="ns-cell"
          :class="{ 'is-open': open === 'device' }"
          @click="toggle('device')"
        >
          <span class="ns-k">连接</span>
          <span class="ns-v">{{ s.globals.device.name }}</span>
          <span class="ns-m"
            >{{ s.globals.device.adb }} · {{ s.globals.device.fields[0].value }} /
            {{ s.globals.device.fields[1].value }}</span
          >
        </button>
        <button
          type="button"
          class="ns-cell"
          :class="{ 'is-open': open === 'pace' }"
          @click="toggle('pace')"
        >
          <span class="ns-k">节奏</span>
          <span class="ns-v">截图 {{ s.globals.pace.fields[0].value }} 毫秒</span>
          <span class="ns-m"
            >轮询 {{ s.globals.pace.fields[1].value }} 毫秒 · 切换超时
            {{ s.globals.pace.fields[2].value }} 秒</span
          >
        </button>
      </div>
      <div v-if="open === 'device' || open === 'pace'" class="ns-drawer ns-drawer--d0">
        <FieldEditor
          :fields="open === 'device' ? s.globals.device.fields : s.globals.pace.fields"
        />
      </div>

      <!-- 外层循环 -->
      <div class="ns-loop ns-d1">
        <div class="ns-loop-bar">
          <span class="ns-k">重复</span>
          <span class="ns-v">一直运行</span>
        </div>
        <div class="ns-loop-body">
          <div class="ns-block ns-d1">
            <div class="ns-block-title">
              <span class="ns-v">基建队列</span>
              <span class="ns-m">按任务时间取下一项，跑单优先</span>
            </div>
            <div class="ns-tasks">
              <template v-for="t in of('base')" :key="t.id">
                <button
                  type="button"
                  class="ns-task"
                  :class="{ 'is-open': open === t.id, 'is-off': !t.enabled }"
                  @click="toggle(t.id)"
                >
                  {{ t.name }}<small>{{ t.enabled ? nextRun(s, t.id) : '停用' }}</small>
                </button>
              </template>
              <button
                v-for="t in spareOf('base')"
                :key="t.id"
                type="button"
                class="ns-task ns-task--spare"
                @click="(insertTask(s, t.id, 'base'), (open = t.id))"
              >
                + {{ t.name }}
              </button>
            </div>
            <template v-for="t in of('base')" :key="`d-${t.id}`">
              <div v-if="open === t.id" class="ns-drawer">
                <div class="ns-drawer-head">
                  <b>{{ t.name }}</b>
                  <span class="ns-m">{{ cadenceLabel(s, t) }}</span>
                  <n-switch v-model:value="t.enabled" size="small" />
                </div>
                <FieldEditor :fields="t.fields" />
                <div class="ns-drawer-foot">
                  <span class="ns-m">基建队列按时间排序</span>
                  <n-button size="tiny" quaternary type="error" @click="removeTask(s, t.id)"
                    >移出</n-button
                  >
                </div>
              </div>
            </template>
          </div>

          <!-- 判定：是否进入闲时序列 -->
          <div class="ns-if ns-d1">
            <div class="ns-if-head">
              <svg
                class="ns-if-tri"
                viewBox="0 0 100 40"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <line x1="0" y1="0" x2="82" y2="40" />
                <line x1="100" y1="0" x2="82" y2="40" />
              </svg>
              <span class="ns-if-q"
                >距下一项基建任务 ≥ 9 分钟？<em>现在 {{ gate?.gap }} 分钟</em></span
              >
              <span class="ns-if-yes" :class="{ 'is-live': gate?.open }">是</span>
              <span class="ns-if-no" :class="{ 'is-live': !gate?.open }">否</span>
            </div>
            <div class="ns-if-body">
              <div class="ns-yes ns-d2">
                <div v-for="g in groups" :key="g.id" class="ns-group">
                  <component
                    :is="g.key ? 'button' : 'div'"
                    :type="g.key ? 'button' : undefined"
                    class="ns-group-head"
                    :class="{ 'is-open': g.key && open === g.key, 'is-btn': g.key }"
                    @click="g.key && toggle(g.key)"
                  >
                    <span class="ns-k">{{ g.key ? '若' : '然后' }}</span>
                    <span class="ns-v">{{ g.cond }}</span>
                    <span class="ns-m">{{ g.note }}</span>
                  </component>
                  <div v-if="g.key && open === g.key" class="ns-drawer">
                    <label v-if="g.key === 'gap'" class="ns-field">
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
                    <template v-else>
                      <label
                        v-for="(label, i) in ['停运开始', '停运结束']"
                        :key="label"
                        class="ns-field"
                      >
                        {{ label }}
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
                    </template>
                  </div>
                  <div class="ns-group-body ns-d3">
                    <span class="ns-group-label">{{ g.title }}</span>
                    <ol class="ns-seq">
                      <li v-for="(t, i) in of(g.id)" :key="t.id">
                        <button
                          type="button"
                          class="ns-step"
                          :class="{ 'is-open': open === t.id, 'is-off': !t.enabled }"
                          @click="toggle(t.id)"
                        >
                          <span class="ns-idx">{{ i + 1 }}</span
                          >{{ t.name }}
                        </button>
                        <div v-if="open === t.id" class="ns-drawer ns-drawer--step">
                          <div class="ns-drawer-head">
                            <b>{{ t.name }}</b>
                            <span class="ns-m"
                              >{{ cadenceLabel(s, t) }} · 下次 {{ nextRun(s, t.id) }}</span
                            >
                            <n-switch v-model:value="t.enabled" size="small" />
                          </div>
                          <FieldEditor :fields="t.fields" />
                          <div class="ns-drawer-foot">
                            <template v-if="reorderable(t.section)">
                              <n-button size="tiny" secondary @click="moveTask(s, t.id, -1)"
                                >前移</n-button
                              >
                              <n-button size="tiny" secondary @click="moveTask(s, t.id, 1)"
                                >后移</n-button
                              >
                            </template>
                            <span v-else class="ns-m">顺序固定</span>
                            <n-button
                              size="tiny"
                              quaternary
                              type="error"
                              @click="removeTask(s, t.id)"
                              >移出</n-button
                            >
                          </div>
                        </div>
                      </li>
                      <li v-for="t in spareOf(g.id)" :key="t.id">
                        <button
                          type="button"
                          class="ns-step ns-step--spare"
                          @click="(insertTask(s, t.id, g.id), (open = t.id))"
                        >
                          + {{ t.name }}
                        </button>
                      </li>
                    </ol>
                  </div>
                </div>

                <button
                  type="button"
                  class="ns-group-head is-btn"
                  :class="{ 'is-open': open === 'idle' }"
                  @click="toggle('idle')"
                >
                  <span class="ns-k">然后</span>
                  <span class="ns-v">{{ idleLabel(s) }}</span>
                  <span class="ns-m">空闲动作</span>
                </button>
                <div v-if="open === 'idle'" class="ns-drawer">
                  <n-radio-group v-model:value="s.globals.idle.value" size="small">
                    <n-radio-button
                      v-for="[v, label] in s.globals.idle.options"
                      :key="v"
                      :value="v"
                      >{{ label }}</n-radio-button
                    >
                  </n-radio-group>
                </div>
                <div class="ns-group-head">
                  <span class="ns-k">然后</span>
                  <span class="ns-v">休眠到 {{ gate?.at }}</span>
                  <span class="ns-m">下一项基建任务</span>
                </div>
              </div>
              <div class="ns-no ns-d2">
                <span class="ns-m">继续等基建队列</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ns {
  /* 亮色主题下 --mower-text 为空，原型里先兜底 */
  --tx: var(--mower-text, var(--n-text-color, rgb(31, 34, 37)));
  --tx-m: var(--mower-text-muted, color-mix(in srgb, var(--tx) 60%, transparent));
  --ns-ink: var(--tx);
  --ns-edge: color-mix(in srgb, var(--tx) 22%, transparent);
  --ns-d0: var(--mower-surface);
  --ns-d1: color-mix(in srgb, var(--mower-primary) 6%, var(--mower-surface));
  --ns-d2: color-mix(in srgb, var(--mower-primary) 11%, var(--mower-surface));
  --ns-d3: color-mix(in srgb, var(--mower-primary) 17%, var(--mower-surface));
  --ns-mono: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  max-width: 1080px;
  margin: 0 auto;
  padding: 36px 28px 110px;
  color: var(--ns-ink);
}
.ns-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 18px;
}
.ns-head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}
.ns-clock {
  font: 13px var(--ns-mono);
  color: var(--tx-m);
}
.ns-chart {
  border: 1px solid var(--ns-edge);
  background: var(--ns-d0);
}
.ns-d1 {
  background: var(--ns-d1);
}
.ns-d2 {
  background: var(--ns-d2);
}
.ns-d3 {
  background: var(--ns-d3);
}
.ns-k {
  font: 600 11px var(--ns-mono);
  letter-spacing: 0.05em;
  color: var(--mower-primary);
}
.ns-v {
  font-size: 14px;
  font-weight: 500;
}
.ns-m {
  font-size: 12px;
  color: var(--tx-m);
}
button {
  box-sizing: border-box;
  font: inherit;
  color: inherit;
}

/* 前置块 */
.ns-pre {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.ns-cell {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 2px 8px;
  padding: 12px 16px;
  border: 0;
  border-bottom: 1px solid var(--ns-edge);
  text-align: left;
  background: none;
  cursor: pointer;
}
.ns-cell + .ns-cell {
  border-left: 1px solid var(--ns-edge);
}
.ns-cell .ns-k {
  grid-row: span 2;
  line-height: 20px;
}

/* ⊐ 形循环：左侧竖条 + 顶部横条包住循环体 */
.ns-loop {
  display: grid;
  grid-template-columns: 112px 1fr;
}
.ns-loop-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-right: 1px solid var(--ns-edge);
}
.ns-loop-body {
  min-width: 0;
  margin-bottom: 26px;
  border-bottom: 1px solid var(--ns-edge);
}
.ns-block {
  padding: 12px 16px 14px;
  border-bottom: 1px solid var(--ns-edge);
}
.ns-block-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}
.ns-tasks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ns-task {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 12px;
  border: 1px solid var(--ns-edge);
  border-radius: 4px;
  font-size: 13px;
  background: var(--ns-d0);
  cursor: pointer;
  transition: border-color 160ms cubic-bezier(0.32, 0.72, 0, 1);
}
.ns-task small {
  font: 11px var(--ns-mono);
  color: var(--tx-m);
}
.ns-task--spare,
.ns-step--spare {
  border-style: dashed;
  color: var(--tx-m);
  background: transparent;
}
.ns-task:hover,
.ns-task.is-open {
  border-color: var(--mower-primary);
}
.is-off {
  color: var(--tx-m);
  text-decoration: line-through;
}

/* 判定块 */
.ns-if-head {
  position: relative;
  display: grid;
  grid-template-columns: 82fr 18fr;
  height: 64px;
  border-bottom: 1px solid var(--ns-edge);
}
.ns-if-tri {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  stroke: var(--ns-edge);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.ns-if-tri line {
  vector-effect: non-scaling-stroke;
}
.ns-if-q {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}
.ns-if-q em {
  margin-left: 10px;
  font: normal 11px var(--ns-mono);
  color: var(--tx-m);
}
.ns-if-yes,
.ns-if-no {
  align-self: end;
  padding: 0 14px 6px;
  font: 600 12px var(--ns-mono);
  color: var(--tx-m);
}
.ns-if-no {
  text-align: right;
}
.is-live {
  color: var(--mower-primary);
}
.ns-if-body {
  display: grid;
  grid-template-columns: 82fr 18fr;
}
.ns-no {
  display: flex;
  align-items: center;
  justify-content: center;
  border-left: 1px solid var(--ns-edge);
}
.ns-group-head {
  display: grid;
  grid-template-columns: 44px auto 1fr;
  align-items: baseline;
  gap: 10px;
  width: 100%;
  padding: 10px 16px;
  border: 0;
  border-bottom: 1px solid var(--ns-edge);
  text-align: left;
  background: none;
}
.ns-group-head .ns-m {
  justify-self: end;
}
.ns-group-head.is-btn {
  cursor: pointer;
}
.ns-group-head.is-btn:hover,
.ns-cell:hover,
.ns-step:hover {
  background: color-mix(in srgb, var(--tx) 5%, transparent);
}
.is-open.ns-group-head,
.is-open.ns-cell {
  box-shadow: inset 3px 0 0 var(--mower-primary);
}
.ns-group-body {
  display: grid;
  grid-template-columns: 112px 1fr;
  margin-left: 44px;
  border-left: 1px solid var(--ns-edge);
  border-bottom: 1px solid var(--ns-edge);
}
.ns-group-label {
  padding: 10px 14px;
  font-size: 12.5px;
  font-weight: 600;
}
.ns-seq {
  margin: 0;
  padding: 0;
  list-style: none;
}
.ns-seq li + li {
  border-top: 1px solid color-mix(in srgb, var(--tx) 9%, transparent);
}
.ns-step {
  display: flex;
  align-items: baseline;
  gap: 10px;
  width: 100%;
  padding: 7px 14px;
  border: 0;
  font-size: 13px;
  text-align: left;
  background: none;
  cursor: pointer;
}
.ns-step.is-open {
  box-shadow: inset 3px 0 0 var(--mower-primary);
}
.ns-idx {
  width: 14px;
  font: 11px var(--ns-mono);
  color: var(--tx-m);
}

/* 抽屉：就地展开的设置 */
.ns-drawer {
  box-sizing: border-box;
  max-width: 560px;
  margin: 10px 16px 14px;
  padding: 14px 16px;
  border: 1px solid var(--ns-edge);
  border-radius: 6px;
  background: var(--ns-d0);
  box-shadow: 0 12px 32px -18px color-mix(in srgb, var(--tx) 40%, transparent);
  animation: ns-in 220ms cubic-bezier(0.32, 0.72, 0, 1);
}
.ns-drawer--d0 {
  margin-top: 12px;
}
.ns-drawer--step {
  margin: 4px 14px 12px;
}
@keyframes ns-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
}
.ns-drawer-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.ns-drawer-head .n-switch {
  margin-left: auto;
}
.ns-drawer-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--ns-edge);
}
.ns-drawer-foot > :last-child {
  margin-left: auto;
}
.ns-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.ns-field + .ns-field {
  margin-top: 10px;
}
@media (prefers-reduced-motion: reduce) {
  .ns-drawer {
    animation: none;
  }
}
@media (max-width: 760px) {
  .ns-pre,
  .ns-if-body {
    grid-template-columns: 1fr;
  }
  .ns-loop {
    grid-template-columns: 44px 1fr;
  }
  .ns-loop-bar .ns-v {
    display: none;
  }
  .ns-no {
    display: none;
  }
  .ns-group-body {
    grid-template-columns: 1fr;
    margin-left: 0;
  }
}
</style>
