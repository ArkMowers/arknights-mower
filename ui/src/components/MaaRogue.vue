<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
const { t } = i18n.global

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { storeToRefs } from 'pinia'
import { computed, inject, watch } from 'vue'

const mobile = inject('mobile')

const config_store = useConfigStore()

const { maa_rg_theme, rogue } = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

import { render_op_option, render_op_label, filterOperatorOption } from '@/utils/op_select'
import HelpText from '@/components/HelpText.vue'
import {
  blackflow_animals,
  blackflow_rewards,
  collectible_start_visible,
  difficulty_options,
  elite_two_visible,
  is_field_enabled,
  modes_for_theme,
  monthly_squad_check_comms_visible,
  only_elite_two_needs_reset,
  only_elite_two_visible,
  rogue_themes,
  rogueOptionLabel,
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
const squad_display_override = {
  get 代理人() {
    return t('tasks.unsupportedSquad', { squad: rogueOptionLabel('rogueSquads', '代理人分队') })
  }
}

for (const s in squad) {
  squad[s] = squad[s].map((x) => {
    const value = x + '分队'
    return {
      get label() {
        return squad_display_override[x] ?? rogueOptionLabel('rogueSquads', value)
      },
      value
    }
  })
}

// 职业组按主题变化：界园/黑流树海额外有「灵活部署」「坚不可摧」，其余主题没有。
const roles = computed(() => {
  const base = [
    {
      get label() {
        return t('tasks.rolesFirstStrike')
      },
      value: '先手必胜'
    },
    {
      get label() {
        return t('tasks.rolesSteady')
      },
      value: '稳扎稳打'
    },
    {
      get label() {
        return t('tasks.rolesWeakness')
      },
      value: '取长补短'
    }
  ]
  if (maa_rg_theme.value === 'JieGarden' || maa_rg_theme.value === 'BlackFlow') {
    base.push({
      get label() {
        return t('tasks.rolesFlexible')
      },
      value: '灵活部署'
    })
    base.push({
      get label() {
        return t('tasks.rolesUnbreakable')
      },
      value: '坚不可摧'
    })
  }
  base.push({
    get label() {
      return t('tasks.rolesRandom')
    },
    value: '随心所欲'
  })
  return base
})

// MAA 各主题「推荐配置」提示（RoguelikeThemeTip*，{key=...} 已解析），挂在开局干员旁的 ？ 上；
// 开头照 MAA 的 StartingCoreCharTip（「不填写则使用默认策略。」）并标注来源，
// 主题名用 MAA 的缩写（傀影/水月/萨米/萨卡兹/界园/黑流树海）。
const rogue_theme_tip = computed(() => {
  const theme = maa_rg_theme.value
  return rogue_themes.some(({ value }) => value === theme)
    ? t('tasks.rogueTipHeader') +
        t(`tasks.rogueTips.${theme}`, {
          operator: operatorDisplayName('机械师'),
          squad1: rogueOptionLabel('rogueSquads', '特勤分队'),
          squad2: rogueOptionLabel('rogueSquads', '堡垒战术分队'),
          roles1: t('tasks.rolesSteady'),
          roles2: t('tasks.rolesUnbreakable')
        })
    : ''
})

const foldartal_options = [
  {
    get label() {
      return t('maaActivities.followMaaDefault')
    },
    value: null
  },
  {
    get label() {
      return t('maaActivities.enabled')
    },
    value: true
  },
  {
    get label() {
      return t('maaActivities.disabled')
    },
    value: false
  }
]
const blackflow_reward_values = computed({
  get: () =>
    blackflow_rewards
      .filter((item) => (rogue.value.blackflow_start_rewards ?? 0) & item.mask)
      .map((item) => item.value),
  set: (values) => {
    rogue.value.blackflow_start_rewards = blackflow_rewards
      .filter((item) => values.includes(item.value))
      .reduce((mask, item) => mask | item.mask, 0)
  }
})
function set_animal(index, value) {
  const animals = [...(rogue.value.blackflow_start_animals ?? [])]
  animals[index] = value
  rogue.value.blackflow_start_animals = animals.filter(Boolean)
}

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
  col_list.push({
    get label() {
      return rogueOptionLabel('rogueParadigms', c)
    },
    value: c
  })
}

