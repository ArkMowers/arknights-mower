<script setup>
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed, inject, watch } from 'vue'

const mobile = inject('mobile')

const config_store = useConfigStore()

const { maa_rg_theme, rogue } = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

import { pinyin_match } from '@/utils/common'
import { render_op_label } from '@/utils/op_select'
import HelpText from '@/components/HelpText.vue'
import {
  collectible_start_visible,
  difficulty_options,
  elite_two_visible,
  is_field_enabled,
  modes_for_theme,
  monthly_squad_check_comms_visible,
  only_elite_two_needs_reset,
  only_elite_two_visible,
  rogue_themes,
  start_foldartal_visible
} from '@/utils/roguelike_options'

// 分队名与顺序对照 RoguelikeSettingsUserControlModel（主题分队 + 通用分队 + 高规格）；
// 高规格仅傀影/水月/萨米/萨卡兹/界园有，黑流树海无。
const squad = {
  Phantom: [
    '集群',
    '矛头',
    '研究',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Mizuki: [
    '集群',
    '矛头',
    '心胜于物',
    '物尽其用',
    '以人为本',
    '研究',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Sami: [
    '集群',
    '矛头',
    '永恒狩猎',
    '生活至上',
    '科学主义',
    '特训',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  Sarkaz: [
    '集群',
    '矛头',
    '魂灵护送',
    '博闻广记',
    '蓝图测绘',
    '因地制宜',
    '异想天开',
    '点刺成锭',
    '拟态学者',
    '专业人士',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  JieGarden: [
    '特勤',
    '高台突破',
    '地面突破',
    '游客',
    '司岁台',
    '天师府',
    '花团锦簇',
    '棋行险着',
    '岁影回音',
    '代理人',
    '知学',
    '商贾',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术',
    '高规格'
  ],
  BlackFlow: [
    '特勤',
    '矛头',
    '高台突破',
    '地面突破',
    '本源研修',
    '文明开化',
    '开拓者',
    '多边贸易',
    '地质调查',
    '指挥',
    '后勤',
    '突击战术',
    '堡垒战术',
    '远程战术',
    '破坏战术'
  ]
}

// 个别分队显示带注解（代理人分队（不支持）），值仍为干净分队名。
const squad_display_override = { 代理人: '代理人分队（不支持）' }

for (const s in squad) {
  squad[s] = squad[s].map((x) => {
    const value = x + '分队'
    return { label: squad_display_override[x] ?? value, value }
  })
}

// 职业组按主题变化：界园/黑流树海额外有「灵活部署」「坚不可摧」，其余主题没有。
const roles = computed(() => {
  const base = [
    { label: '先手必胜（先锋、狙击、特种）', value: '先手必胜' },
    { label: '稳扎稳打（重装、术师、狙击）', value: '稳扎稳打' },
    { label: '取长补短（近卫、辅助、医疗）', value: '取长补短' }
  ]
  if (maa_rg_theme.value === 'JieGarden' || maa_rg_theme.value === 'BlackFlow') {
    base.push({ label: '灵活部署（先锋、辅助、特种）', value: '灵活部署' })
    base.push({ label: '坚不可摧（重装、术师、医疗）', value: '坚不可摧' })
  }
  base.push({ label: '随心所欲（三张随机）', value: '随心所欲' })
  return base
})

// MAA 各主题「推荐配置」提示（RoguelikeThemeTip*，{key=...} 已解析），挂在开局干员旁的 ？ 上；
// 开头照 MAA 的 StartingCoreCharTip（「不填写则使用默认策略。」）并标注来源，
// 主题名用 MAA 的缩写（傀影/水月/萨米/萨卡兹/界园/黑流树海）。
const rogue_theme_tip_header = '以下提示来自 MAA：\n不填写则使用默认策略。\n\n'
const rogue_theme_tip = computed(() => {
  const tips = {
    Phantom: `傀影推荐配置：

开局分队: 指挥分队 / 突击战术分队
开局职业组: 取长补短（近卫、辅助、医疗）
开局干员: 丰川祥子 / 棘刺

当前难度 ≥3 时，可能无法在开局招募 6★ 干员，导致出错或失败`,
    Mizuki: `水月推荐配置：

开局分队: 以人为本分队 / 心胜于物分队
开局职业组: 稳扎稳打（重装、术师、狙击）
开局干员: 维什戴尔

1. box 里强力 6★ 干员较多时推荐选择 ｢以人为本分队｣
2. 当前难度 ≥4 时，6★ 干员希望消耗 +1，使用部分分队时可能无法在开局招募 6★ 干员，导致出错或失败`,
    Sami: `萨米推荐配置：

开局分队: 特训分队 / 远程战术分队
开局职业组: 稳扎稳打（重装、术师、狙击）
开局干员: 维什戴尔

当前难度 ≥6 时，6★ 干员希望消耗 +1，使用部分分队时可能无法在开局招募 6★ 干员，导致出错或失败`,
    Sarkaz: `萨卡兹推荐配置：

开局分队: 蓝图测绘分队 / 远程战术分队
开局职业组: 稳扎稳打（重装、术师、狙击）
开局干员: 维什戴尔

1. 使用 ｢蓝图测绘分队｣ 时将完全采用避战策略，适合快速刷等级，不追求通关
2. 使用 ｢点刺成锭分队｣ 可提升刷源石锭效率，但需要注意策略选择为 ｢刷源石锭｣
3. 当前难度 ≥15 时，6★ 干员希望消耗 +1，使用部分分队时可能无法招募开局 6★ 干员，导致出错或失败`,
    JieGarden: `界园推荐配置：

开局分队: 指挥分队 / 远程战术分队
开局职业组: 稳扎稳打（重装、术师、狙击）
开局干员: 维什戴尔

1. 当策略选择 ｢刷源石锭｣，难度选择 ≥3 或 ｢MAX｣，开局分队选择 ｢指挥分队｣ 时将启用指挥避战策略
2. 使用指挥避战策略将大幅提高刷源石锭效率，也可用于快速刷等级（不追求通关），但需要注意策略选择为 ｢刷源石锭｣
3. 已解锁的最高难度 <3 或未解锁相关科技时，请不要使用指挥避战策略，否则会导致出错
4. 当前难度 ≥15 时，6★ 干员希望消耗 +1，使用部分分队时可能无法招募开局 6★ 干员，导致出错或失败`,
    BlackFlow: `黑流树海推荐配置：

开局干员: 机械师（要精二）
开局分队: ｢特勤分队｣ / ｢堡垒战术分队｣
开局职业组: ｢稳扎稳打（重装、术师、狙击）｣ / ｢坚不可摧（重装、术师、医疗）｣

1. 目前没有专用战斗策略，作战由招募评分自动决策；
    刷源石锭、刷等级、刷襁褓动物目前全部围绕精二机械师的飞展开。
    本次肉鸽机制繁多，不按上述配置开局就只能使用默认寻路与战斗，大概率失败，
    强烈推荐精二机械师开局（精二机械师只需通关一次 N1，相对简单）
2. 机械师精二后，完成 ｢招募精通 II｣ ｢效果提升 II｣ 科技，开局即可携带 ｢结构性原理｣（全图任意飞 3 次）；
    解锁很简单，精二后累计卖出 10 个零件即可，强烈推荐。
    未解锁时只能向周围 8 格飞 3 次，虽然也能刷，但效率会低不少
3. 刷等级时，机械师（要精二）+ 上述分队与职业组 + 重装券，可以快速飞完三层
4. 没有精二机械师就不要选机械师，可以正常刷钱，但战斗大概率暴毙，其他策略待后续优化
5. 刷等级 + 不勾选 ｢投资源石锭｣，即可跳过商店`
  }
  return tips[maa_rg_theme.value] ? rogue_theme_tip_header + tips[maa_rg_theme.value] : ''
})

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

// 烧水分队：未填写时默认跟随 squad（协议：默认与 squad 同步，两者皆空时为指挥分队）
const collectible_squad_options = computed(() => [
  { label: '默认（跟随分队）', value: '' },
  ...(squad[maa_rg_theme.value] ?? [])
])

// 凹开局/只凹直升的可见性与「只凹需先勾直升」的联动清理规则都在 roguelike_options.js
// 维护（与协议条件同处）：直升取消勾选或直升不再可见（主题/策略/分队变化）时只凹一并
// 清除，避免下发 start_with_elite_two=false 与 only_start_with_elite_two=true 的非法组合。
watch(
  [
    () => rogue.value.only_start_with_elite_two,
    () => rogue.value.start_with_elite_two,
    () => rogue.value.mode,
    () => rogue.value.squad,
    maa_rg_theme
  ],
  () => {
    if (
      only_elite_two_needs_reset(
        maa_rg_theme.value,
        rogue.value.mode,
        rogue.value.squad,
        rogue.value.start_with_elite_two,
        rogue.value.only_start_with_elite_two
      )
    ) {
      rogue.value.only_start_with_elite_two = false
    }
  },
  { immediate: true }
)

// 策略下拉：按当前主题过滤主题限定模式（10001/20001/30001 等），其余主题不可见。
const mode_options = computed(() => modes_for_theme(maa_rg_theme.value))

// 切主题后（含载入时）若当前策略已不属于该主题，回退到通用策略 0（刷等级），避免下发无效组合。
watch(
  maa_rg_theme,
  () => {
    if (!mode_options.value.some((m) => m.value === rogue.value.mode)) {
      rogue.value.mode = 0
    }
  },
  { immediate: true }
)

// 策略切到「刷源石锭」时强制开启投资（对照 RoguelikeMode 设置器），该模式下投资勾选随之禁用。
watch(
  () => rogue.value.mode,
  (mode) => {
    if (mode === 1 && !rogue.value.investment_enabled) {
      rogue.value.investment_enabled = true
    }
  },
  { immediate: true }
)
// 刷开局期望奖励：选项按主题变化（对照 UpdateRoguelikeStartWithAllDict），
// 存储只保留选中的奖励键（协议 collectible_mode_start_list）。
const start_reward_options = computed(() => {
  const base = [
    { label: '热水壶', value: 'hot_water' },
    { label: '盾', value: 'shield' },
    { label: '锭', value: 'ingot' },
    { label: '希望', value: 'hope' },
    { label: '随机奖励', value: 'random' }
  ]
  const theme = maa_rg_theme.value
  if (theme === 'JieGarden') {
    base.splice(
      base.findIndex((o) => o.value === 'hope'),
      1
    )
  }
  if (theme === 'Mizuki') {
    base.push({ label: '钥匙', value: 'key' }, { label: '骰子', value: 'dice' })
  }
  if (theme === 'Sarkaz') base.push({ label: '构想', value: 'ideas' })
  if (theme === 'JieGarden') base.push({ label: '票券', value: 'ticket' })
  return base
})
const start_reward_values = computed({
  get: () =>
    Object.entries(rogue.value.collectible_mode_start_list ?? {})
      .filter(([, v]) => v)
      .map(([k]) => k),
  set: (v) => {
    rogue.value.collectible_mode_start_list = Object.fromEntries(v.map((k) => [k, true]))
  }
})

// 凹开局板子输入（协议 start_foldartal_list，最多 3 个，与 MAA 模型一致）；逗号分隔。
const start_foldartal_values = computed({
  get: () => (rogue.value.start_foldartal_list ?? []).join(','),
  set: (v) => {
    rogue.value.start_foldartal_list = v
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3)
  }
})

// 黑流树海刷襁褓动物目标品种（对照协议枚举与 MAA 显示名）。
const blackflow_target_options = [
  { label: '襁褓中的猫', value: 'swaddled_cat' },
  { label: '襁褓羽蛇', value: 'swaddled_feathered_serpent' },
  { label: '襁褓中的狗', value: 'swaddled_dog' },
  { label: '襁褓三头犬', value: 'swaddled_cerberus' }
]

// 界园刷常乐节点目标子类型（对照 MAA 显示名）。
const find_playtime_options = [
  { label: '令 - 掷地有声', value: 1 },
  { label: '黍 - 种因得果', value: 2 },
  { label: '年 - 三缺一', value: 3 }
]
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
    <n-form-item label="肉鸽主题">
      <n-select v-model:value="maa_rg_theme" :options="rogue_themes" />
    </n-form-item>
    <n-form-item label="开局分队">
      <n-select v-model:value="rogue.squad" :options="squad[maa_rg_theme]" />
    </n-form-item>
    <n-form-item label="开局职业组">
      <n-select v-model:value="rogue.roles" :options="roles" />
    </n-form-item>
    <n-form-item>
      <template #label>
        开局干员
        <HelpText>
          <span style="white-space: pre-line">{{ rogue_theme_tip }}</span>
        </HelpText>
      </template>
      <n-select
        filterable
        clearable
        :options="operators"
        v-model:value="rogue.core_char"
        :filter="(p, o) => pinyin_match(o.label, p)"
        :render-label="render_op_label"
      />
    </n-form-item>
    <n-form-item
      v-if="elite_two_visible(maa_rg_theme, rogue.mode, rogue.squad)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.start_with_elite_two">凹开局干员直升精二</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="
        only_elite_two_visible(maa_rg_theme, rogue.mode, rogue.squad, rogue.start_with_elite_two)
      "
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.only_start_with_elite_two"
        >只凹开局干员直升精二，不进行作战</n-checkbox
      >
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.use_support">开局干员使用助战</n-checkbox>
    </n-form-item>
    <n-form-item v-if="rogue.use_support" :show-label="false">
      <n-checkbox v-model:checked="rogue.use_nonfriend_support">开局干员使用非好友助战</n-checkbox>
    </n-form-item>
    <n-form-item label="策略">
      <n-select :options="mode_options" v-model:value="rogue.mode" />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('monthly_squad_auto_iterate', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.monthly_squad_auto_iterate">月度小队自动切换</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="
        monthly_squad_check_comms_visible(
          maa_rg_theme,
          rogue.mode,
          rogue.monthly_squad_auto_iterate
        )
      "
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.monthly_squad_check_comms"
        >将月度小队通信也作为切换依据</n-checkbox
      >
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('deep_exploration_auto_iterate', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.deep_exploration_auto_iterate"
        >深入调查自动切换</n-checkbox
      >
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('refresh_trader_with_dice', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.refresh_trader_with_dice">刷新商店（指路鳞）</n-checkbox>
    </n-form-item>
    <n-form-item
      label="坍缩范式"
      v-if="is_field_enabled('expected_collapsal_paradigms', maa_rg_theme, rogue.mode)"
    >
      <n-select multiple :options="col_list" v-model:value="rogue.expected_collapsal_paradigms" />
    </n-form-item>
    <n-form-item label="难度">
      <n-select v-model:value="rogue.difficulty" :options="difficulty_options(maa_rg_theme)" />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_at_final_boss', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_at_final_boss">到达险路恶敌前停止</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_at_max_level', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_at_max_level">肉鸽等级刷满后停止</n-checkbox>
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.investment_enabled" :disabled="rogue.mode === 1"
        >投资源石锭</n-checkbox
      >
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_when_investment_full', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_when_investment_full">源石锭投资满时停止</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('investment_with_more_score', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.investment_with_more_score"
        >投资模式启用购物、招募、进2层</n-checkbox
      >
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('collectible_mode_shopping', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.collectible_mode_shopping">烧水时启用购物</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('collectible_mode_squad', maa_rg_theme, rogue.mode)"
      label="烧水分队"
    >
      <n-select v-model:value="rogue.collectible_mode_squad" :options="collectible_squad_options" />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('first_floor_foldartal', maa_rg_theme, rogue.mode)"
      label="第一层远见板子"
    >
      <n-input
        v-model:value="rogue.first_floor_foldartal"
        placeholder="板子名，留空不凹"
        style="width: 200px"
      />
    </n-form-item>
    <n-form-item
      v-if="start_foldartal_visible(maa_rg_theme, rogue.mode, rogue.squad)"
      label="凹开局板子"
    >
      <n-input
        v-model:value="start_foldartal_values"
        placeholder="多个用逗号分隔，最多 3 个"
        style="width: 260px"
      />
    </n-form-item>
    <n-form-item
      v-if="
        collectible_start_visible(
          maa_rg_theme,
          rogue.mode,
          rogue.squad,
          rogue.only_start_with_elite_two,
          rogue.start_with_elite_two
        )
      "
      label="刷开局期望奖励"
    >
      <n-select multiple :options="start_reward_options" v-model:value="start_reward_values" />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('blackflow_cultivation_target', maa_rg_theme, rogue.mode)"
      label="目标襁褓动物"
    >
      <n-select
        v-model:value="rogue.blackflow_cultivation_target"
        :options="blackflow_target_options"
      />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('find_playtime_target', maa_rg_theme, rogue.mode)"
      label="目标常乐节点"
    >
      <n-select v-model:value="rogue.find_playtime_target" :options="find_playtime_options" />
    </n-form-item>
  </n-form>
</template>
