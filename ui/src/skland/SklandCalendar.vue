<script setup>
import { computed, nextTick, ref } from 'vue'
import AlertCircleOutline from '@vicons/ionicons5/es/AlertCircleOutline'
import CheckmarkSharp from '@vicons/ionicons5/es/CheckmarkSharp'
import GiftOutline from '@vicons/ionicons5/es/GiftOutline'
import SklandRewardArt from './SklandRewardArt.vue'
import SklandRewardIcon from './SklandRewardIcon.vue'
import { formatDateShort, formatMonthDayCN, number, SIGNED_OUTCOMES } from './statistics'

const props = defineProps({
  month: { type: String, required: true },
  today: { type: String, required: true },
  signIn: { type: Object, default: null },
  game: { type: String, default: '' },
  selectedIndex: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  detailView: { type: String, default: 'day' },
  failureCount: { type: Number, default: 0 },
  failureEntry: { type: Object, default: null }
})

const emit = defineEmits(['select', 'update:detail-view'])
const grid = ref(null)
const rewardLimit = 2
const detailViews = [
  { key: 'day', label: '签到详情' },
  { key: 'rewards', label: '月度奖励' },
  { key: 'failures', label: '失败记录' }
]
const STATE_LABELS = {
  claimed: '已领取',
  upcoming: '待领取',
  unreachable: '本月领不到',
  unclaimed: '月底未领取'
}

const slots = computed(() => props.signIn?.slots || [])
// 读取中还没有签到格时，按本月天数画出带序号的占位格，奖励图标的位置是占位块，
// 读完后图标出现在同样的位置。
const placeholderDays = computed(() => {
  const [year, month] = props.month.split('-').map(Number)
  return new Date(year, month, 0).getDate() || 0
})
const selected = computed(() => slots.value.find((slot) => slot.index === props.selectedIndex))
const todayFailed = computed(
  () => !props.signIn?.todaySigned && Boolean(props.signIn?.todayRecord?.hasFailure)
)
const selectedPosition = computed(() =>
  slots.value.findIndex((slot) => slot.index === props.selectedIndex)
)

/**
 * 参照游戏内签到页：选中格子周围一圈的格子亮起细线，离选中格越远越淡。
 * 返回选中格相对这一格偏移几列几行，供细线的渐隐中心定位。
 */
const nearOffsets = computed(() => {
  const selected = selectedPosition.value
  return slots.value.map((_, position) => {
    if (selected < 0 || position === selected) return null
    const x = (selected % 7) - (position % 7)
    const y = Math.floor(selected / 7) - Math.floor(position / 7)
    return Math.abs(x) <= 1 && Math.abs(y) <= 1 ? { '--near-x': x, '--near-y': y } : null
  })
})

function rewardLabel(reward) {
  return `${reward.item} ×${number(reward.count)}`
}

function stateLabel(slot) {
  if (slot.state !== 'today') return STATE_LABELS[slot.state] || ''
  if (slot.claimed) return '今日已领取'
  if (todayFailed.value) return '今日签到失败'
  return slot.placeholder ? '' : '今日可领取'
}

function slotLabel(slot) {
  const rewards = slot.rewards.length ? slot.rewards.map(rewardLabel).join('、') : '奖励未知'
  const date = slot.claimed && slot.date ? `，${formatMonthDayCN(slot.date)}签到` : ''
  const state = stateLabel(slot)
  const label = props.signIn?.source === 'local' ? '本机签到记录' : `第 ${slot.index} 格奖励`
  return `${label}，${rewards}${state ? `，${state}` : ''}${date}`
}

