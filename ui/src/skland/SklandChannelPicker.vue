<script setup>
import { computed } from 'vue'
import SkeletonField from '@/components/SkeletonField.vue'
import { channelChipLabel } from './statistics'

const props = defineProps({
  channels: { type: Array, required: true },
  selected: { type: Object, default: null },
  // 读取中按上次读到的版面占位：select 表示有多个账号、要显示账号选择框，chips 是所选账号各渠道
  // 名称的宽度（em）。渠道按钮的框照常显示，账号和渠道名先占位。传 true 时按两个账号、两个渠道
  // 占位。
  placeholder: { type: [Boolean, Object], default: false }
})
const placeholderShape = computed(() => {
  if (!props.placeholder) return null
  const chips = props.placeholder === true ? 2 : props.placeholder.chips
  return {
    select: props.placeholder === true || Boolean(props.placeholder.select),
    chips: (Array.isArray(chips) ? chips : Array(Math.max(Number(chips) || 0, 0)).fill(5.6))
      .slice(0, 8)
      .map((width) => Math.min(Math.max(Number(width) || 0, 1), 16))
  }
})
const emit = defineEmits(['select'])

const STATUS_LABELS = {
  signed: '今天已签到',
  failed: '今天签到失败',
  pending: '今天尚未签到',
  stale: '近期无记录'
}

const accounts = computed(() => [...new Set(props.channels.map((channel) => channel.account))])
const accountOptions = computed(() =>
  accounts.value.map((account) => {
    const failed = props.channels.filter(
      (channel) => channel.account === account && channel.status === 'failed'
    ).length
    return { label: failed ? `${account} · ${failed} 个失败` : account, value: account }
  })
)
const accountChannels = computed(() =>
  props.channels.filter((channel) => channel.account === props.selected?.account)
)
const attention = computed(() =>
  props.channels.filter(
    (channel) => channel.status === 'failed' && channel.key !== props.selected?.key
  )
)

function pickAccount(account) {
  const channel =
    props.channels.find((item) => item.account === account && item.status === 'failed') ||
    props.channels.find((item) => item.account === account)
  if (channel) emit('select', channel.key)
}

const chipLabel = channelChipLabel

function chipTitle(channel) {
  return [channel.display_name, STATUS_LABELS[channel.status]].filter(Boolean).join(' · ')
}
</script>

<template>
  <div class="channel-picker">
    <div class="channel-picker__account">
      <template v-if="placeholderShape">
        <SkeletonField
          v-if="placeholderShape.select"
          kind="select"
          size="small"
          class="channel-picker__select"
          width="6em"
        />
        <strong v-else class="channel-picker__single"
          ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 7em"
        /></strong>
      </template>
      <n-select
        v-else-if="accounts.length > 1"
        :value="selected?.account"
        :options="accountOptions"
        class="channel-picker__select"
        size="small"
        filterable
        :consistent-menu-width="false"
        :input-props="{ 'aria-label': '签到账号' }"
        @update:value="pickAccount"
      />
      <strong v-else class="channel-picker__single">{{ selected?.account }}</strong>
    </div>
    <div class="channel-picker__chips" role="group" aria-label="签到渠道">
      <template v-if="placeholderShape">
        <span v-for="(width, index) in placeholderShape.chips" :key="index" class="channel-chip">
          <span class="skeleton-bone skeleton-text" :style="{ '--skeleton-w': `${width}em` }" />
        </span>
      </template>
      <button
        v-for="channel in accountChannels"
        :key="channel.key"
        type="button"
        class="channel-chip"
        :class="`is-${channel.status}`"
        :aria-pressed="channel.key === selected?.key"
        :title="chipTitle(channel)"
        @click="emit('select', channel.key)"
      >
        <span v-if="channel.status === 'failed'" class="channel-chip__dot" aria-hidden="true" />
        {{ chipLabel(channel) }}
        <span v-if="STATUS_LABELS[channel.status]" class="sr-only"
          >，{{ STATUS_LABELS[channel.status] }}</span
        >
      </button>
    </div>
    <p v-if="attention.length" class="channel-picker__alert" role="status">
      <span>另有 {{ attention.length }} 个渠道今天签到失败</span>
      <button type="button" @click="emit('select', attention[0].key)">
        查看 {{ attention[0].account }} {{ chipLabel(attention[0]) }}
      </button>
    </p>
  </div>
</template>

<style scoped>
.channel-picker {
  display: grid;
  gap: 7px;
  flex: none;
  padding: 10px 10px 9px;
  border-bottom: 1px solid var(--mower-divider);
}
.channel-picker__account {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.channel-picker__select {
  flex: 1 1 auto;
  min-width: 0;
}
.channel-picker__single {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.channel-picker__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.channel-chip {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  min-height: 28px;
  padding: 3px 10px 3px 8px;
  overflow: hidden;
  border: 1px solid var(--mower-divider);
  border-radius: 14px;
  background: var(--mower-surface);
  color: var(--mower-text-muted);
  font: inherit;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.channel-chip:hover {
  color: var(--mower-text);
}
.channel-chip[aria-pressed='true'] {
  border-color: #eeb415;
  background: color-mix(in srgb, #eeb415 24%, var(--mower-surface));
  color: var(--mower-text);
  font-weight: 650;
}
.channel-chip:focus-visible,
.channel-picker__alert button:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: 2px;
}
/* 只有今天签到失败的渠道带红点，其余状态放在悬停说明里。 */
.channel-chip__dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--mower-error);
}
.channel-chip.is-stale {
  border-style: dashed;
}
.channel-picker__alert {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px 8px;
  margin: 0;
  color: var(--mower-error-text, var(--mower-error));
  font-size: 12px;
}
.channel-picker__alert button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--skland-link, var(--mower-primary));
  font: inherit;
  cursor: pointer;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
