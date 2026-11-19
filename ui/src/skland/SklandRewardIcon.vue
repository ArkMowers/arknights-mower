<script setup>
import { publicAsset } from '@/utils/publicAsset'
import { computed, ref } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  game: { type: String, required: true },
  item: { type: String, required: true }
})

const endfieldIcons = new Map([
  ['嵌晶玉', 'item_diamond'],
  ['中级作战记录', 'item_expcard_stage1_mid'],
  ['高级作战记录', 'item_expcard_stage1_high'],
  ['初级认知载体', 'item_expcard_stage2_low'],
  ['武器检查装置', 'item_weapon_expcard_mid'],
  ['武器检查套组', 'item_weapon_expcard_high'],
  ['协议棱柱', 'item_char_skill_level_1_6'],
  ['折金票', 'item_gold']
])

const missing = ref('')
const src = computed(() => {
  if (props.game === '明日方舟' && props.item) {
    return publicAsset(`/depot/${encodeURIComponent(props.item)}.webp`)
  }
  const endfieldIcon = props.game === '终末地' && endfieldIcons.get(props.item)
  return endfieldIcon ? publicAsset(`/skland-icons/endfield/${endfieldIcon}.webp`) : ''
})
</script>

<template>
  <img
    v-if="src && src !== missing"
    :key="src"
    v-bind="$attrs"
    :src="src"
    alt=""
    loading="lazy"
    @error="missing = src"
  />
  <slot v-else />
</template>
