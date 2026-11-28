<script setup>
// PROTOTYPE：任务配置页的编排方案，通过 ?variant=H|E|F|G|D|A|B|C 切换，全部使用内存里的假数据。
// 选定方案后：胜出方案按正式标准重写进 maasettings.vue，本目录整体移到原型分支。
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { createState } from './data'
import MetroVariant from './MetroVariant.vue'
import DialVariant from './DialVariant.vue'
import ScoreVariant from './ScoreVariant.vue'
import LoopVariant from './LoopVariant.vue'
import ListingVariant from './ListingVariant.vue'
import SchematicVariant from './SchematicVariant.vue'
import StructogramVariant from './StructogramVariant.vue'
import PrototypeSwitcher from './PrototypeSwitcher.vue'
import TaskSwitchesVariant from './TaskSwitchesVariant.vue'

defineOptions({ name: 'TaskflowPrototype' })

const variants = [
  { key: 'E', name: '程序清单', component: ListingVariant },
  { key: 'F', name: '工程图纸', component: SchematicVariant },
  { key: 'G', name: '结构图', component: StructogramVariant },
  { key: 'D', name: '∞ 回路', component: LoopVariant },
  { key: 'A', name: '线路图', component: MetroVariant },
  { key: 'B', name: '同心表盘', component: DialVariant },
  { key: 'C', name: '乐谱', component: ScoreVariant },
  { key: 'H', name: '任务开关', component: TaskSwitchesVariant }
]
const route = useRoute()
const current = computed(
  () => variants.find((variant) => variant.key === route.query.variant) ?? variants[0]
)
// 各变体共用一份状态，切换时可以对比同一份配置的不同呈现
const state = createState()
</script>

<template>
  <div class="taskflow-prototype">
    <component :is="current.component" :state="state" />
    <PrototypeSwitcher
      v-if="current.key !== 'H'"
      :variants="variants.filter((variant) => variant.key !== 'H')"
    />
  </div>
</template>

<style scoped>
.taskflow-prototype {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  min-height: 100%;
}
</style>
