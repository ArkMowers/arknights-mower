<script setup>
import { useConfigStore } from '@/stores/config';
import { usePlanStore } from '@/stores/plan';
import { storeToRefs } from 'pinia';
import { inject } from 'vue';

const mobile = inject('mobile')

const config_store = useConfigStore()

const { maa_rg_theme, rogue } = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

import { pinyin_match } from '@/utils/common';
import { render_op_label } from '@/utils/op_select';

const rogue_themes = [
  { label: '傀影与猩红孤钻', value: 'Phantom' },
  { label: '水月与深蓝之树', value: 'Mizuki' },
  { label: '探索者的银凇止境', value: 'Sami' },
  { label: '萨卡兹的无终奇语', value: 'Sarkaz' }
]

const squad = {
  Phantom: [
    '研究',
    '指挥',
    '集群',
    '后勤',
    '矛头',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Mizuki: [
    '心胜于物',
    '物尽其用',
    '以人为本',
    '研究',
    '指挥',
    '集群',
    '后勤',
    '矛头',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Sami: [
    '永恒狩猎',
    '生活至上',
    '科学主义',
    '特训',
    '指挥',
    '集群',
    '后勤',
    '矛头',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Sarkaz: [
    '因地制宜',
    '魂灵护送',
    '博闻广记',
    '蓝图测绘',
    '指挥',
    '集群',
    '后勤',
    '矛头',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ]
}

for (const s in squad) {
  squad[s] = squad[s].map((x) => {
    return { label: x + '分队', value: x + '分队' }
  })
}

const roles = [
  { label: '先手必胜（先锋、狙击、特种）', value: '先手必胜' },
  { label: '稳扎稳打（重装、术师、狙击）', value: '稳扎稳打' },
  { label: '取长补短（近卫、辅助、医疗）', value: '取长补短' },
  { label: '随心所欲（随机）', value: '随心所欲' }
]

const mode_list = [
  { label: '刷蜡烛，尽可能稳定地打更多层数', value: 0 },
  { label: '刷源石锭，第一层投资完就退出', value: 1 },
  { label: '【即将弃用】兼顾', value: 2 },
  // { label: '开发中...', value: 3 },
  { label: '刷开局，到达第三层后直接退出', value: 4 },
  { label: '刷坍缩范式', value: 5 }
]

const col = [
  '去量化',
  '去量深化',
  '实质性坍缩',
  '蔓延性坍缩',
  '非线性移动',
  '非线性行动',
  '情绪实体',
  '恐怖实体',
  '泛社会悖论',
  '泛文明悖论',
  '气压异常',
  '气压失序',
  '触发性损伤',
  '触发性危殆',
  '趋同性消耗',
  '趋同性缺失',
  '目空一些',
  '睁眼瞎',
  '图像损坏',
  '一抹黑'
]
const col_list = []
for (const c of col) {
  col_list.push({ label: c, value: c })
}
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
    <n-form-item label="主题">
      <n-select v-model:value="maa_rg_theme" :options="rogue_themes" />
    </n-form-item>
    <n-form-item label="分队">
      <n-select v-model:value="rogue.squad" :options="squad[maa_rg_theme]" />
    </n-form-item>
    <n-form-item label="职业">
      <n-select v-model:value="rogue.roles" :options="roles" />
    </n-form-item>
    <n-form-item label="干员">
      <n-select
        filterable
        :options="operators"
        v-model:value="rogue.core_char"
        :filter="(p, o) => pinyin_match(o.label, p)"
        :render-label="render_op_label"
      />
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.use_support">开局干员使用助战</n-checkbox>
    </n-form-item>
    <n-form-item v-if="rogue.use_support" :show-label="false">
      <n-checkbox v-model:checked="rogue.use_nonfriend_support">开局干员使用非好友助战</n-checkbox>
    </n-form-item>
    <n-form-item label="策略">
      <n-select :options="mode_list" v-model:value="rogue.mode" />
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.refresh_trader_with_dice">刷新商店（指路鳞）</n-checkbox>
    </n-form-item>
    <n-form-item label="坍缩范式">
      <n-select multiple :options="col_list" v-model:value="rogue.expected_collapsal_paradigms" />
    </n-form-item>
  </n-form>
</template>
