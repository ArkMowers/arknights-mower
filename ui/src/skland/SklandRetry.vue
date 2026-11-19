<script setup>
import SessionLink from '@/components/SessionLink.vue'

defineProps({
  busy: { type: Boolean, default: false },
  message: { type: String, default: '' },
  error: { type: Boolean, default: false },
  account: { type: Boolean, default: false }
})
const emit = defineEmits(['retry'])
</script>

<template>
  <div class="skland-retry">
    <p v-if="account" class="skland-retry__hint">
      重试前请检查
      <SessionLink to="/settings#task-accounts">森空岛账号</SessionLink>。
    </p>
    <div class="skland-retry__row">
      <n-button size="small" :loading="busy" @click="emit('retry')">重新签到</n-button>
      <span v-if="message" :class="{ 'is-error': error }" role="status">{{ message }}</span>
    </div>
  </div>
</template>

<style scoped>
.skland-retry {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
}
.skland-retry__hint {
  margin: 0;
  color: var(--mower-text-muted);
}
.skland-retry__hint a {
  color: var(--skland-link, var(--mower-primary));
}
.skland-retry__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  color: var(--mower-text-muted);
}
.skland-retry__row .is-error {
  color: var(--mower-error-text, var(--mower-error));
}
</style>
