<script setup>
import { computed, ref } from 'vue'
import emptyAvatar from '@/assets/log/empty-operator.svg?url&no-inline'

const props = defineProps({
  name: { type: String, required: true },
  showName: { type: Boolean, default: false },
  hideHint: Boolean,
  size: { type: Number, default: 24 }
})

const resourceBase = import.meta.env.BASE_URL
const displayName = computed(() => (!props.name || props.name === '_' ? 'Empty' : props.name))
const description = computed(
  () =>
    ({
      Current: 'Current（保留当前干员）',
      Free: 'Free（自动选择干员）',
      Empty: 'Empty（留空）'
    })[displayName.value] ?? displayName.value
)
const isPlaceholder = computed(() => ['Current', 'Free', 'Empty'].includes(displayName.value))
const avatarSource = computed(() =>
  displayName.value === 'Empty'
    ? emptyAvatar
    : `${resourceBase}avatar/${encodeURIComponent(displayName.value)}.webp`
)
const failedSource = ref('')
const hasAvatar = computed(() => failedSource.value !== avatarSource.value)

function imageFailed(event) {
  failedSource.value = event.target?.getAttribute?.('src') ?? avatarSource.value
}
</script>

<template>
  <span
    class="log-operator"
    :class="{
      'log-operator--with-avatar': hasAvatar,
      'log-operator--placeholder': isPlaceholder
    }"
    :style="{ '--log-operator-size': `${size}px` }"
    :data-operator-name="displayName"
    :title="hideHint ? '' : description"
    :role="showName ? undefined : 'img'"
    :aria-label="showName ? undefined : description"
    :tabindex="showName ? undefined : 0"
  >
    <img
      v-if="hasAvatar"
      :key="avatarSource"
      class="log-operator__avatar"
      :src="avatarSource"
      :width="size"
      :height="size"
      alt=""
      aria-hidden="true"
      loading="lazy"
      decoding="async"
      draggable="false"
      @error="imageFailed"
    />
    <span v-if="showName || !hasAvatar" class="log-operator__name">{{ displayName }}</span>
  </span>
</template>

<style scoped>
.log-operator {
  display: inline;
  color: inherit;
  font: inherit;
  white-space: nowrap;
  user-select: text;
}

.log-operator__avatar {
  display: inline-block;
  box-sizing: border-box;
  width: var(--log-operator-size);
  height: var(--log-operator-size);
  border: 1px solid color-mix(in srgb, var(--mower-text, #30343a) 20%, transparent);
  border-radius: 50%;
  background-color: var(--mower-surface, #fff);
  box-shadow: 0 1px 4px rgba(24, 25, 28, 0.16);
  object-fit: cover;
  vertical-align: middle;
  user-select: none;
}

.log-operator--with-avatar .log-operator__name {
  margin-inline-start: 4px;
}

:is(html[data-mower-theme='dark'], html[data-window-shell-theme='dark'])
  .log-operator--placeholder[data-operator-name='Empty']
  .log-operator__avatar {
  border-color: rgba(0, 0, 0, 0.2);
  background-color: #fff;
  box-shadow: none;
  filter: invert(1);
}

.log-operator:is([data-operator-name='Current'], [data-operator-name='Free']) .log-operator__avatar {
  --log-placeholder-ring: color-mix(in srgb, var(--mower-text, #30343a) 20%, transparent);
  border: 0;
  padding: 1px;
  background-color: color-mix(in srgb, var(--mower-surface, #fff) 62%, transparent);
  box-shadow: inset 0 0 0 var(--log-hairline, 1px) var(--log-placeholder-ring);
}

:is(html[data-mower-theme='dark'], html[data-window-shell-theme='dark'])
  .log-operator:is([data-operator-name='Current'], [data-operator-name='Free'])
  .log-operator__avatar {
  --log-placeholder-ring: rgb(0 0 0 / 20%);
  background-color: rgb(255 255 255 / 62%);
  filter: invert(0.86);
}

.log-operator:is([data-operator-name='Current'], [data-operator-name='Free']) .log-operator__name {
  color: var(--mower-text-muted, #6b7280);
}

.log-operator:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
  border-radius: 4px;
}
</style>
