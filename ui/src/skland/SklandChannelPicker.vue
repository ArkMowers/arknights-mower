<script setup>
import { computed } from 'vue'

const props = defineProps({
  channels: { type: Array, required: true },
  selected: { type: Object, default: null }
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

function chipLabel(channel) {
  const region = channel.channel === 'bilibili服' ? 'B服' : channel.channel
  const role = channel.shared ? ` · ${channel.display_name || `角色 ${channel.role_index}`}` : ''
  return `${channel.game_group} ${region}${role}`
}

function chipTitle(channel) {
  return [channel.display_name, STATUS_LABELS[channel.status]].filter(Boolean).join(' · ')
}
</script>

<template>
  <div class="channel-picker">
    <div class="channel-picker__account">
      <n-select
        v-if="accounts.length > 1"
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
