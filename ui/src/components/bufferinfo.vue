<template>
  <span v-html="des" @click="handleTermClick($event)"></span>
  <n-modal v-model:show="showModal" v-if="props.isbuffer">
    <n-card
      style="width: min(600px, calc(100vw - 32px)); user-select: text"
      :title="t('baseSkills.specialEffects')"
      :bordered="false"
      size="huge"
      role="dialog"
      aria-modal="true"
    >
      <div v-for="item in displayedTerms" :key="item.termId">
        <n-card :title="item.termName">
          <div v-html="richText2HTML(item.description)"></div>
        </n-card>
      </div>
    </n-card>
  </n-modal>
</template>

<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, ref } from 'vue'
import { richText2HTML, findTerm } from '@/stores/richText2HTML'
import { useBasementSkill } from '@/stores/basementSkill'
import { localizedBaseTerm } from '@/i18n/baseSkillDetails'

defineOptions({ name: 'BasementSkillTerms' })

const { buffer: buffer1 } = useBasementSkill()
const showModal = ref(false)
const props = defineProps({
  des: String,
  isbuffer: Boolean,
  buffer: Array
})
const displayedTerms = computed(() =>
  (props.buffer || []).map((id) => localizedBaseTerm(id, buffer1.value[id])).filter(Boolean)
)
const handleTermClick = (event) => {
  const clickedTermElement = findTerm(event)
  if (clickedTermElement) {
    showModal.value = true // 设置 showModal 为 true，显示模态框
  }
}
</script>

<style>
.cc-vup {
  color: #0098dc;
}

.cc-vdown {
  color: #ff6237;
}

.cc-rem {
  color: #f49800;
}

.cc-kw {
  color: #00b0ff;
}
</style>