function dateText(slot) {
  if (slot.claimed) {
    if (!slot.date) return ''
    const suffix = slot.date === props.today ? '（今天）' : ''
    const elsewhere = slot.record?.outcome === 'repeated' ? '，当天已在其他地方签到' : ''
    return `${formatDateShort(slot.date, props.today)}${suffix}签到领取${elsewhere}。`
  }
  if (slot.state === 'today') {
    if (todayFailed.value) {
      return slot.placeholder ? '' : '今天的签到还没有成功，成功后领取这一格。'
    }
    return slot.placeholder ? '' : '今天签到即可领取。'
  }
  if (slot.state === 'upcoming' && slot.date) {
    return `之后每天签到，预计 ${formatMonthDayCN(slot.date)} 领取。`
  }
  return slot.state === 'unclaimed' ? '这个月的签到没有走到这一格。' : ''
}

function failureText(record) {
  const messages = record.failedMessages.join('、') || '未返回失败信息'
  const attempts = number(record.failedAttempts || 1)
  if (SIGNED_OUTCOMES.includes(record.outcome))
    return `失败 ${attempts} 次 · 当天已签到 · ${messages}`
  return record.failedAttempts > 1 ? `失败 ${attempts} 次 · ${messages}` : messages
}

function selectSlot(index) {
  emit('select', index)
}

async function onGridKeydown(event) {
  if (!event.target.dataset.slot || event.altKey || event.ctrlKey || event.metaKey) return
  const offsets = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
  const indexes = slots.value.map((slot) => slot.index)
  const position = indexes.indexOf(Number(event.target.dataset.slot))
  let target
  if (event.key in offsets) target = position + offsets[event.key]
  else if (event.key === 'Home') target = 0
  else if (event.key === 'End') target = indexes.length - 1
  else return
  event.preventDefault()
  target = indexes[Math.min(indexes.length - 1, Math.max(0, target))]
  selectSlot(target)
  await nextTick()
  grid.value?.querySelector(`button[data-slot="${target}"]`)?.focus()
}
</script>