// 烧水分队：未填写时默认跟随 squad（协议：默认与 squad 同步，两者皆空时为指挥分队）
const collectible_squad_options = computed(() => [
  {
    get label() {
      return t('tasks.defaultFollowSquad')
    },
    value: ''
  },
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
    { label: rogueOptionLabel('rogueRewards', '热水壶'), value: 'hot_water' },
    {
      get label() {
        return t('tasks.shield')
      },
      value: 'shield'
    },
    {
      get label() {
        return t('tasks.ingots')
      },
      value: 'ingot'
    },
    {
      get label() {
        return t('tasks.hope')
      },
      value: 'hope'
    },
    {
      get label() {
        return t('tasks.randomReward')
      },
      value: 'random'
    }
  ]
  const theme = maa_rg_theme.value
  if (theme === 'JieGarden') {
    base.splice(
      base.findIndex((o) => o.value === 'hope'),
      1
    )
  }
  if (theme === 'Mizuki') {
    base.push(
      {
        get label() {
          return t('tasks.key')
        },
        value: 'key'
      },
      {
        get label() {
          return t('tasks.dice')
        },
        value: 'dice'
      }
    )
  }
  if (theme === 'Sarkaz')
    base.push({
      get label() {
        return t('tasks.ideas')
      },
      value: 'ideas'
    })
  if (theme === 'JieGarden')
    base.push({
      get label() {
        return t('tasks.tickets')
      },
      value: 'ticket'
    })
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
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓中的猫')
    },
    value: 'swaddled_cat'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓羽蛇')
    },
    value: 'swaddled_feathered_serpent'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓中的狗')
    },
    value: 'swaddled_dog'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓三头犬')
    },
    value: 'swaddled_cerberus'
  }
]

