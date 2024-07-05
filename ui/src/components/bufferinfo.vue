<template>
  <span v-html="des" @click="handleTermClick($event)"></span>
  <n-modal v-model:show="showModal" v-if="props.isbuffer">
    <n-card
      style="width: 600px; user-select: none"
      title="特殊效果"
      :bordered="false"
      size="huge"
      role="dialog"
      aria-modal="true"
    >
      <div v-for="item in props.buffer">
        <n-card :title="buffer1[item].termName">
          <div v-html="richText2HTML(buffer1[item].description)"></div>
        </n-card>
      </div>
    </n-card>
  </n-modal>
</template>

<script setup>
import { ref, computed } from 'vue'
import { richText2HTML, findTerm } from '@/stores/richText2HTML'
import buffer1 from '@/pages/buffer.json'
const showModal = ref(false)
const props = defineProps({
  des: String,
  isbuffer: Boolean,
  buffer: Array
})
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