<template>
  <div class="calendar-layout">
    <div class="calendar-main">
      <ol
        v-if="slots.length"
        ref="grid"
        class="slot-grid"
        aria-label="签到日历"
        @keydown="onGridKeydown"
      >
        <li v-for="(slot, position) in slots" :key="slot.index">
          <button
            type="button"
            class="sign-slot"
            :class="[
              `is-${slot.state}`,
              {
                'is-claimed': slot.claimed,
                'is-failed': slot.state === 'today' && todayFailed,
                'is-near': nearOffsets[position]
              }
            ]"
            :style="nearOffsets[position]"
            :data-slot="slot.index"
            :aria-label="slotLabel(slot)"
            :aria-pressed="slot.index === selectedIndex"
            :aria-current="slot.state === 'today' ? 'date' : undefined"
            :tabindex="slot.index === (selectedIndex ?? slots[0]?.index) ? 0 : -1"
            @click="selectSlot(slot.index)"
          >
            <span class="sign-slot__number" aria-hidden="true">{{ slot.index }}</span>
            <span v-if="slot.state === 'today' && todayFailed" class="sign-slot__corner">
              <n-icon
                :component="AlertCircleOutline"
                class="sign-slot__failure"
                aria-hidden="true"
              />
            </span>
            <span v-if="slot.rewards.length" class="sign-slot__rewards" aria-hidden="true">
              <span
                v-for="reward in slot.rewards.slice(0, rewardLimit)"
                :key="`${reward.item}×${reward.count}`"
                class="sign-slot__reward"
                :title="rewardLabel(reward)"
              >
                <SklandRewardIcon class="sign-slot__icon" :game="game" :item="reward.item">
                  <GiftOutline class="sign-slot__icon sign-slot__fallback" />
                </SklandRewardIcon>
                <span class="sign-slot__quantity">{{ number(reward.count) }}</span>
              </span>
              <span
                v-if="slot.rewards.length > rewardLimit"
                class="sign-slot__more"
                :title="`另有 ${slot.rewards.length - rewardLimit} 项奖励`"
              >
                +{{ slot.rewards.length - rewardLimit }}
              </span>
            </span>
            <span v-else class="sign-slot__unknown" aria-hidden="true"><GiftOutline /></span>
            <span v-if="slot.claimed" class="sign-slot__check" aria-hidden="true">
              <n-icon :component="CheckmarkSharp" />
            </span>
          </button>
        </li>
      </ol>
      <ol v-else-if="loading" class="slot-grid" aria-hidden="true">
        <li v-for="index in placeholderDays" :key="index">
          <span class="sign-slot is-placeholder">
            <span class="sign-slot__number">{{ index }}</span>
            <span class="sign-slot__rewards"
              ><span class="skeleton-bone sign-slot__placeholder"
            /></span>
          </span>
        </li>
      </ol>
    </div>

    <aside class="calendar-detail" aria-label="签到明细" :aria-busy="!signIn && loading">
      <slot name="channels" />
      <div class="calendar-detail__views" role="group" aria-label="明细视图">
        <button
          v-for="view in detailViews"
          :key="view.key"
          type="button"
          :aria-pressed="detailView === view.key"
          @click="emit('update:detail-view', view.key)"
        >
          {{ view.label }}
          <span v-if="view.key === 'failures' && failureCount">{{ number(failureCount) }}</span>
        </button>
      </div>
      <section
        v-if="detailView === 'day'"
        class="calendar-detail__groups slot-detail"
        aria-label="签到详情"
        aria-live="polite"
      >
        <template v-if="failureEntry">
          <header class="slot-detail__header">
            <h2>{{ formatDateShort(failureEntry.date, today) }}签到失败</h2>
            <span v-if="failureEntry.recovered" class="slot-detail__state is-claimed">
              {{ failureEntry.accountFailure ? '当天已读到签到角色' : '当天已签到' }}
            </span>
          </header>
          <p class="slot-detail__date">
            {{ failureEntry.account }}
            <template v-if="failureEntry.game"> · {{ failureEntry.game }}</template>
            <template v-if="failureEntry.roleName"> · {{ failureEntry.roleName }}</template>
          </p>
          <p class="slot-detail__failure">
            失败 {{ number(failureEntry.attempts) }} 次 ·
            {{ failureEntry.messages.join('、') || '未返回失败信息' }}
          </p>
          <slot v-if="failureEntry.pending" name="retry" />
        </template>
        <template v-else-if="selected">
          <header class="slot-detail__header">
            <h2 v-if="signIn?.source === 'local'">本机签到记录</h2>
            <h2 v-else>第 {{ selected.index }} 格奖励</h2>
            <span
              v-if="stateLabel(selected)"
              class="slot-detail__state"
              :class="`is-${selected.state}`"
            >
              {{ stateLabel(selected) }}
            </span>
          </header>
          <ul v-if="selected.rewards.length" class="slot-detail__rewards" aria-label="签到奖励">
            <li
              v-for="reward in selected.rewards"
              :key="`${reward.item}×${reward.count}`"
              :title="rewardLabel(reward)"
            >
              <SklandRewardArt class="slot-detail__art" :game="game" :item="reward.item" />
              <span class="slot-detail__name">{{ reward.item }}</span>
              <strong class="slot-detail__count">×{{ number(reward.count) }}</strong>
            </li>
          </ul>
          <p v-else-if="selected.claimed" class="slot-detail__note">这次签到没有奖励明细。</p>
          <p v-if="dateText(selected)" class="slot-detail__date">{{ dateText(selected) }}</p>
          <p v-if="selected.record?.hasFailure" class="slot-detail__failure">
            {{ failureText(selected.record) }}
          </p>
          <slot v-if="selected.state === 'today' && todayFailed" name="retry" />
        </template>
        <template v-else-if="loading && !signIn">
          <header class="slot-detail__header">
            <h2><span class="skeleton-bone skeleton-text" style="--skeleton-w: 5.5em" /></h2>
          </header>
          <ul class="slot-detail__rewards" aria-hidden="true">
            <li>
              <span class="skeleton-bone slot-detail__art-placeholder" />
              <span class="slot-detail__name"
                ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 4em"
              /></span>
              <strong class="slot-detail__count"
                ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 2.4em"
              /></strong>
            </li>
          </ul>
        </template>
        <p v-else class="slot-detail__note" role="status">
          {{ loading ? '正在读取签到记录…' : '这个渠道本月还没有签到记录' }}
        </p>
      </section>
      <div v-else class="calendar-detail__groups calendar-detail__monthly">
        <slot v-if="detailView === 'rewards'" name="rewards" />
        <slot v-else name="failures" />
      </div>
    </aside>
  </div>
