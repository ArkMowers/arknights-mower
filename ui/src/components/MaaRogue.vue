<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()

const { maa_rg_theme, rogue } = storeToRefs(store)

const rogue_themes = [
  { label: '傀影与猩红孤钻', value: 'Phantom' },
  { label: '水月与深蓝之树', value: 'Mizuki' },
  { label: '探索者的银凇止境', value: 'Sami' }
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
</script>

<template>
  <table class="tab-content">
    <tr>
      <td>主题：</td>
      <td>
        <n-radio-group v-model:value="maa_rg_theme">
          <n-space>
            <n-radio v-for="t in rogue_themes" :value="t.value">{{ t.label }}</n-radio>
          </n-space>
        </n-radio-group>
      </td>
    </tr>
    <tr>
      <td>分队：</td>
      <td>
        <n-select v-model:value="rogue.squad" :options="squad[maa_rg_theme]" />
      </td>
    </tr>
    <tr>
      <td>职业：</td>
      <td>
        <n-select v-model:value="rogue.roles" :options="roles" />
      </td>
    </tr>
    <tr>
      <td>干员：</td>
      <td>
        <n-input v-model:value="rogue.core_char" />
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <n-checkbox v-model:checked="rogue.use_support">开局干员使用助战</n-checkbox>
      </td>
    </tr>
    <tr v-if="rogue.use_support">
      <td colspan="2">
        <n-checkbox v-model:checked="rogue.use_nonfriend_support"
          >开局干员使用非好友助战</n-checkbox
        >
      </td>
    </tr>
    <tr>
      <td>策略：</td>
      <td>
        <n-radio-group v-model:value="rogue.mode">
          <n-space>
            <n-radio :value="0">刷等级</n-radio>
            <n-radio :value="1">刷源石锭</n-radio>
          </n-space>
        </n-radio-group>
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <n-checkbox v-model:checked="rogue.investment_enabled">投资源石锭</n-checkbox>
      </td>
    </tr>
    <tr v-if="rogue.investment_enabled">
      <td colspan="2">
        <n-checkbox v-model:checked="rogue.stop_when_investment_full"
          >储备源石锭达到上限时停止</n-checkbox
        >
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <n-checkbox v-model:checked="rogue.refresh_trader_with_dice">刷新商店（指路鳞）</n-checkbox>
      </td>
    </tr>
  </table>
</template>

<style scoped lang="scss">
.tab-content {
  margin: 0 24px 12px 24px;
}
</style>