// 界园刷常乐节点目标子类型（对照 MAA 显示名）。
const find_playtime_options = [
  {
    get label() {
      return operatorDisplayName('令') + ' - ' + rogueOptionLabel('roguePlaytime', '掷地有声')
    },
    value: 1
  },
  {
    get label() {
      return operatorDisplayName('黍') + ' - ' + rogueOptionLabel('roguePlaytime', '种因得果')
    },
    value: 2
  },
  {
    get label() {
      return operatorDisplayName('年') + ' - ' + rogueOptionLabel('roguePlaytime', '三缺一')
    },
    value: 3
  }
]
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'" :show-feedback="false" class="rogue">
    <n-form-item :label="t('tasks.roguelikeTheme')">
      <n-select
        v-model:value="maa_rg_theme"
        :options="rogue_themes"
        :consistent-menu-width="false"
      />
    </n-form-item>
    <n-form-item :label="t('tasks.startingSquad')">
      <n-select
        v-model:value="rogue.squad"
        :options="squad[maa_rg_theme]"
        :consistent-menu-width="false"
      />
    </n-form-item>
    <n-form-item :label="t('tasks.startingClasses')">
      <n-select v-model:value="rogue.roles" :options="roles" :consistent-menu-width="false" />
    </n-form-item>
    <n-form-item>
      <template #label
        >{{ t('tasks.startingOperator')
        }}<HelpText>
          <span style="white-space: pre-line">{{ rogue_theme_tip }}</span>
        </HelpText>
      </template>
      <n-select
        :consistent-menu-width="false"
        filterable
        clearable
        :options="operators"
        v-model:value="rogue.core_char"
        :filter="filterOperatorOption"
        :render-label="render_op_label"
        :render-option="render_op_option"
      />
    </n-form-item>
    <n-form-item :label="t('maaActivities.openingRecruitPriority')">
      <maa-rogue-recruit v-model="rogue.core_char_list" :options="operators" />
    </n-form-item>
    <n-form-item
      v-if="elite_two_visible(maa_rg_theme, rogue.mode, rogue.squad)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.start_with_elite_two">{{
        t('tasks.rerollEliteTwo')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="
        only_elite_two_visible(maa_rg_theme, rogue.mode, rogue.squad, rogue.start_with_elite_two)
      "
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.only_start_with_elite_two">{{
        t('tasks.onlyRerollEliteTwo')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.use_support">{{ t('tasks.startWithSupport') }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="
        rogue.use_support ||
        rogue.core_char_list?.some((item) => item.use_support) ||
        (maa_rg_theme === 'BlackFlow' &&
          rogue.mode === 30003 &&
          rogue.collectible_mode_core_char_list?.some((item) => item.use_support))
      "
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.use_nonfriend_support">{{
        t('tasks.allowNonFriendSupport')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item :label="t('tasks.strategy')">
      <n-select :consistent-menu-width="false" :options="mode_options" v-model:value="rogue.mode" />
    </n-form-item>
    <template v-if="maa_rg_theme === 'Sami'">
      <n-form-item :label="t('maaActivities.useFoldartal')"
        ><n-select
          :consistent-menu-width="false"
          v-model:value="rogue.use_foldartal"
          :options="foldartal_options"
      /></n-form-item>
      <n-form-item :label="t('maaActivities.checkParadigms')"
        ><n-select
          :consistent-menu-width="false"
          v-model:value="rogue.check_collapsal_paradigms"
          :options="foldartal_options"
      /></n-form-item>
      <n-form-item
        v-if="rogue.check_collapsal_paradigms ?? rogue.mode === 5"
        :label="t('maaActivities.doubleCheckParadigms')"
      >
        <n-select
          :consistent-menu-width="false"
          v-model:value="rogue.double_check_collapsal_paradigms"
          :options="foldartal_options"
        />
      </n-form-item>
    </template>
    <n-form-item
      v-if="
        maa_rg_theme === 'Sarkaz' &&
        rogue.mode === 1 &&
        ['点刺成锭分队', '后勤分队'].includes(rogue.squad)
      "
      :label="t('maaActivities.investmentSeed')"
    >
      <n-input v-model:value="rogue.start_with_seed" :placeholder="t('maaActivities.noSeed')" />
    </n-form-item>
    <n-form-item
      v-if="maa_rg_theme === 'BlackFlow' && rogue.mode === 0"
      :label="t('maaActivities.levelRoute')"
    >
      <n-select
        :consistent-menu-width="false"
        v-model:value="rogue.blackflow_strategy"
        :options="[
          { label: t('maaActivities.followMaaDefault'), value: '' },
          { label: t('maaActivities.burn'), value: 'burn' },
          { label: t('maaActivities.burnInvestment'), value: 'burn_with_investment' },
          { label: t('maaActivities.ending', { number: 1 }), value: 'ending1' },
          { label: t('maaActivities.ending', { number: 2 }), value: 'ending2' },
          { label: t('maaActivities.ending', { number: 3 }), value: 'ending3' }
        ]"
      />
    </n-form-item>
    <template v-if="maa_rg_theme === 'BlackFlow' && rogue.mode === 30003">
      <n-form-item :label="t('maaActivities.prepAnimals')">
        <n-flex vertical style="width: 100%">
          <n-select
            :consistent-menu-width="false"
            v-for="index in 2"
            :key="index"
            clearable
            :value="rogue.blackflow_start_animals?.[index - 1] ?? null"
            :options="blackflow_animals"
            :placeholder="t('maaActivities.noAnimal')"
            @update:value="set_animal(index - 1, $event)"
          />
          <n-text depth="3">{{ t('maaActivities.prepAnimalHelp') }}</n-text>
        </n-flex>
      </n-form-item>
      <n-form-item :label="t('maaActivities.targetOpeningRewards')">
        <n-flex vertical style="width: 100%">
          <n-select
            :consistent-menu-width="false"
            multiple
            v-model:value="blackflow_reward_values"
            :options="blackflow_rewards"
          />
          <n-text depth="3">{{ t('maaActivities.targetRewardHelp') }}</n-text>
        </n-flex>
      </n-form-item>
      <n-form-item :label="t('maaActivities.utopiaFirstFloor')">
        <n-checkbox v-model:checked="rogue.blackflow_start_utopia">{{
          t('maaActivities.utopiaEnabled')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item :label="t('maaActivities.rewardPriority')">
        <n-flex vertical style="width: 100%">
          <n-select
            :consistent-menu-width="false"
            multiple
            v-model:value="rogue.blackflow_start_reward_priority"
            :options="blackflow_rewards"
          />
          <n-text depth="3">{{ t('maaActivities.rewardPriorityHelp') }}</n-text>
        </n-flex>
      </n-form-item>
      <n-form-item :label="t('maaActivities.prepRoles')">
        <n-select
          :consistent-menu-width="false"
          clearable
          :value="rogue.collectible_mode_roles"
          @update:value="rogue.collectible_mode_roles = $event ?? ''"
          :options="roles"
          :placeholder="t('maaActivities.followOpeningRoles')"
        />
      </n-form-item>
      <n-form-item :label="t('maaActivities.prepRecruit')">
        <maa-rogue-recruit v-model="rogue.collectible_mode_core_char_list" :options="operators" />
      </n-form-item>
    </template>
    <n-form-item
      v-if="is_field_enabled('monthly_squad_auto_iterate', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.monthly_squad_auto_iterate">{{
        t('tasks.iterateMonthlySquads')
      }}</n-checkbox>
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
      <n-checkbox v-model:checked="rogue.monthly_squad_check_comms">{{
        t('tasks.checkMonthlyComms')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('deep_exploration_auto_iterate', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.deep_exploration_auto_iterate">{{
        t('tasks.iterateDeepInvestigations')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('refresh_trader_with_dice', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.refresh_trader_with_dice">{{
        t('tasks.refreshTraderDice')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      :label="t('tasks.collapsalParadigms')"
      v-if="is_field_enabled('expected_collapsal_paradigms', maa_rg_theme, rogue.mode)"
    >
      <n-select
        :consistent-menu-width="false"
        multiple
        :options="col_list"
        v-model:value="rogue.expected_collapsal_paradigms"
      />
    </n-form-item>
    <n-form-item :label="t('tasks.difficulty')">
      <n-select
        v-model:value="rogue.difficulty"
        :options="difficulty_options(maa_rg_theme)"
        :consistent-menu-width="false"
      />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_at_final_boss', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_at_final_boss">{{
        t('tasks.stopBeforeFinalBoss')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_at_max_level', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_at_max_level">{{
        t('tasks.stopAtMaxLevel')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item :show-label="false">
      <n-checkbox v-model:checked="rogue.investment_enabled" :disabled="rogue.mode === 1">{{
        t('tasks.investIngots')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('stop_when_investment_full', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.stop_when_investment_full">{{
        t('tasks.stopInvestmentFull')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('investment_with_more_score', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.investment_with_more_score">{{
        t('tasks.investmentMoreScore')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('collectible_mode_shopping', maa_rg_theme, rogue.mode)"
      :show-label="false"
    >
      <n-checkbox v-model:checked="rogue.collectible_mode_shopping">{{
        t('tasks.collectibleShopping')
      }}</n-checkbox>
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('collectible_mode_squad', maa_rg_theme, rogue.mode)"
      :label="rogue.mode === 30003 ? t('maaActivities.prepSquad') : t('tasks.collectibleSquad')"
    >
      <n-select
        :consistent-menu-width="false"
        v-model:value="rogue.collectible_mode_squad"
        :options="collectible_squad_options"
      />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('first_floor_foldartal', maa_rg_theme, rogue.mode)"
      :label="t('tasks.firstFloorFoldartal')"
    >
      <n-input
        v-model:value="rogue.first_floor_foldartal"
        :placeholder="t('tasks.foldartalNameEmpty')"
        style="width: 200px"
      />
    </n-form-item>
    <n-form-item
      v-if="start_foldartal_visible(maa_rg_theme, rogue.mode, rogue.squad)"
      :label="t('tasks.startingFoldartals')"
    >
      <n-input
        v-model:value="start_foldartal_values"
        :placeholder="t('tasks.commaSeparatedThree')"
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
      :label="t('tasks.startingRewardTargets')"
    >
      <n-select
        :consistent-menu-width="false"
        multiple
        :options="start_reward_options"
        v-model:value="start_reward_values"
      />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('blackflow_cultivation_target', maa_rg_theme, rogue.mode)"
      :label="t('tasks.swaddledAnimalTarget')"
    >
      <n-select
        :consistent-menu-width="false"
        v-model:value="rogue.blackflow_cultivation_target"
        :options="blackflow_target_options"
      />
    </n-form-item>
    <n-form-item
      v-if="is_field_enabled('find_playtime_target', maa_rg_theme, rogue.mode)"
      :label="t('tasks.playtimeTarget')"
    >
      <n-select
        :consistent-menu-width="false"
        v-model:value="rogue.find_playtime_target"
        :options="find_playtime_options"
      />
    </n-form-item>
  </n-form>
</template>