</template>

<style scoped>
.calendar-layout {
  --stage-today: #f1d27d;
  --stage-claimed-opacity: 0.62;
  --stage-quantity: color-mix(in srgb, #141416 72%, var(--mower-surface));
  display: grid;
  grid-template-columns: minmax(0, 2.35fr) minmax(305px, 1fr);
  gap: 18px;
}
.calendar-layout:where(html[data-mower-theme='dark'] *) {
  --stage-today: #9b7505;
  --stage-today-number-opacity: 1;
  --stage-claimed-opacity: 0.44;
  --stage-quantity: color-mix(in srgb, var(--mower-text) 12%, var(--mower-surface));
}
.calendar-main {
  min-width: 0;
  container: skland-calendar / inline-size;
}
/*
 * 参照游戏内签到页的布局：格子不画卡片，序号是图标后方的大号淡色数字。
 * 底板和线条颜色跟随亮色、暗色主题，不照搬游戏的深色背景。
 */
.slot-grid {
  --slot-gap: 6px;
  --stage-line: color-mix(in srgb, var(--mower-text) 55%, transparent);
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: var(--slot-gap);
  margin: 0;
  padding: 12px;
  border-radius: var(--skland-inner-radius, 12px);
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-control-surface);
  color: var(--mower-text);
  list-style: none;
  font-variant-numeric: tabular-nums;
}
/*
 * 待领取的图标保持原色，已领取的图标降低不透明度并叠上白勾。
 * 今天对应的格子有金色底色，本月领不到或月底未领取的格子只剩淡影。
 */
