<script setup>
import LogOperator from '@/components/LogOperator.vue'

defineProps({
  token: { type: Object, required: true },
  muteExperience: Boolean
})
</script>

<template>
  <span
    class="log-token log-token--item"
    :class="{
      'log-token--order-operator': token.type === 'order-operator',
      'log-token--item-experience':
        token.type === 'item' && muteExperience && /作战(?:记录|录像)/u.test(token.text)
    }"
    :style="{ '--log-item-light': token.lightColor, '--log-item-dark': token.darkColor }"
    ><log-operator v-if="token.type === 'order-operator'" :name="token.name" show-name :size="16" />
    <template v-else
      ><img :src="token.icon" width="16" height="16" alt="" aria-hidden="true" />{{
        token.text
      }}</template
    ></span
  >
</template>

<style scoped>
.log-token--item {
  --log-item-active: var(--log-item-light);
  --log-item-mix: 70%;
  color: color-mix(in srgb, var(--log-item-active) var(--log-item-mix), var(--log-ink));
  white-space: nowrap;
}
.log-token--item-experience {
  --log-item-mix: 35%;
}
.log-token--item > img {
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-right: 3px;
  object-fit: contain;
  vertical-align: -3px;
}
html[data-mower-theme='dark'] .log-token--item,
html[data-window-shell-theme='dark'] .log-token--item {
  --log-item-active: var(--log-item-dark);
  --log-item-mix: 85%;
}
</style>
