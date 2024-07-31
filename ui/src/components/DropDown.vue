<script setup>
defineProps({
  select: { type: Function },
  options: { type: Array },
  type: { default: 'default' },
  up: { default: false, type: Boolean }
})
import DropUpIcon from '@vicons/ionicons4/MdArrowDropup'
import DropDownIcon from '@vicons/ionicons4/MdArrowDropdown'
</script>

<template>
  <n-dropdown trigger="hover" width="trigger" :options="options" @select="select">
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
  padding: 0 6px;
}
</style>