.sign-slot {
  --reward-size: clamp(28px, 8.4cqi, 72px);
  position: relative;
  display: block;
  isolation: isolate;
  width: 100%;
  height: clamp(58px, 12.4cqi, 104px);
  padding: 0;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.sign-slot::before {
  content: '';
  position: absolute;
  z-index: 0;
  inset: 6px;
  border-radius: 1px;
  opacity: 0;
}
.sign-slot.is-today::before {
  background: var(--stage-today);
  opacity: 1;
}
.sign-slot.is-today.is-failed::before {
  background: color-mix(in srgb, var(--mower-error) 30%, var(--mower-surface));
}
.sign-slot:is(.is-unreachable, .is-unclaimed)::before {
  opacity: 1;
  background: repeating-linear-gradient(
    135deg,
    transparent 0 5px,
    color-mix(in srgb, var(--stage-line) 32%, transparent) 5px 6px
  );
  pointer-events: none;
}
/*
 * 选中格是白色粗框；周围一圈格子各有一个细框，以选中格中心做径向渐隐，越远越淡。
 */
.sign-slot::after {
  content: '';
  position: absolute;
  z-index: 5;
  inset: 0;
  border: 1px solid var(--stage-line);
  border-radius: 2px;
  opacity: 0;
  pointer-events: none;
}
.sign-slot:hover::after {
  opacity: 0.4;
}
.sign-slot.is-near::after {
  --near-mask: radial-gradient(
    180% 180% at calc(50% + var(--near-x) * (100% + var(--slot-gap)))
      calc(50% + var(--near-y) * (100% + var(--slot-gap))),
    #000 38%,
    transparent 100%
  );
  opacity: 1;
  -webkit-mask-image: var(--near-mask);
  mask-image: var(--near-mask);
}
.sign-slot[aria-pressed='true']::after {
  border: 3px solid var(--mower-text);
  opacity: 1;
}
.sign-slot:focus-visible,
.calendar-detail__groups:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
.sign-slot__number {
  position: absolute;
  z-index: 1;
  inset: 3px auto auto 8px;
  color: color-mix(in srgb, var(--mower-text) 38%, var(--mower-control-surface));
  font-size: clamp(24px, 6.2cqi, 54px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
  opacity: 0.72;
  pointer-events: none;
}
.sign-slot.is-claimed .sign-slot__number {
  z-index: 3;
  opacity: 0.52;
}
.sign-slot.is-unreachable .sign-slot__number,
.sign-slot.is-unclaimed .sign-slot__number {
  opacity: 0.4;
}
.sign-slot.is-today .sign-slot__number,
.sign-slot[aria-pressed='true'] .sign-slot__number {
  color: var(--mower-text);
  opacity: 0.78;
}
.sign-slot.is-today .sign-slot__number {
  opacity: var(--stage-today-number-opacity, 0.78);
}
.sign-slot.is-placeholder {
  cursor: default;
}
.sign-slot.is-placeholder::after {
  display: none;
}
.sign-slot__placeholder {
  width: var(--reward-size);
  height: var(--reward-size);
  border-radius: calc(8px * var(--mower-corner-scale));
}
.sign-slot__corner {
  position: absolute;
  z-index: 4;
  inset: 8px 8px auto auto;
  display: flex;
}
.sign-slot__failure {
  color: var(--mower-error-text, var(--mower-error));
  font-size: clamp(15px, 2.4cqi, 19px);
}
.sign-slot__rewards {
  position: absolute;
  z-index: 2;
  inset: auto 8px 9px 12px;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 3px;
  min-width: 0;
}
.sign-slot__reward {
  position: relative;
  display: grid;
  flex: 0 1 auto;
  justify-items: center;
  align-content: end;
  min-width: 0;
}
.sign-slot__icon {
  width: 100%;
  max-width: var(--reward-size);
  height: var(--reward-size);
  object-fit: contain;
}
.sign-slot__fallback {
  width: var(--reward-size);
  max-width: 100%;
  padding: 16%;
  color: color-mix(in srgb, var(--mower-text) 46%, transparent);
}
.sign-slot.is-claimed .sign-slot__icon {
  opacity: var(--stage-claimed-opacity);
  filter: saturate(0.85);
}
.sign-slot.is-unreachable .sign-slot__rewards,
.sign-slot.is-unclaimed .sign-slot__rewards {
  opacity: 0.3;
  filter: grayscale(1);
}
.sign-slot__quantity {
  position: absolute;
  z-index: 1;
  inset: auto -5px -2px auto;
  min-width: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--stage-quantity);
  color: #fff;
  font-size: 11px;
  font-weight: 650;
  line-height: 18px;
  text-align: center;
  white-space: nowrap;
}
.sign-slot.is-claimed .sign-slot__quantity {
  background: color-mix(in srgb, var(--stage-quantity) 86%, var(--mower-surface));
}
.sign-slot__more {
  position: absolute;
  z-index: 2;
  inset-inline-end: -3px;
  inset-block-start: -6px;
  padding: 0 4px;
  border-radius: calc(5px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-text) 14%, var(--mower-surface));
  color: var(--mower-text);
  font-size: 11px;
  font-weight: 650;
  line-height: 16px;
}
.sign-slot__unknown {
  position: absolute;
  z-index: 2;
  inset: auto 0 12px;
  color: color-mix(in srgb, var(--mower-text) 40%, transparent);
  font-size: clamp(16px, 3.6cqi, 28px);
  font-weight: 700;
  text-align: center;
}
.sign-slot__unknown svg {
  width: 1em;
  height: 1em;
}
@media (prefers-reduced-motion: no-preference) {
  .sign-slot[aria-pressed='true']::after {
    animation: sign-slot-select 160ms ease-out;
  }
  @keyframes sign-slot-select {
    from {
      opacity: 0.4;
    }
  }
  .sign-slot__rewards,
  .sign-slot__unknown {
    transition: transform 160ms ease-out;
  }
  .sign-slot:active :is(.sign-slot__rewards, .sign-slot__unknown) {
    transform: scale(0.97);
    transition-duration: 70ms;
  }
}
.sign-slot__check {
  position: absolute;
  z-index: 4;
  inset-block-start: 67%;
  inset-inline-start: 52%;
  display: flex;
  color: #fff;
  font-size: clamp(24px, 5.4cqi, 42px);
  filter: drop-shadow(0 1px 2px rgb(0 0 0 / 75%));
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.sign-slot__check :deep(path) {
  stroke-width: 64;
}
.calendar-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--mower-divider);
  border-radius: calc(10px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: var(--mower-control-surface);
  contain: size;
}
.calendar-detail__views {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
  flex: none;
  padding: 5px;
  border-bottom: 1px solid var(--mower-divider);
}
.calendar-detail__views button {
  min-height: 32px;
  padding: 5px 2px;
  border: 0;
  border-radius: calc(5px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: transparent;
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}
.calendar-detail__views button:hover {
  color: var(--mower-text);
}
.calendar-detail__views button[aria-pressed='true'] {
  background: var(--mower-surface);
  color: var(--mower-text);
  font-weight: 650;
}
.calendar-detail__views button span {
  margin-left: 3px;
  color: var(--mower-error-text, var(--mower-error));
  font-variant-numeric: tabular-nums;
}
.calendar-detail__groups {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  scrollbar-width: thin;
}
.slot-detail__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.slot-detail__header h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
}
.slot-detail__state {
  padding: 0 7px;
  border-radius: calc(9px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-text) 8%, transparent);
  color: var(--mower-text-muted);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
}
.slot-detail__state.is-today {
  background: color-mix(in srgb, var(--stage-today) 36%, transparent);
  color: var(--mower-text);
}
.slot-detail__state.is-claimed {
  background: color-mix(in srgb, var(--mower-success) 14%, transparent);
  color: var(--mower-success-text, var(--mower-success));
}
.slot-detail__rewards {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}
/* 参照游戏内右栏：大图标在左，物品名和数量在右。 */
.slot-detail__rewards li {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding-right: 8px;
  border-radius: calc(8px * var(--mower-corner-scale));
  corner-shape: var(--mower-corner-shape);
  background: color-mix(in srgb, var(--mower-text) 5%, transparent);
}
.slot-detail__art-placeholder {
  aspect-ratio: 1;
  border-radius: calc(7px * var(--mower-corner-scale));
}
.slot-detail__name {
  overflow-wrap: anywhere;
  font-size: 14px;
  font-weight: 600;
}
.slot-detail__count {
  font-size: 15px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.slot-detail__date,
.slot-detail__note {
  margin: 9px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
}
.slot-detail__note {
  color: var(--skland-muted);
}
.slot-detail__failure {
  margin: 4px 0 0;
  color: var(--mower-error-text, var(--mower-error));
  font-size: 12px;
}
@container main-content (max-width: 740px) {
  .calendar-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .calendar-detail {
    contain: none;
  }
  .calendar-detail__groups {
    overflow: visible;
  }
}
@container skland-calendar (max-width: 480px) {
  .slot-grid {
    --slot-gap: 4px;
    padding: 6px;
  }
  .sign-slot {
    --reward-size: clamp(21px, 7.7cqi, 35px);
  }
  .sign-slot::before {
    inset: 3px;
  }
  .sign-slot[aria-pressed='true']::after {
    border-width: 2px;
  }
  .sign-slot__number {
    inset-inline-start: 3px;
    font-size: clamp(19px, 6.6cqi, 30px);
  }
  .sign-slot__rewards {
    inset: auto 2px 4px;
    gap: 2px;
  }
  .sign-slot__corner {
    inset: 4px 4px auto auto;
  }
  .sign-slot__quantity {
    display: none;
  }
  .sign-slot__more {
    padding: 0 2px;
    font-size: 10px;
    line-height: 12px;
  }
  .sign-slot__failure {
    font-size: 13px;
  }
}
</style>
