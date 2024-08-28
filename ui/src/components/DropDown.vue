<script setup>
defineProps({
  select: { type: Function },
  options: { type: Array },
  type: { default: 'default' },
  up: { default: false, type: Boolean }
})

import DropUpIcon from '@vicons/ionicons4/MdArrowDropup'
import DropDownIcon from '@vicons/ionicons4/MdArrowDropdown'

import { inject, computed } from 'vue'

const mobile = inject('mobile')

const btn_pad = computed(() => {
  if (mobile.value) {
    return '12px'
  } else {
    return '6px'
  }
})
</script>

<template>
  <n-dropdown
    trigger="hover"
    width="trigger"
    :options="options"
    @select="select"
    :placement="up ? 'top' : 'bottom'"
  >
    <n-button-group>
      <slot />
      <n-button class="dropdown" :type="type" ghost>
        <template #icon>
          <n-icon><drop-up-icon v-if="up" /><drop-down-icon v-else /></n-icon>
        </template>
      </n-button>
    </n-button-group>
  </n-dropdown>
</template>

<style scoped>
.dropdown {
  padding-left: v-bind(btn_pad);
  padding-right: v-bind(btn_pad);
}
</style>
